# Intégration opérationnelle locale

## Portée

ARET-MMU relie désormais la mémoire SQLite canonique au cycle de session Claude Code, au transport Git limité au Memory Store et aux Memory Bundles vérifiés. Aucun service persistant n’est requis. Les mutations de mémoire restent transactionnelles ; les éventuelles mutations Git et les checkpoints de compaction sont configurables et bornés.

| Mécanisme | Emplacement | Déclenchement | Écriture par défaut |
|---|---|---|---|
| Restauration de session | `.claude/hooks/aret-mmu-session-start.sh` | `SessionStart` | Arme la barrière, sans mutation SQLite |
| Checkpoint Pre/PostCompact | `.claude/hooks/aret-mmu-pre-compact.sh`, `.claude/hooks/aret-mmu-post-compact.sh` | Compaction Claude Code | Désactivée, opt-in ; `PostCompact` réarme la barrière |
| Garde de reprise | `.claude/hooks/aret-mmu-resume-*.sh` | `PreToolUse`, `PostToolUse`, `Stop` | État éphémère local uniquement |
| Git Memory Store | `ops/git_memory.py` | Opération mémoire contrôlée ou CLI | Selon politique Git |
| Memory Bundle v3 | CLI et MCP | Export/import explicite | Import sur cible vide uniquement |

## Hooks Claude Code installés

Le fichier `.claude/settings.json` du dépôt ARET configure `SessionStart`, `PreCompact`, `PostCompact`, `PreToolUse`, `PostToolUse` et `Stop`. Le dépôt principal peut lancer son hook de préparation avant le hook ARET-MMU ; la distribution autonome ARET-MMU ne dépend que de ses propres wrappers. Le contexte de reprise est issu de SQLite et du statut Git en lecture seule, jamais d’une reconstruction heuristique de conversation.

`SessionStart` et `PostCompact` émettent une réponse JSON contenant `hookSpecificOutput.additionalContext`. Claude Code reçoit automatiquement depuis SQLite le contenu intégral, page par page, des documents 70, 80, 81, 82 et 90, ainsi que les huit dernières entrées complètes du journal 71. Le paquet ajoute doctrine, Front, roadmap, audit, assets, branche et commits, état de l’arbre, outils MCP et catalogue de pipelines. Les documents source sont donc ingérés et transmis sans relecture Markdown après compaction. Si le corpus dépasse la borne de transport, le hook échoue au lieu de tronquer silencieusement le contexte. Le garde éphémère exige que l’agent produise le récapitulatif des règles, de l’état, des capacités, de Git, des limites et de la prochaine action, puis appelle `aret_acknowledge_resume`. `PreToolUse` refuse toute autre action jusqu’à cette confirmation ; `PostToolUse` valide une confirmation MCP réussie ; `Stop` émet une relance unique lorsque `stop_hook_active` n’est pas déjà fixé.

Les checkpoints Pre/PostCompact restent non destructifs par défaut. Pour auditer les événements de compaction dans `audit_event`, activez explicitement la variable suivante dans l’environnement du runtime Claude Code.

```bash
export ARET_HOOK_WRITE_ENABLED=true
```

Cette activation écrit uniquement des événements `SESSION_CHECKPOINT` bornés dans l’audit. Le résumé de compaction n’est jamais transformé en connaissance canonique.

## Vérification locale

```bash
cd /chemin/vers/Automatic-reverse-engineering-toolkit
printf '{"source":"compact"}\n' | \
  CLAUDE_PROJECT_DIR="$PWD" .claude/hooks/aret-mmu-session-start.sh
```

La réponse doit contenir une clé `hookSpecificOutput` dont `hookEventName` vaut `SessionStart`, un `additionalContext` non vide, les cinq en-têtes de documents canoniques complets, les huit dernières entrées 71 et un résumé `resume_guard`. Dans Claude Code, la commande `/hooks` permet ensuite de vérifier les six événements effectivement configurés. Tenter une opération `Bash`, `Edit` ou `Write` avant l’appel réussi à `aret_acknowledge_resume` doit produire un refus `PreToolUse`.

## Git limité au Memory Store

Le gestionnaire Git refuse une cible qui n’est pas un dossier `.aret-memory/` contenu dans le dépôt. Il refuse aussi toute opération si des changements hors de ce namespace sont présents, et ne tente aucune fusion SQLite. Dans le dépôt ARET, le chemin cible est `aret-memory/.aret-memory`.

```bash
python3 aret-memory/ops/git_memory.py \
  --repository /chemin/vers/Automatic-reverse-engineering-toolkit \
  status
```

La politique de synchronisation après mutation, sa branche et le comportement de push sont définis de façon explicite dans la configuration de synchronisation ARET-MMU. Les conflits Git touchant `.aret-memory/` doivent toujours être refusés et résolus hors du MCP.

## Memory Bundle v3

Un bundle v3 est une archive ZIP contenant le snapshot canonique, le manifeste hashé, les artefacts de preuve, l’identité de source facultative et les migrations SQL applicables avec leurs SHA-256. L’import vérifie toutes ces données avant activation, reconstruit FTS5, est idempotent pour un même bundle et refuse la fusion vers une cible non vide.

```bash
cd aret-memory
python3 cli/aret_memory.py --memory-dir .aret-memory export-bundle --name transfert_aret
python3 cli/aret_memory.py \
  --memory-dir /chemin/vers/cible/.aret-memory \
  --write-enabled import-bundle \
  .aret-memory/exports/transfert_aret.bundle.zip
```

> Un bundle est un mécanisme de transfert ou de secours. Il ne permet pas de synchroniser concurrentiellement deux fichiers SQLite vivants.

Les opérations correspondantes sont disponibles au MCP par `aret_export_bundle` et `aret_import_bundle`.

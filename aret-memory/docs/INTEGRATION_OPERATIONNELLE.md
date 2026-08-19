# Intégration opérationnelle locale

## Portée

ARET-MMU relie désormais la mémoire SQLite canonique au cycle de session Claude Code, au transport Git limité au Memory Store et aux Memory Bundles vérifiés. Aucun service persistant n’est requis. Les mutations de mémoire restent transactionnelles ; les éventuelles mutations Git et les checkpoints de compaction sont configurables et bornés.

| Mécanisme | Emplacement | Déclenchement | Écriture par défaut |
|---|---|---|---|
| Restauration de session | `.claude/hooks/aret-mmu-session-start.sh` | `SessionStart` | Aucune |
| Checkpoint Pre/PostCompact | `.claude/hooks/aret-mmu-pre-compact.sh`, `.claude/hooks/aret-mmu-post-compact.sh` | Compaction Claude Code | Désactivée, opt-in |
| Git Memory Store | `ops/git_memory.py` | Opération mémoire contrôlée ou CLI | Selon politique Git |
| Memory Bundle v3 | CLI et MCP | Export/import explicite | Import sur cible vide uniquement |

## Hooks Claude Code installés

Le fichier `.claude/settings.json` du dépôt ARET est configuré pour lancer le hook de préparation ARET existant, puis le hook ARET-MMU à chaque `SessionStart`. Les événements `PreCompact` et `PostCompact` appellent également les wrappers ARET-MMU. Le rituel historique qui rechargeait de gros documents Markdown ne fait plus partie de la configuration active : le contexte chaud provient de SQLite.

`SessionStart` émet une réponse JSON contenant `hookSpecificOutput.hookEventName="SessionStart"` et `hookSpecificOutput.additionalContext`. Claude Code injecte donc un contexte compact comprenant la doctrine, la version mémoire, l’Active Front et les adresses pertinentes. Les pages froides restent chargées uniquement par `FIND`, puis `READ` ou `READ_BATCH`.

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

La réponse doit contenir une clé `hookSpecificOutput` dont `hookEventName` vaut `SessionStart` et un `additionalContext` non vide. Dans Claude Code, la commande `/hooks` permet ensuite de vérifier les trois événements effectivement configurés.

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

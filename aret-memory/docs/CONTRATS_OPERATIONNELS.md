# Contrats opérationnels ARET-MMU

## Principes

Les opérations de session, de synchronisation et de transport mémoire sont **déterministes, auditables et bornées**. Elles ne transforment pas un résultat de recherche en preuve, ne sélectionnent pas un résultat technique à la place de l’opérateur et ne promeuvent jamais une connaissance sans preuve HMAC-admissible.

> Les hooks ne sont pas des démons. Le runtime hôte les appelle à des événements précis ; chaque script lit un JSON, produit une réponse JSON bornée, puis termine.

| Domaine | Règle actuelle |
|---|---|
| Hooks | Lecture seule par défaut. `SessionStart` et `PostCompact` injectent un Resume Dossier V1.1 prêt puis arment une barrière liée à son hash ; les checkpoints exigent `ARET_HOOK_WRITE_ENABLED=true`. |
| Front | `update_front` modifie un sous-ensemble ; `replace_front` remplace le contexte chaud et conserve l’état précédent dans l’audit. |
| Git | Les commits sont limités à `.aret-memory/`. Toute modification hors périmètre refuse le commit mémoire. |
| WAL | Checkpoint `TRUNCATE` avant commit Git et export de bundle ; un SQLite occupé bloque l’opération concernée. |
| Fichiers temporaires | `.aret-memory/*.sqlite-wal`, `.sqlite-shm` et `runtime/` sont ignorés par Git ; la base `.sqlite` reste versionnable. |
| Relations | Les traversées retournent `ACTIVE` par défaut ; `include_inactive=true` expose les liens `SUPERSEDED` et leur `superseded_by`. |
| Briques | Le bootstrap initialise les jalons `M7-GUI`, `AUTO-LIFT-02`, `FIBERS-01` à `FIBERS-05` et `PHASE-A` à `PHASE-C`. |
| Bundle | Version 3, manifest/snapshot/migrations/artefacts hashés et contrôlés. |
| Import | Store cible vide uniquement ; aucun merge SQLite implicite. |

## Hooks Claude Code installés

`.claude/settings.json` active les lanceurs ARET-MMU exécutables suivants.

| Événement | Lanceur installé | Comportement |
|---|---|---|
| `SessionStart` | `.claude/hooks/aret-mmu-session-start.sh` | Vérifie et injecte le Resume Dossier V1.1, puis arme une barrière liée à son empreinte. |
| `PreCompact` | `.claude/hooks/aret-mmu-pre-compact.sh` | Retourne Front, audit récent borné et contexte de reprise ; checkpoint seulement sur activation. |
| `PostCompact` | `.claude/hooks/aret-mmu-post-compact.sh` | Réinjecte un Resume Dossier V1.1 fraîchement vérifié et réarme une barrière liée à son empreinte ; trace optionnelle de compaction. |
| `PreToolUse` | `.claude/hooks/aret-mmu-resume-pre-tool.sh` | Refuse tout outil sauf `aret_acknowledge_resume` tant que le récapitulatif rituel n’est pas confirmé. |
| `PostToolUse` | `.claude/hooks/aret-mmu-resume-post-tool.sh` | Ne lève la barrière que si les six volets sont valides et si le hash transmis égale le contrat injecté. |
| `Stop` | `.claude/hooks/aret-mmu-resume-stop.sh` | Fournit une relance unique lorsque l’agent tente de conclure sans récapitulatif confirmé. |

`SessionStart` et `PostCompact` n’injectent ni historique massif ni extraits sélectionnés par date. Ils exigent et formatent un **Resume Dossier V1.1** à six sections fixes : playbook stable, handoff actif, adresses pertinentes, capacités/outils/portes, Git/limites/garde-fous et rituel. Le playbook utilise exclusivement `knowledge` et `knowledge_tag` : ses cinq domaines obligatoires sont `PLAYBOOK_FOUNDATION`, `PLAYBOOK_METHOD`, `PLAYBOOK_ARCHITECTURE` avec `PLAYBOOK_SHARED_STACK`, `PLAYBOOK_GATES` et `PLAYBOOK_TOOLING`, tous sous le tag `CORE_PLAYBOOK`. La migration one-off `migration/bootstrap_playbook_v11.py` ajoute idempotemment trois fiches `RULE` compactes de méthode, gates et diagnostic, sous `DERIVED_PLAYBOOK_V11`, puis les relie par `DERIVED_FROM` aux sources canoniques. Cette migration est hors des hooks et de `aret_prepare_handoff`, qui ne fait qu’écrire transactionnellement le handoff dans `front_state`. Son `handoff_front_hash` doit égaler le hash du Front courant, faute de quoi le dossier est `STALE` et le hook échoue bruyamment. Le dossier est borné à 12 500 octets ; le contexte final est borné à 18 500 octets, sans troncature. Après injection, l’agent rédige les six volets du rituel et transmet également `resume_contract_hash` à `aret_acknowledge_resume`. `PostToolUse` compare cette valeur au hash armé pour la session ; toute divergence maintient la barrière. L’état du garde est éphémère sous `.aret-memory/runtime/resume_guard/`, donc n’est ni une connaissance SQLite ni une donnée Git. Le résumé de compaction, lorsqu’il est fourni, reste un champ d’audit et ne devient pas une connaissance canonique.

## Git mémoire local

`ops/git_memory.py` fournit les opérations directes `status`, `commit` et `push`, auxquelles s’ajoute `automatic_sync()` appelé après une mutation SQLite uniquement si `.aret-memory/sync_policy.json` active `auto_commit`.

```json
{
  "auto_commit": false,
  "auto_push": false,
  "remote": "origin",
  "branch": ""
}
```

La politique livrée ne committte ni ne pousse automatiquement. Le chemin mémoire est toujours calculé avec `git rev-parse --show-toplevel` : depuis le sous-répertoire `aret-memory/`, le périmètre Git réel demeure `aret-memory/.aret-memory/`. Si `auto_commit=true`, la synchronisation :

1. localise le dépôt Git et le seul répertoire `.aret-memory/` autorisé ;
2. force `PRAGMA wal_checkpoint(TRUNCATE)` sur `aret_memory.sqlite` ;
3. refuse les changements Git hors du Memory Store ;
4. ajoute et committte uniquement le sous-arbre mémoire ;
5. pousse seulement si `auto_push=true` et une branche explicite est configurée.

Un échec Git est exposé dans l’état de synchronisation mais ne revient jamais en arrière sur une transaction SQLite déjà validée. Le MCP expose `aret_sync_memory` pour déclencher cette politique locale ; il ne fournit aucun accès Git généraliste.

## Memory Bundle v3

```text
bundle.zip
├── manifest.json       # Version, hashes, device source, inventaires
├── snapshot.json       # Tables canoniques et métadonnées sérialisées
├── artifacts/          # Copies hashées d’artefacts de preuve
└── schema/             # Migrations SQL avec SHA-256 vérifié
```

Avant l’export, le Store force un checkpoint WAL. Le manifest v3 contient le hash logique du snapshot, son SHA-256, le hash du manifest, `source_device_id`, l’inventaire des artefacts et l’inventaire hashé des migrations. L’import refuse les chemins dangereux, le ZIP incomplet, un manifest/snapshot/migration/artefact altéré, un artefact en collision et toute cible non vide.

L’import est idempotent pour un hash de bundle déjà connu. La non-fusion est volontaire : deux mémoires vivantes doivent être comparées et réconciliées par une décision explicite, jamais par une heuristique SQLite.

## Vérification locale

```bash
cd aret-memory
pytest -q
python3 tests/mcp_integration_check.py
python3 -m compileall -q aret_mmu_server.py core evidence hooks migration ops
```

Les tests couvrent les hooks, la séparation FIND/READ, les preuves HMAC, le confinement Git depuis un Memory Store imbriqué, les checkpoints WAL, les bundles v3, les relations adressables et leur cycle de vie actif, le bootstrap de fonctions/briques/graphe, la réinitialisation auditée du Front, le bootstrap Playbook V1.1 idempotent, ses six relations `DERIVED_FROM`, les procédures et outils effectivement injectés, la fraîcheur du handoff et le refus d’une confirmation dont le hash ne correspond pas. Le catalogue d’oracles couvre désormais neuf gates fermés. [1] [2]

## Références

[1]: ../ops/git_memory.py "Git mémoire et checkpoint WAL"
[2]: ../core/repository.py "Transactions, Front, bundles et audit"
[3]: ../../.claude/settings.json "Hooks installés"

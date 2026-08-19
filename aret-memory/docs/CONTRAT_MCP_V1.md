# Contrat MCP ARET-MMU — État opérationnel v5

## Objet et doctrine

ARET-MMU est une façade MCP déterministe devant un **Memory Store SQLite** local. SQLite est la source de vérité ; FTS5, exports, bundles et contexte restauré sont des représentations dérivées. La façade ne propose ni SQL libre, ni commande shell générique, ni recherche sémantique autoritative.

> **Principe de sûreté.** `FIND` découvre des candidats. Seuls `READ` et `READ_BATCH`, sur des adresses explicitement sélectionnées, retournent le contenu canonique. Un score de recherche ne démontre jamais une propriété du programme.

| Domaine | Contrat actuel |
|---|---|
| Transport | Stdio par défaut ; HTTP diffusible seulement sur lancement explicite avec `--streamable-http`. |
| Répertoire mémoire | `.aret-memory/`, configurable avec `--memory-dir` ou `ARET_MEMORY_DIR`. |
| Base canonique | `.aret-memory/aret_memory.sqlite`, en SQLite WAL avec clés étrangères actives. |
| Écriture | Lecture seule par défaut ; `ARET_WRITE_ENABLED=true` ou `--write-enabled` est requis pour toute mutation. |
| Artefacts | Sous `.aret-memory/artifacts/`, hors SQLite, hashés et lus explicitement sous borne. |
| Preuves | `PROVEN` exige une preuve liée, `PASS` et HMAC-admissible. |
| Historique | Connaissances append-first ; aucune suppression générale ni réécriture de contenu via MCP. |
| Git | Limité à `.aret-memory/`; `auto_commit=false` et `auto_push=false` par défaut. |

## Ressources adressables

| Ressource | Adresse |
|---|---|
| Connaissance | `ARET://knowledge/<knowledge_id>` |
| Composant | `ARET://component/<component_id>` |
| Fonction | `ARET://function/<component:module!symbol>` |
| Brique | `ARET://brick/<brick_id>` |
| Preuve | `ARET://proof/<proof_id>` |
| Relation | `ARET://relation/<relation_id>` |
| Mémoire chaude | `ARET://front/current` |

Toutes les adresses sont validées et canoniques. `aret_read` peut lire chacune des ressources ci-dessus, y compris une relation retournée par `aret_add_relation` ou `aret_supersede_relation`.

## Outils MCP actuels

Le serveur déclare **32 outils métier**.

| Outil | Mode | Contrat principal |
|---|---|---|
| `aret_boot` | Lecture | Doctrine, versions, chemins, mode écriture, HMAC et état de synchronisation. |
| `aret_get_front` | Lecture | Active Front et adresses pertinentes. |
| `aret_restore` | Lecture | Noyau de reprise borné : doctrine, versions et Front. |
| `aret_find` | Lecture | Découverte structurée/FTS sans contenu intégral. |
| `aret_read` | Lecture | Lecture exacte d’une adresse ARET. |
| `aret_read_batch` | Lecture | Lecture de plusieurs adresses connues sous bornes d’items et d’octets. |
| `aret_get_forensics` | Lecture | Découverte des forensics ciblée par composant ou fonction. |
| `aret_get_proofs` | Lecture | Métadonnées des preuves liées à une connaissance. |
| `aret_get_related` | Lecture | Relations `ACTIVE` autour d’une entité connue ; historique seulement avec `include_inactive=true`. |
| `aret_get_roadmap` | Lecture | Vue compacte et bornée des briques, priorités, états, bloqueurs, décisions et preuves actives. |
| `aret_read_artifact` | Lecture | Lecture explicite, hashée et bornée d’un artefact. |
| `aret_append_knowledge` | Écriture | Création append-first, tags, provenance et liaisons de preuve contrôlées. |
| `aret_update_front` | Écriture | Mise à jour partielle, bornée et auditée du Front. |
| `aret_replace_front` | Écriture | Remplacement intégral et audité du Front, sans toucher à l’historique métier. |
| `aret_rebuild_front` | Écriture | Ajout prudent de pointeurs dérivés au Front. |
| `aret_record_proof` | Écriture | Enregistrement d’une preuve et contrôle de son reçu HMAC. |
| `aret_attach_proof` | Écriture | Liaison de preuve et promotion conditionnelle. |
| `aret_invalidate_proof` | Écriture | Invalidation et réévaluation transactionnelle des `PROVEN`. |
| `aret_add_relation` | Écriture | Ajout d’un lien typé entre deux entités existantes. |
| `aret_supersede_relation` | Écriture | Nouveau lien de remplacement et audit append-only de la relation remplacée. |
| `aret_register_component` | Écriture | Création d’un composant stable. |
| `aret_register_function` | Écriture | Création d’un symbole rattaché à un composant. |
| `aret_register_brick` | Écriture | Création d’une brique avec état, jalon, cible et priorité validés. |
| `aret_update_brick` | Écriture | Mise à jour auditée d’état, jalon, cible et priorité ; refuse de désactiver une brique encore affichée dans le Front. |
| `aret_run_oracle` | Écriture | Exécution d’un oracle de liste fermée, artefact et preuve. |
| `aret_sync_memory` | Opérationnel | Auto-sync local selon `sync_policy.json`, jamais hors `.aret-memory/`. |
| `aret_rebuild_index` | Écriture | Reconstruction FTS5 à partir du canonique. |
| `aret_export_reference_91` | Export | Vue 91 dérivée du canonique ; elle ne remplace pas la provenance historique. |
| `aret_export_roadmap` | Export | Roadmap Markdown dérivée et hashée, filtrable par jalon, composant ou plateforme. |
| `aret_export` | Export | JSON, Markdown, HTML ou bundle. |
| `aret_export_bundle` | Export | Bundle v3 hashé après checkpoint WAL. |
| `aret_import_bundle` | Import | Import vérifié vers Store vide, sans fusion implicite. |

## Invariants appliqués

| Invariant | Application |
|---|---|
| Intégrité transactionnelle | Toute mutation utilise `BEGIN IMMEDIATE`, puis commit ou rollback. |
| `PROVEN` | Validé dans le code et verrouillé par triggers SQLite sur insertion/promotion. |
| Append-first | Trigger SQL contre la réécriture sémantique des connaissances ; succession via une nouvelle page. |
| Audit | Événements avant/après sur opérations métier, Front, imports, index et checkpoints. |
| Relations | `ACTIVE` par défaut ; une supersession marque l’ancien lien `SUPERSEDED` et conserve `superseded_by`. |
| Roadmap | Les briques possèdent `milestone`, `target_platform` et `priority` (1–5) ; la vue roadmap reste dérivée de SQLite. |
| Front | La clé `brick` ne peut référencer qu’une brique `ACTIVE`, jamais une brique seulement planifiée. |
| Index | FTS5 entièrement reconstructible depuis `knowledge` et `knowledge_tag`. |
| Artefacts | Chemin sous `artifacts/`, SHA-256 contrôlé avant lecture. |
| Pagination | Défaut : 20 objets / 65 536 octets ; plafond : 100 objets / 262 144 octets. |
| WAL | Checkpoint `TRUNCATE` avant export de bundle et commit Git mémoire ; refus explicite si SQLite le signale occupé. |
| Git | Fichiers WAL/SHM exclus par `.gitignore`; toute modification hors Memory Store refuse le commit mémoire. |

## Intégrations opérationnelles

Les hooks Claude Code `SessionStart`, `PreCompact` et `PostCompact` sont installés dans `.claude/settings.json`. `SessionStart` injecte exclusivement le contexte minimal via `hookSpecificOutput.additionalContext`. Les checkpoints de compaction ne sont écrits que si `ARET_HOOK_WRITE_ENABLED=true`; ils sont des événements d’audit, non des connaissances autoritatives.

Les adaptateurs d’oracle autorisés sont `difftest`, `transpilediff`, `stdcall_audit`, `winediff`, `winehash`, `ehdiff`, `gnuehdiff`, `funcdiff` et `cpudiff`. Ils ne prennent aucune commande shell arbitraire : les huit scripts et la commande Cargo CPU sont codés dans le catalogue fermé. Une dépendance absente produit `SKIPPED`; `winehash` produit une mesure `UNKNOWN` à comparer à un runner Windows et ne peut pas promouvoir une connaissance.

## Références

[1]: ../aret_mmu_server.py "Façade MCP et outils enregistrés"
[2]: ../core/repository.py "Règles métier, transactions, WAL, exports et import"
[3]: ../core/addressing.py "Adressage ARET canonique"
[4]: ../schema/001_initial.sql "Contraintes et triggers SQLite"
[5]: ../ops/git_memory.py "Git mémoire borné, chemin relatif racine et checkpoint WAL"
[6]: ../evidence/adapters/oracles.py "Catalogue fermé des neuf oracles"
[7]: ../migration/bootstrap_initial_graph.py "Bootstrap des symboles, relations et briques"
[8]: ../schema/005_roadmap_bricks.sql "Métadonnées roadmap V1.1 des briques"
[9]: ../migration/bootstrap_roadmap_v11.py "Classement idempotent des briques existantes"

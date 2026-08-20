# Contrat MCP ARET-MMU — État opérationnel v5

## Objet et doctrine

ARET-MMU est une façade MCP déterministe devant un **Memory Store SQLite** local. SQLite est la source de vérité ; FTS5, exports, bundles et contexte restauré sont des représentations dérivées. La façade ne propose ni SQL libre, ni commande shell générique, ni recherche sémantique autoritative.

> **Principe de sûreté.** `FIND` découvre des candidats. Seuls `READ` et `READ_BATCH`, sur des adresses explicitement sélectionnées, retournent le contenu canonique. Un score de recherche ne démontre jamais une propriété du programme.

| Domaine | Contrat actuel |
|---|---|
| Transport | Stdio par défaut ; HTTP diffusible seulement sur lancement explicite avec `--streamable-http`. |
| Bootstrap Cloud | `scripts/launch_aret_mcp.sh` crée le venv, synchronise les dépendances sur changement de `pyproject.toml` et journalise uniquement sur stderr avant `exec`. |
| Répertoire mémoire | `.aret-memory/`, configurable avec `--memory-dir` ou `ARET_MEMORY_DIR`. |
| Base canonique | `.aret-memory/aret_memory.sqlite`, en SQLite WAL avec clés étrangères actives. |
| Écriture | Lecture seule par défaut ; `ARET_WRITE_ENABLED=true` ou `--write-enabled` est requis au démarrage pour toute mutation. |
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

Le serveur déclare **43 outils métier**.

| Outil | Mode | Contrat principal |
|---|---|---|
| `aret_boot` | Lecture | Doctrine, versions, chemins, mode écriture, HMAC et état de synchronisation. |
| `aret_get_front` | Lecture | Active Front et adresses pertinentes. |
| `aret_restore` | Lecture | Noyau de reprise borné : doctrine, versions et Front. |
| `aret_get_resume_brief` | Lecture | Vue de compatibilité pour investigation ciblée ; elle ne remplace pas le Resume Dossier injecté. |
| `aret_get_resume_protocol` | Lecture | Pointeurs documentaires et protocole historique, sans relecture obligatoire. |
| `aret_acknowledge_resume` | Lecture | Valide les six volets du rituel et exige le hash du Resume Dossier injecté. |
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
| `aret_prepare_handoff` | Écriture | Prépare atomiquement le handoff, `last_action` et le checkpoint V1.2 ; aucun outil supplémentaire n’est créé. |
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
| `aret_get_pipeline_catalog` | Lecture | Catalogue fermé des pipelines ARET, politiques, prérequis et délais. |
| `aret_get_toolchain_status` | Lecture | État des dépendances ARET/Wine/MinGW/Rust/Unicorn/Clang/Z3. |
| `aret_run_pipeline` | Opérationnel | Planifie ou exécute un pipeline ARET fermé ; `dry_run=true` par défaut et confirmations explicites selon politique. |
| `aret_get_pipeline_runs` | Lecture | Derniers verdicts de pipeline sans charger leurs artefacts. |
| `aret_read_pipeline_artifact` | Lecture | Lecture bornée et hashée d’un artefact de pipeline adressé. |
| `aret_get_assets` | Lecture | Assets binaires, corpus et snapshots enregistrés avec hash et provenance. |
| `aret_register_asset` | Écriture | Import local confirmé, copie sous Store, hash et audit. |
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
| Resume Dossier V1.2 | Cinq domaines `CORE_PLAYBOOK` obligatoires, fiches opérationnelles dérivées compactes, handoff Front atomique et checkpoint technique conditionnel, sans table supplémentaire. |
| Checkpoint technique | `NONE` impose les cinq champs vides et déclare qu’aucun geste ne doit être inventé ; `ACTIVE` exige cible, changement, état, dernière validation et actions immédiates, chacun sous borne. |
| Cohérence du geste | `aret_prepare_handoff` écrit `last_action` avec le checkpoint actif, ou une absence explicite avec `NONE`, dans la même transaction. |
| Fraîcheur de reprise | `handoff_front_hash` couvre le checkpoint et doit égaler le Front courant ; une divergence rend le dossier `STALE` et bloque l’injection. |
| Bornes de reprise | Dossier ≤ 12 500 octets et contexte total ≤ 18 500 octets ; tout dépassement échoue explicitement, sans troncature. |
| Confirmation de reprise | Les six champs de rituel et `resume_contract_hash` doivent correspondre au hash armé par SessionStart/PostCompact ; sinon la barrière reste active. |
| Index | FTS5 entièrement reconstructible depuis `knowledge` et `knowledge_tag`. |
| Artefacts | Chemin sous `artifacts/`, SHA-256 contrôlé avant lecture. |
| Pipelines | Catalogue fermé, argv contrôlés, délais bornés et artefact hashé pour toute exécution réelle. |
| Génération | `dry_run=true` par défaut ; `confirm_apply=true` obligatoire pour l’exécution générative. |
| Réseau / sensible | Profils et sources fermés ; `confirm_network=true` ou `confirm_sensitive=true` obligatoire pour l’exécution réelle. |
| Assets | Copie sous Store, provenance, SHA-256, taille maximale 2 GiB ; chemins hors dépôt/artefacts refusés. |
| Pagination | Défaut : 20 objets / 65 536 octets ; plafond : 100 objets / 262 144 octets. |
| WAL | Checkpoint `TRUNCATE` avant export de bundle et commit Git mémoire ; refus explicite si SQLite le signale occupé. |
| Git | Fichiers WAL/SHM exclus par `.gitignore`; toute modification hors Memory Store refuse le commit mémoire. |
| Démarrage Cloud | Le profil `.mcp.json` versionné pointe vers le lanceur et fixe `ARET_WRITE_ENABLED=false` ; l’écriture nécessite une configuration distincte et un redémarrage MCP. |

## Intégrations opérationnelles

Les hooks Claude Code `SessionStart`, `PreCompact` et `PostCompact` sont installés dans `.claude/settings.json`. `SessionStart` et `PostCompact` sélectionnent exclusivement les connaissances `ACTIVE` taguées `CORE_PLAYBOOK`, puis construisent depuis `knowledge`, `knowledge_tag` et `front_state` un Resume Dossier V1.2 à six sections fixes : playbook stable, handoff actif incluant un checkpoint technique conditionnel, adresses pertinentes, capacités/outils/portes, Git/limites et rituel. Le bootstrap one-off `migration/bootstrap_playbook_v11.py` crée idempotemment les trois fiches dérivées et compactes de méthode, gates et diagnostic, avec relations `DERIVED_FROM` vers leurs sources historiques ; il n’est jamais appelé par un hook ni par `aret_prepare_handoff`. Cette macro écrit atomiquement les quatre champs de handoff, l’action suivante, les adresses chaudes, l’état `NONE` ou `ACTIVE` du checkpoint, les cinq faits techniques et `last_action`, puis leur hash de fraîcheur commun. `NONE` est le seul état admissible lorsqu’aucun geste n’est actif ; aucun checkpoint ne peut être rétrospectivement fabriqué par migration. Aucun document historique n’est injecté massivement ni relu par défaut. Les checkpoints de compaction ne sont écrits que si `ARET_HOOK_WRITE_ENABLED=true`; ils sont des événements d’audit, non des connaissances autoritatives.

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
[10]: ../schema/006_pipeline_assets.sql "Assets et exécutions de pipeline canonisés"
[11]: ../evidence/adapters/pipelines.py "Catalogue fermé, prévol, artefacts et confirmations"
[12]: ../migration/bootstrap_playbook_v11.py "Bootstrap idempotent des fiches opérationnelles dérivées"

# Pipelines ARET-MMU V1

## Objet

ARET-MMU expose désormais une **façade MCP fermée** sur les capacités opérationnelles d’ARET. Claude ne reçoit jamais un shell, une URL, un script ou un chemin de sortie arbitraire. Il choisit un pipeline nommé, consulte son plan avec `dry_run=true`, puis fournit les confirmations exigées par la politique du pipeline.

> Les pipelines ne modifient jamais le dépôt ARET implicitement, et `auto_push=false` demeure la politique mémoire par défaut. Chaque exécution réelle produit un artefact JSON hashé dans `.aret-memory/artifacts/pipelines/`, une entrée `pipeline_run` adressable et un événement d’audit append-only.

## Outils MCP ajoutés

| Outil MCP | Rôle |
|---|---|
| `aret_get_pipeline_catalog` | Catalogue des pipelines nommés, politiques, dépendances et délais. |
| `aret_get_toolchain_status` | État de Wine, MinGW, Rust, Unicorn, Clang, Z3, Winelib et binaire ARET. |
| `aret_run_pipeline` | Planifie ou exécute un pipeline fermé ; `dry_run=true` par défaut. |
| `aret_get_pipeline_runs` | Dernières exécutions et verdicts sans charger les artefacts lourds. |
| `aret_read_pipeline_artifact` | Lecture bornée, hashée et explicitement adressée d’un artefact de pipeline. |
| `aret_get_assets` | Inventaire des assets binaires, corpus et snapshots avec hash et provenance. |
| `aret_register_asset` | Import local explicitement confirmé d’un PE32, DLL, IAT map ou snapshot. |
| `aret_get_resume_brief` | Paquet de reprise : Front, règles, journal 71, audit ; Git reste en lecture seule séparée. |

## Catalogue de pipelines

| Politique | Pipelines | Confirmation requise |
|---|---|---|
| `READ_ONLY` | `toolchain_status`, `inspect_binary`, `measure_binary_walls`, `measure_walls`, `measure_corpus_imports`, `run_regression_gate`, `run_gauntlet`, `run_busybox_sweep`, `run_sqlite_sweep`, `run_transpile_diff`, `run_inplace_diff`, `prove_rewrites`, `run_magicdiv_check`, `run_relay_diff`, `measure_wine_heavy` | Aucune pour l’exécution, mais le Store doit être en écriture pour persister l’artefact et l’audit. |
| `GENERATE` | `generate_flirt_signatures`, `execute_auto_lift`, `generate_stdcall_pops`, `generate_win32_signatures`, `generate_codepage_cp1252`, `generate_codepage_cp437`, `generate_mlang_codepage`, `run_wine_heavy_proof`, `build_gauntlet` | `dry_run=false` et `confirm_apply=true`. |
| `NETWORK` | `fetch_wall_corpus`, `setup_winelib` | `dry_run=false` et `confirm_network=true`. Sources, profils et commandes sont fermés. |
| `SENSITIVE` | `capture_snapshot` | `dry_run=false` et `confirm_sensitive=true`. Le PID et la plage mémoire sont bornés et journalisés. |

Les oracles existants restent disponibles via `aret_run_oracle` : `difftest`, `transpilediff`, `stdcall_audit`, `winediff`, `winehash`, `ehdiff`, `gnuehdiff`, `funcdiff` et `cpudiff`. Ils ne sont pas dupliqués dans les pipelines.

## Corpus et walls

`fetch_wall_corpus` est la voie contrôlée pour le corpus PE32 FOSS : trois profils fixes (`sample`, `medium`, `full`) correspondent respectivement à 25, 125 et 450 paquets. Les seules sources autorisées sont MSYS2 mingw32 et UnxUtils. L’exécution garde les journaux, déduplique les binaires et, en cas de succès, enregistre un asset `CORPUS` pointant vers le corpus local géré par le Store.

`measure_binary_walls` et `measure_walls` indiquent les instructions non modélisées, imports non pris en charge et appels non résolus. Un wall est une **mesure de priorité**, jamais une preuve de correction : toute correction reste validée par un oracle différentiel ou une preuve adaptée.

## Assets

Les assets sont sous `.aret-memory/artifacts/assets/` et ont des adresses `ARET://asset/AS-…`. L’import n’accepte que des fichiers localisés dans le dépôt ARET ou déjà sous les artefacts du Store. Le MCP enregistre le SHA-256, la taille, le type et la provenance ; les chemins hors périmètre et les assets de plus de 2 GiB sont refusés.

## Contexte Claude et reprise

Le hook `SessionStart` injecte désormais le Front, la doctrine, les règles actives, les dernières entrées 71, l’audit récent, le catalogue compact de pipelines et les huit derniers verdicts. Après une compression, Claude sait donc quels outils existent, quels pipelines sont récents, quelles confirmations sont nécessaires et quelles pages de mémoire lire avant action.

Les derniers commits et l’état de l’arbre restent volontairement hors SQLite. Ils doivent être fournis par un hook Git **lecture seule** ; ARET-MMU n’expose ni commande Git arbitraire ni push automatique.

## Sous-outils internes

Certains scripts sont délibérément conservés comme sous-étapes des pipelines plutôt que comme outils MCP publics séparés : `bench/eh/build.sh`, `bench/eh/gen_msvcrt_lib.py` et `bench/gen_transpile_driver.py` alimentent respectivement `ehdiff` et `run_transpile_diff`. Les exposer directement ferait apparaître des paramètres de compilation internes sans valeur pour la décision de Claude et élargirait inutilement la surface d’exécution. Le résultat fonctionnel reste accessible via les pipelines et oracles correspondants.

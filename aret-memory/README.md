# ARET-MMU

**ARET-MMU** est un serveur MCP local qui met en œuvre le noyau de l’architecture fournie : une mémoire durable SQLite, structurée, adressable, auditée et distincte des preuves d’exécution. Sa conception évite les documents monolithiques et les déductions sémantiques : une recherche découvre des candidats, tandis qu’une lecture par adresse restitue l’objet canonique exact.

> **SQLite est la source de vérité.** FTS5, les exports et le contexte d’un modèle sont des représentations dérivées, régénérables et non autoritatives.

| Élément | Implémentation livrée |
|---|---|
| Stockage canonique | `.aret-memory/aret_memory.sqlite` |
| Mémoire chaude | Table `front_state`, lue par `aret_get_front` |
| Découverte | Filtres structurés et FTS5 dérivé, via `aret_find` |
| Récupération | Adresses `ARET://…`, `aret_read` et `aret_read_batch` borné |
| Connaissances | Types, statuts, tags, relations et hashes de contenu |
| Preuves | Métadonnées SQLite et artefacts externes hashés sous `.aret-memory/artifacts/` |
| Promotion `PROVEN` | Refusée sans preuve `PASS` **admissible** et explicitement liée |
| Écriture | Désactivée par défaut ; mutations contrôlées, transactionnelles et auditées après activation explicite |
| Protocole | Stdio par défaut ; HTTP Streamable en option pour un déploiement local contrôlé |

## Périmètre V1

Le projet livre un serveur MCP réellement exécutable, des migrations SQLite versionnées, les couches d’accès déterministes, un CLI d’inspection, un mécanisme de reçus de preuve HMAC, des migrations documentaires sourcées et une suite de tests. Les écritures restent **désactivées par défaut** conformément à la phase de prototypage sans risque de l’architecture ; les outils d’écriture sont néanmoins implémentés derrière `ARET_WRITE_ENABLED=true` pour une activation progressive et contrôlée.

| Fonction | État |
|---|---|
| `boot`, Front, FIND, READ, READ_BATCH | Disponible |
| Composants, fonctions et briques adressables | Disponible, avec écriture activée |
| Append-first, versionnement et relations | Disponible, avec écriture activée |
| Preuves, intégrité des artefacts et invariant `PROVEN` | Disponible, avec écriture activée |
| Oracles `difftest`, `winediff`, `funcdiff` | Adaptateurs déterministes : capture d’artefact, HMAC, preuve, liaison et promotion contrôlée |
| Pipelines, corpus et assets | 27 pipelines fermés, politiques `READ_ONLY` / `GENERATE` / `NETWORK` / `SENSITIVE`, `dry_run` par défaut et artefacts hashés |
| Audit et reconstruction FTS5 | Disponible |
| Exports JSON, Markdown et bundle de lecture | Disponible |
| Références 70, 80 et 81 | Disponible : 86 objets sourcés, couverture des lignes substantielles et contrôle d’intégrité. |
| Journal 71 | Disponible : 378 entrées datées, contenu exact, provenance et contrôle d’exhaustivité. |
| Trackers 82 et 90 | Disponible : 50 sections non chevauchantes avec provenance et contrôle d’intégrité. |
| Corpus documentaire central | Disponible : 514 objets sourcés, index FTS5 reconstruit et vérifié. |
| Hooks de cycle de vie Claude Code | Disponible : contexte injecté à `SessionStart` / `PostCompact` et barrière de reprise obligatoire |
| Synchronisation Git automatique et résolution de conflits | Opt-in, bornée au Memory Store ; `auto_push=false` par défaut |

## Prérequis et installation

Le serveur requiert Python 3.11 ou ultérieur. Il utilise le SDK Python officiel MCP v2, qui permet d’exposer des outils typés sur les transports stdio et HTTP Streamable. [1]

```bash
cd /chemin/vers/aret-memory
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
```

La première exécution crée automatiquement `.aret-memory/`, sa base SQLite, le dossier `artifacts/` et les métadonnées de format. Elle ne charge aucun document historique et n’invente aucune mémoire.

```bash
aret-memory boot
python aret_mmu_server.py --memory-dir "$(pwd)/.aret-memory"
```

La dernière commande démarre le serveur en **stdio**. C’est le mode adapté à un client MCP local : aucune sortie métier ne doit être écrite sur stdout hors du protocole.

## Connexion comme MCP local

Le fichier de configuration suivant est un modèle. Remplacez les chemins par ceux de votre copie locale du projet et de son environnement virtuel. Le serveur est explicitement lancé en lecture seule ; cette configuration est le mode recommandé pour la première migration et les revues.

```json
{
  "mcpServers": {
    "ARET-MMU": {
      "command": "/chemin/vers/aret-memory/.venv/bin/python",
      "args": [
        "/chemin/vers/aret-memory/aret_mmu_server.py",
        "--memory-dir",
        "/chemin/vers/aret-memory/.aret-memory"
      ],
      "env": {
        "ARET_WRITE_ENABLED": "false"
      }
    }
  }
}
```

Après connexion, appelez `aret_boot`, puis `aret_get_front`. Lorsqu’une session vient de démarrer ou d’être compactée, les hooks injectent automatiquement depuis SQLite le contenu intégral des documents 70, 80, 81, 82 et 90, ainsi que les huit dernières entrées complètes du journal 71. Le paquet ajoute doctrine, Front, roadmap, audit, Git, assets et catalogue de pipelines. Produisez le récapitulatif rituel de ce paquet, puis appelez `aret_acknowledge_resume` : les hooks refusent toute autre opération tant que cette confirmation n’a pas réussi. Aucun fichier Markdown n’est à relire après compaction ; n’utilisez `aret_find`, `aret_read` ou `aret_read_batch` que pour approfondir une connaissance ciblée hors du paquet injecté. Le hook échoue explicitement si le corpus dépasse sa borne de transport, plutôt que de tronquer silencieusement le contexte. Un résultat de recherche ne doit jamais être traité comme une preuve.

| Outil | Usage |
|---|---|
| `aret_boot` | Lit doctrine, version du format, mode écriture et bornes. |
| `aret_get_front` | Récupère la mémoire chaude minimale. |
| `aret_restore` | Restitue le noyau de reprise : doctrine, versions et Active Front, sans historique massif. |
| `aret_get_resume_brief` / `aret_get_resume_protocol` | Restituent les pointeurs canoniques utiles à une investigation ciblée ; ils ne déclenchent aucune relecture obligatoire. |
| `aret_acknowledge_resume` | Confirme le récapitulatif rituel du contexte SQLite injecté après SessionStart ou PostCompact. |
| `aret_find` | Découvre des candidats par composant, tag, type, statut, dates ou FTS5. |
| `aret_read` / `aret_read_batch` | Restitue le contenu canonique, le hash et les métadonnées d’une ou plusieurs adresses connues. |
| `aret_get_forensics` | Découvre les forensics liés à un composant ou une fonction. |
| `aret_get_proofs` / `aret_read_artifact` | Inspecte des preuves, puis lit explicitement un artefact borné et vérifié. |
| `aret_run_oracle` | Exécute un oracle autorisé, capture son artefact et enregistre le proof correspondant. |
| `aret_attach_proof` | Lie une preuve existante ; la promotion est refusée hors `PASS` admissible. |
| `aret_invalidate_proof` | Retire une preuve admissible et réévalue transactionnellement les `PROVEN` liés. |
| `aret_get_related` | Traverse uniquement les relations explicitement stockées. |
| `aret_rebuild_front` | Reconstitue les pointeurs dérivés du Front sans supprimer les clés manuelles. |
| `aret_export` | Produit une vue JSON, Markdown, HTML ou un bundle vérifié. |
| `aret_get_pipeline_catalog` / `aret_run_pipeline` | Exposent uniquement des pipelines nommés et fermés, avec plan `dry_run`, confirmations explicites et artefacts hashés. |
| `aret_get_assets` / `aret_register_asset` | Inventorient et importent les corpus et artefacts admis, sans chemin arbitraire. |

## Activation contrôlée des écritures

N’activez les écritures qu’après avoir validé les parcours de lecture et la politique de preuves. L’activation est explicite et limitée au processus lancé.

```bash
export ARET_WRITE_ENABLED=true
python aret_mmu_server.py --memory-dir "$(pwd)/.aret-memory" --write-enabled
```

Les outils `aret_register_component`, `aret_register_function`, `aret_register_brick`, `aret_append_knowledge`, `aret_update_front`, `aret_rebuild_front`, `aret_record_proof`, `aret_attach_proof`, `aret_invalidate_proof`, `aret_add_relation` et `aret_rebuild_index` deviennent alors disponibles. Toute mutation se déroule dans une transaction SQLite et génère un événement d’audit. Il n’existe pas d’outil MCP de suppression ni de réécriture du contenu d’une connaissance.

### Preuves et statut `PROVEN`

Une preuve `PASS` ne devient admissible que si un adaptateur de confiance produit un reçu HMAC-SHA256 canonique. L’adaptateur et le serveur partagent `ARET_PROOF_HMAC_SECRET`, qui ne doit pas être communiqué à un modèle ni inscrit dans une instruction utilisateur. Sans reçu valide, la preuve reste conservée pour audit mais ne peut pas justifier un statut `PROVEN`.

```bash
export ARET_PROOF_HMAC_SECRET='valeur-secrète-générée-localement'
python -m evidence.capture /chemin/vers/manifest_preuve.json --output /chemin/vers/receipt.json
```

Le manifeste contient les mêmes champs que `aret_record_proof` : `kind`, `command`, `result`, `exit_code`, `artifact_path`, `artifact_hash`, `environment`, `started_at` et `finished_at`. Pour un artefact, placez d’abord le fichier sous `.aret-memory/artifacts/`, puis calculez et transmettez son hash SHA-256. Toute lecture vérifie à nouveau ce hash.

## CLI de maintenance et d’audit

Le CLI évite le SQL direct tout en donnant accès aux opérations de lecture et de maintenance explicites.

```bash
aret-memory boot
aret-memory show-front
aret-memory find --component EH --type FORENSIC --status PROVEN --tag ABI
aret-memory read ARET://knowledge/EH-0042
aret-memory show-proofs EH-0042
aret-memory related EH-0042 --type SUPERSEDES
aret-memory export --format markdown --name revue_eh
aret-memory --write-enabled rebuild-index
```

Le fichier d’export est toujours dérivé de l’état canonique. Le format `bundle` produit un ZIP v3 importable : manifest hashé, snapshot canonique, migrations hashées et artefacts vérifiés. Un checkpoint WAL est effectué avant la sérialisation ; un import est idempotent pour le même bundle et refusé dans une cible non vide afin d’empêcher toute fusion implicite de mémoires vivantes.

## Migrations documentaires ARET

Les importeurs conservent chaque extrait Markdown exact, son commit source, son chemin, ses lignes, sa section et son hash SHA-256. Ils sont idempotents pour une même révision et ne créent jamais de statut `PROVEN` à partir d’un texte historique.

```bash
# Migration pilote historique, utile seulement pour reconstruire un Store vierge.
python3 migration/import_pilot.py

# Compléter et contrôler les références 70/80/81.
python3 migration/import_references_70_80_81.py
python3 migration/verify_references_70_80_81.py

# Migration exhaustive des 378 entrées datées du journal 71, puis vérification.
python3 migration/import_journal_71.py
python3 migration/verify_journal_71.py

# Migration structurée des trackers 82/90, puis vérification.
python3 migration/import_trackers_82_90.py
python3 migration/verify_trackers_82_90.py
```

Les détails sont documentés dans [`MIGRATION_PILOTE_70_71_80_81.md`](docs/MIGRATION_PILOTE_70_71_80_81.md), [`MIGRATION_REFERENCES_70_80_81.md`](docs/MIGRATION_REFERENCES_70_80_81.md), [`MIGRATION_JOURNAL_71.md`](docs/MIGRATION_JOURNAL_71.md), [`MIGRATION_TRACKERS_82_90.md`](docs/MIGRATION_TRACKERS_82_90.md) et [`SOURCE_INVENTORY.md`](docs/SOURCE_INVENTORY.md).

## Conformité d’architecture

Le contrôle exhaustif face au document initial, les corrections appliquées et les écarts conditionnels restants sont documentés dans [`docs/AUDIT_CONFORMITE_ARCHITECTURE.md`](docs/AUDIT_CONFORMITE_ARCHITECTURE.md). Les hooks produisent désormais l’enveloppe `SessionStart` compatible avec `additionalContext`; leur activation dans Claude Code reste une étape d’installation explicite.

## Adaptateurs d’oracles

Les neuf adaptateurs fermés — `difftest`, `transpilediff`, `stdcall_audit`, `winediff`, `winehash`, `ehdiff`, `gnuehdiff`, `funcdiff` et `cpudiff` — exécutent exclusivement les scripts ou la commande Cargo approuvés, capturent leurs sorties, produisent un artefact hashé et créent un proof HMAC lorsque le secret local est défini. `winehash` reste une mesure `UNKNOWN`, non promouvable. Leur usage et leurs prérequis sont détaillés dans [`docs/ADAPTATEURS_ORACLES.md`](docs/ADAPTATEURS_ORACLES.md) ; le contrat de sûreté est dans [`docs/CONTRAT_ORACLES.md`](docs/CONTRAT_ORACLES.md).

## Roadmap structurée V1.1

Les briques possèdent désormais un jalon (`milestone`), une plateforme cible (`target_platform`) et une priorité de 1 à 5. La roadmap reste une vue dérivée de SQLite : `aret_get_roadmap` retourne les briques, états, bloqueurs et relations actives sous une borne d’items ; `aret_export_roadmap` produit un Markdown hashé. Une brique affichée dans le Front doit rester `ACTIVE` ; `aret_update_brick` refuse de la désactiver tant que le Front n’a pas été remplacé.

```bash
# Vue compacte de la roadmap active
aret-mmu   # puis appeler aret_get_roadmap(milestone="M8") via le client MCP

# Bootstrap idempotent des métadonnées de la livraison actuelle
python3 migration/bootstrap_roadmap_v11.py --memory-dir .aret-memory
```

Les conventions et le contrat détaillé sont dans [`docs/MEMOIRE_STRATEGIQUE_CAPACITES_ET_ROADMAP.md`](docs/MEMOIRE_STRATEGIQUE_CAPACITES_ET_ROADMAP.md) et [`docs/ROADMAP_V1_1_IMPLEMENTEE.md`](docs/ROADMAP_V1_1_IMPLEMENTEE.md).

## Intégration opérationnelle

Les scripts `hooks/session_start.py`, `hooks/pre_compact.py` et `hooks/post_compact.py` injectent depuis SQLite le corpus complet 70/80/81/82/90, les huit dernières entrées 71, doctrine, Front, règles, audit, contexte Git et catalogue de pipelines. Les hooks `PreToolUse`, `PostToolUse` et `Stop` appliquent ensuite une barrière de reprise : Claude doit produire le récapitulatif rituel de ce contexte déjà injecté et le confirmer avec `aret_acknowledge_resume` avant toute action hors reprise. Aucune relecture documentaire MCP n’est imposée. Les opérations Git sont limitées au Memory Store ; une synchronisation automatique post-transaction reste opt-in (`auto_commit=false`, `auto_push=false` par défaut), bornée à `.aret-memory/` depuis la racine Git et précédée d’un checkpoint WAL. Les Memory Bundles v3 permettent un transport vérifié sans fusion implicite.

Le guide complet et les commandes reproductibles sont disponibles dans [`docs/INTEGRATION_OPERATIONNELLE.md`](docs/INTEGRATION_OPERATIONNELLE.md) et [`docs/CONTRATS_OPERATIONNELS.md`](docs/CONTRATS_OPERATIONNELS.md).

## Tests de non-régression

La suite vérifie notamment l’absence de promotion `PROVEN` sans reçu de preuve valide, la séparation FIND/READ, la borne de `READ_BATCH`, le versionnement append-first, l’audit, la reconstruction FTS5 et l’intégrité des artefacts.

```bash
pytest -q
python tests/mcp_integration_check.py
```

## Arborescence

```text
aret-memory/
├── .aret-memory/          # État durable local : SQLite, artefacts, exports
├── schema/                # Migrations SQLite versionnées
├── core/                  # Adressage, politiques et référentiel transactionnel
├── evidence/              # Reçus HMAC et adaptateurs d’oracles déterministes
├── cli/                   # Maintenance sans SQL arbitraire et bundles
├── hooks/                 # Reprise de session en lecture seule
├── ops/                   # Git borné au Memory Store et auto-sync opt-in
├── migration/             # Importeurs et vérificateurs documentaires idempotents
├── tests/                 # Tests unitaires, migrations et intégration MCP stdio
├── aret_mmu_server.py     # Façade MCP et point d’entrée
└── docs/                  # Contrat, inventaire et rapports de migration
```

## Références

[1]: https://py.sdk.modelcontextprotocol.io/ "MCP Python SDK — documentation officielle"

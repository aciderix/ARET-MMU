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
| Resume Dossier V1.2 | Playbook tagué enrichi, handoff atomique et checkpoint technique conditionnel hashé, avec contexte de reprise borné |

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
| Hooks de cycle de vie Claude Code | Disponible : Resume Dossier V1.2 contractuel injecté à `SessionStart` / `PostCompact`, puis barrière de reprise obligatoire |
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

Le fichier `.mcp.json` de projet lance `scripts/launch_aret_mcp.sh`. Ce lanceur crée idempotemment `aret-memory/.venv`, installe les dépendances déclarées par `pyproject.toml` si elles ne sont pas déjà synchronisées, puis remplace son processus par le serveur MCP. Toutes ses sorties techniques sont envoyées vers stderr ; stdout reste réservé au protocole stdio. Cette forme est adaptée aux conteneurs Claude Code éphémères comme aux postes locaux.

```json
{
  "mcpServers": {
    "aret-memory": {
      "command": "${CLAUDE_PROJECT_DIR}/aret-memory/scripts/launch_aret_mcp.sh",
      "args": [
        "--memory-dir",
        "${CLAUDE_PROJECT_DIR}/aret-memory/.aret-memory"
      ],
      "env": {
        "ARET_WRITE_ENABLED": "false"
      }
    }
  }
}
```

Le bootstrap Python automatique n’accorde aucun droit d’écriture. Sur un conteneur vierge, le premier démarrage nécessite un accès aux dépendances Python ou à leur cache ; les démarrages suivants réutilisent le venv tant que `pyproject.toml` n’a pas changé.

Après connexion, appelez `aret_boot`, puis `aret_get_front`. À `SessionStart` et `PostCompact`, les hooks injectent un **Resume Dossier V1.2** compact et contractuel : playbook stable à cinq domaines, fiches opérationnelles dérivées de méthode, gates et diagnostic ; handoff actif ; checkpoint technique ; cinq adresses chaudes au plus ; capacités/pipelines ; état Git ; et rituel. Le checkpoint est `NONE` lorsqu’aucun geste technique n’est réellement actif, ce qui interdit toute donnée inventée. Lorsqu’il est `ACTIVE`, il porte obligatoirement la cible, le dernier changement, l’état d’exécution, la dernière validation et les actions immédiates. Il ne relit ni n’injecte massivement les documents historiques. Produisez le récapitulatif rituel des six volets, puis appelez `aret_acknowledge_resume` avec l’empreinte `resume_contract_hash` affichée dans le dossier : les hooks refusent toute autre opération tant que cette confirmation du même contrat n’a pas réussi. Ne relisez les sources que pour un approfondissement ciblé sur une adresse. Utilisez ensuite `aret_find` pour obtenir une sélection de candidats et `aret_read` ou `aret_read_batch` pour lire les éléments dont les adresses ont été retenues. Un résultat de recherche ne doit jamais être traité comme une preuve.

| Outil | Usage |
|---|---|
| `aret_boot` | Lit doctrine, version du format, mode écriture et bornes. |
| `aret_get_front` | Récupère la mémoire chaude minimale. |
| `aret_restore` | Restitue le noyau de reprise : doctrine, versions et Active Front, sans historique massif. |
| `aret_get_resume_brief` / `aret_get_resume_protocol` | Restituent les pointeurs canoniques utiles à une investigation ciblée ; ils ne déclenchent aucune relecture obligatoire. |
| `aret_acknowledge_resume` | Confirme les six volets du rituel et le `resume_contract_hash` du dossier injecté après SessionStart ou PostCompact. |
| `aret_prepare_handoff` | Met à jour atomiquement le handoff, `last_action`, le checkpoint V1.2 et les curseurs d’observations V1.3 ; le playbook est préparé séparément par son bootstrap one-off. |
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

## Activation des hooks (barrière de reprise)

Le serveur MCP fournit les outils ; la **barrière de reprise** est portée par des hooks Claude Code déclarés dans le `.claude/settings.json` du dépôt. Leur activation est une étape d’installation explicite : à `SessionStart` et `PostCompact`, un hook injecte le Resume Dossier et arme la barrière ; à `PreToolUse`/`Stop`, la barrière exige le récapitulatif rituel ; à `PostToolUse` sur `aret_acknowledge_resume`, elle est levée.

```json
{
  "hooks": {
    "SessionStart": [{ "hooks": [{ "type": "command", "command": "$CLAUDE_PROJECT_DIR/.claude/hooks/aret-mmu-session-start.sh", "timeout": 10 }] }],
    "PreCompact":   [{ "hooks": [{ "type": "command", "command": "$CLAUDE_PROJECT_DIR/.claude/hooks/aret-mmu-pre-compact.sh",  "timeout": 10 }] }],
    "PostCompact":  [{ "hooks": [{ "type": "command", "command": "$CLAUDE_PROJECT_DIR/.claude/hooks/aret-mmu-post-compact.sh", "timeout": 10 }] }],
    "PreToolUse":   [{ "hooks": [{ "type": "command", "command": "$CLAUDE_PROJECT_DIR/.claude/hooks/aret-mmu-resume-pre-tool.sh", "timeout": 5 }] }],
    "Stop":         [{ "hooks": [{ "type": "command", "command": "$CLAUDE_PROJECT_DIR/.claude/hooks/aret-mmu-resume-stop.sh", "timeout": 5 }] }],
    "PostToolUse":  [{ "matcher": "mcp__aret-memory__aret_acknowledge_resume", "hooks": [{ "type": "command", "command": "$CLAUDE_PROJECT_DIR/.claude/hooks/aret-mmu-resume-post-tool.sh", "timeout": 5 }] }]
  }
}
```

Les entrypoints hooks (`hooks/*.py`) n’utilisent que la bibliothèque standard et des modules locaux : **aucun paquet tiers, aucun venv, aucun réseau** n’est requis pour qu’ils tournent. Il suffit de rendre le paquet importable. C’est essentiel en **session web/cloud** : dans un conteneur frais, le venv n’existe pas encore quand `SessionStart` se déclenche, donc un wrapper qui lance `python3` sans exposer le chemin du paquet échoue en silence (contexte non injecté, barrière non armée). Chaque wrapper source un helper commun qui exporte `PYTHONPATH` et préfère le venv s’il existe :

```bash
# .claude/hooks/aret-mmu-env.sh — à sourcer par chaque wrapper.
aret_mmu_dir="${CLAUDE_PROJECT_DIR:-$(pwd)}/aret-memory"
export ARET_MEMORY_DIR="${ARET_MEMORY_DIR:-${aret_mmu_dir}/.aret-memory}"
export PYTHONPATH="${aret_mmu_dir}${PYTHONPATH:+:${PYTHONPATH}}"   # import sans installation
if [ -x "${aret_mmu_dir}/.venv/bin/python" ]; then aret_mmu_python="${aret_mmu_dir}/.venv/bin/python"; else aret_mmu_python="python3"; fi
aret_mmu_exec() { exec "${aret_mmu_python}" "${aret_mmu_dir}/hooks/$1"; }
```

```bash
# .claude/hooks/aret-mmu-session-start.sh (les cinq autres wrappers sont identiques, à l'entrypoint près)
#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/aret-mmu-env.sh"
aret_mmu_exec session_start.py
```

### Session web/cloud (Claude Code on the web)

Le `.mcp.json` de projet et les hooks de `.claude/settings.json` **sont chargés en session cloud** car ils font partie du clone du dépôt — rien à installer côté client. Deux réglages d’environnement conditionnent le bon démarrage, à faire une fois sur `claude.ai/code` (icône d’environnement → réglages) :

- **Network access = `Trusted`** : le lanceur MCP fait un `pip install -e` au premier démarrage et a besoin d’atteindre PyPI. Avec `None`, la connexion du serveur MCP échoue. (Les hooks, eux, n’ont pas besoin du réseau.)
- **Environment variables** (format `.env`, visibles par les utilisateurs de l’environnement — préférez un environnement personnel pour un secret) :

| Variable | Rôle |
|---|---|
| `ARET_WRITE_ENABLED` | `true` pour autoriser l’écriture (défaut `false`, lecture seule). |
| `ARET_PROOF_HMAC_SECRET` | secret de signature des preuves `PROVEN` (à ne jamais communiquer au modèle). |
| `ARET_MMU_BARRIER_OFF` | **sortie de secours** de la barrière. `1`/`true`/`yes`/`on` = barrière **désactivée** ; absente ou `0` = barrière **active** (normal). À n’activer que pour se débloquer si l’acquittement MCP est indisponible. |

Pour fiabiliser/accélérer le premier démarrage, on peut pré-créer le venv via le **Setup script** de l’environnement (mis en cache) plutôt qu’au premier appel MCP :

```bash
cd "$CLAUDE_PROJECT_DIR/aret-memory" && python3 -m venv .venv && . .venv/bin/activate && pip install -e .
```

## Activation contrôlée des écritures

N’activez les écritures qu’après avoir validé les parcours de lecture et la politique de preuves. Le droit est lu au démarrage : une session MCP déjà connectée ne peut pas s’accorder elle-même ce privilège. Pour une session de travail, passez explicitement `ARET_WRITE_ENABLED` à `true` dans sa configuration MCP, puis redémarrez ou reconnectez le serveur et vérifiez `write_enabled: true` avec `aret_boot`.

```json
{
  "env": {
    "ARET_WRITE_ENABLED": "true"
  }
}
```

Le profil versionné reste à `false`. Le retour au mode lecture seule consiste à rétablir `false` puis redémarrer le serveur. Les outils `aret_register_component`, `aret_register_function`, `aret_register_brick`, `aret_append_knowledge`, `aret_update_front`, `aret_replace_front`, `aret_prepare_handoff`, `aret_rebuild_front`, `aret_record_proof`, `aret_attach_proof`, `aret_invalidate_proof`, `aret_add_relation` et `aret_rebuild_index` deviennent alors disponibles. Toute mutation se déroule dans une transaction SQLite et génère un événement d’audit. Il n’existe pas d’outil MCP de suppression ni de réécriture du contenu d’une connaissance.

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

# Une fois les sources historiques présentes : fiches opérationnelles compactes du Resume Dossier V1.1.
python3 migration/bootstrap_playbook_v11.py --memory-dir .aret-memory
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

## Gouvernance V1.4 : laboratoire, capacité officielle et mémoire

Lorsqu’une capacité ARET figure dans le catalogue MCP, l’agent l’emploie plutôt qu’un équivalent shell direct. Le shell reste autorisé pour compiler, explorer, diagnostiquer et prototyper, mais sa sortie ne devient ni un fait canonique ni une preuve. Après un fait durable, une décision, une preuve ou une préparation de reprise, l’agent met à jour uniquement l’objet mémoire métier concerné ; une recherche infructueuse ou une sortie provisoire ne justifie pas une écriture SQLite.

Un script local ne devient pas immédiatement un outil MCP. Son industrialisation devient obligatoire lorsqu’il est réutilisable ou contribue de manière récurrente à une décision, une validation, une preuve, un corpus, un asset ou une mesure de priorisation. Une capacité officielle doit alors disposer d’un catalogue fermé, de paramètres bornés, d’une politique, d’un résultat ou artefact adressable lorsque requis, de tests et d’une documentation compacte. Cette gouvernance n’ajoute ni table, ni outil, ni whitelist de barrière ; `auto_push=false` demeure inchangé.

## Intégration opérationnelle

Les scripts `hooks/session_start.py`, `hooks/pre_compact.py` et `hooks/post_compact.py` organisent le cycle de reprise. `SessionStart` et `PostCompact` exigent un Resume Dossier V1.3 prêt : cinq domaines de playbook `CORE_PLAYBOOK` couvrant fondation, méthode, architecture shared-stack, portes et outillage ; trois fiches opérationnelles dérivées compactes ; un handoff Front préparé atomiquement ; un checkpoint technique V1.2 ; et une fenêtre V1.3 de faits MCP déjà persistés. `technical_checkpoint_state=NONE` représente explicitement l’absence de geste en cours et impose les cinq champs techniques vides. `ACTIVE` exige les cinq faits bornés : cible, changement, état d’exécution, dernière validation et actions immédiates. La macro met simultanément à jour `last_action`, le checkpoint, le hash du Front et deux curseurs qui délimitent les observations postérieures au handoff. Les observations affichent au plus trois `pipeline_run` ou preuves adressables avec verdict, hash d’artefact et paramètres bornés ; elles ne peuvent jamais décrire l’intention de Claude, un correctif ou une prochaine action. Une dernière validation qui référence un pipeline ou une preuve est vérifiée contre son verdict stocké ; sans adresse, elle reste déclarée et non vérifiée. Une ancienne préparation sans état V1.2 ou sans curseurs V1.3 est refusée jusqu’à ce qu’un handoff factuel soit fourni. Le script `migration/bootstrap_playbook_v11.py` crée les fiches dérivées et leurs relations `DERIVED_FROM` de façon idempotente ; il n’est jamais exécuté par `aret_prepare_handoff`, les hooks ou le chemin de routine. Aucune migration ne crée rétroactivement un checkpoint ou une frontière d’observations. Le dossier seul est refusé au-delà de 12 500 octets, le contexte final au-delà de 18 500 octets, sans troncature silencieuse. Les hooks `PreToolUse`, `PostToolUse` et `Stop` appliquent ensuite une barrière : les six sections du récapitulatif et le hash contractuel injecté, qui inclut l’instantané V1.3, doivent être confirmés par `aret_acknowledge_resume` avant toute autre opération. Les opérations Git sont limitées au Memory Store ; une synchronisation automatique post-transaction reste opt-in (`auto_commit=false`, `auto_push=false` par défaut), bornée à `.aret-memory/` depuis la racine Git et précédée d’un checkpoint WAL. Les Memory Bundles v3 permettent un transport vérifié sans fusion implicite.

Le guide complet et les commandes reproductibles sont disponibles dans [`docs/INTEGRATION_OPERATIONNELLE.md`](docs/INTEGRATION_OPERATIONNELLE.md) et [`docs/CONTRATS_OPERATIONNELS.md`](docs/CONTRATS_OPERATIONNELS.md).

## Tests de non-régression

La suite vérifie notamment l’absence de promotion `PROVEN` sans reçu de preuve valide, la séparation FIND/READ, la borne de `READ_BATCH`, le versionnement append-first, l’audit, la reconstruction FTS5, l’intégrité des artefacts, le playbook à cinq domaines, le bootstrap V1.1 idempotent, ses relations de provenance, les règles opérationnelles injectées, le checkpoint V1.2 `NONE` et `ACTIVE`, ses bornes, son atomicité avec `last_action`, les observations V1.3 après curseur, la vérification fail-closed d’un verdict référencé, la règle V1.4 priorisant trois capacités ARET cataloguées via MCP et le blocage de reprise tant que le hash contractuel ne correspond pas.

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

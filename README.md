# ARET-MMU

**ARET Memory Management Unit** est le serveur MCP de mémoire persistante, structurée, adressable et probatoire conçu pour le projet ARET (*Automatic Reverse Engineering Toolkit*).

> Ce dépôt contient uniquement **ARET-MMU** : le serveur MCP, le Memory Store SQLite, les migrations, les tests, les documents, les adaptateurs d’oracle et les hooks Claude Code. Le code, les corpus et les documents métier d’ARET restent dans leur dépôt principal séparé.

## Ce que fournit ARET-MMU

| Capacité | Fonctionnement |
|---|---|
| Mémoire canonique | SQLite WAL avec FTS5, migrations hashées, audit et adressage `ARET://`. |
| Discipline épistémique | Distinction stricte entre recherche (`FIND`), lecture exacte (`READ`), hypothèse, observation et preuve `PROVEN`. |
| Evidence Store | Preuves signées HMAC, artefacts hashés, invalidation et promotion contrôlée. |
| Graphe | Relations typées, cycle de vie `ACTIVE` / `SUPERSEDED`, traversée historique opt-in. |
| Roadmap V1.1 | Briques classées par jalon, plateforme et priorité ; vue et export de roadmap dérivés. |
| Reprise Claude Code | Contexte complet à `SessionStart` / `PostCompact`, puis barrière obligatoire de lecture contrôlée par `PreToolUse`, `PostToolUse` et `Stop`. |
| Pipelines et corpus | 27 pipelines nommés et fermés, politiques explicites, plan `dry_run` et artefacts hashés. |
| Portabilité | Bundle v3 vérifié et synchronisation Git bornée exclusivement au Memory Store. |

Le serveur expose **41 outils MCP**. Son contrat détaillé est disponible dans [`aret-memory/docs/CONTRAT_MCP_V1.md`](aret-memory/docs/CONTRAT_MCP_V1.md).

## Installation locale

```bash
git clone https://github.com/<votre-compte>/ARET-MMU.git
cd ARET-MMU/aret-memory
python3 -m pip install 'mcp[cli]>=2.0.0'
python3 aret_mmu_server.py
```

Le serveur démarre en lecture seule. Pour autoriser une session de travail à persister des découvertes ou des preuves :

```bash
export ARET_WRITE_ENABLED=true
export ARET_PROOF_HMAC_SECRET='clé-locale-longue-et-non-versionnée'
python3 aret_mmu_server.py
```

Ne publiez jamais une vraie clé HMAC, un jeton GitHub, un fichier `.env` ou un journal SQLite WAL/SHM.

## Configuration Claude Code

Les hooks spécifiques à ARET-MMU sont fournis dans `.claude/`. Ils fonctionnent lorsque le dépôt est ouvert comme projet Claude Code. À chaque `SessionStart` ou `PostCompact`, le contexte injecte automatiquement depuis SQLite doctrine, Front, extraits des règles, roadmap, journal 71, audit, Git, assets, outils MCP et catalogue de pipelines. Les documents source étant déjà ingérés, Claude ne les relit pas par défaut. Il produit le récapitulatif rituel de ce contexte, puis appelle `aret_acknowledge_resume`. Tant que cette confirmation n’a pas réussi, les opérations de poursuite sont refusées et une tentative de fin reçoit une relance unique.

La configuration du serveur MCP doit faire pointer Claude Code vers :

```json
{
  "mcpServers": {
    "aret-memory": {
      "command": "python3",
      "args": ["/chemin/absolu/vers/ARET-MMU/aret-memory/aret_mmu_server.py"],
      "env": {"ARET_WRITE_ENABLED": "true"}
    }
  }
}
```

## Roadmap V1.1

La livraison contient la migration `005_roadmap_bricks.sql`, les outils `aret_get_roadmap`, `aret_update_brick` et `aret_export_roadmap`, ainsi qu’un bootstrap idempotent du classement initial. Le guide complet est dans [`aret-memory/docs/ROADMAP_V1_1_IMPLEMENTEE.md`](aret-memory/docs/ROADMAP_V1_1_IMPLEMENTEE.md).

## Validation

```bash
cd aret-memory
pytest -q
python3 tests/mcp_integration_check.py
python3 -m compileall -q aret_mmu_server.py core evidence hooks migration ops cli
```

La livraison validée contient **49 tests** et le contrôle stdio vérifie les **42 outils** attendus. La suite est exécutable dans le clone MCP isolé ; les tests qui requièrent explicitement un dépôt ARET source restent signalés `skipped` lorsque ce chemin n’est pas configuré.

Pour exécuter les tests qui nécessitent explicitement un dépôt ARET source, clonez ARET séparément et indiquez son chemin :

```bash
ARET_SOURCE_REPOSITORY=/chemin/vers/Automatic-reverse-engineering-toolkit \
  pytest -q
```

Les importeurs de documents acceptent également `--repository-root /chemin/vers/ARET` lors d’une migration réelle.

## Documentation essentielle

| Document | Objet |
|---|---|
| [`aret-memory/README.md`](aret-memory/README.md) | Installation et opérations du Memory Store. |
| [`aret-memory/docs/GUIDE_VULGARISE_FONCTIONNEMENT_ARET_MMU.md`](aret-memory/docs/GUIDE_VULGARISE_FONCTIONNEMENT_ARET_MMU.md) | Explication fonctionnelle complète et accessible. |
| [`aret-memory/docs/MATRICE_CONFORMITE_V5_FINALE_2026-08-19.md`](aret-memory/docs/MATRICE_CONFORMITE_V5_FINALE_2026-08-19.md) | Matrice de conformité architecturale V5. |
| [`aret-memory/docs/MEMOIRE_STRATEGIQUE_CAPACITES_ET_ROADMAP.md`](aret-memory/docs/MEMOIRE_STRATEGIQUE_CAPACITES_ET_ROADMAP.md) | Gestion des capacités, décisions et objectifs à long terme. |
| [`aret-memory/docs/STATUT_DOCUMENT_91.md`](aret-memory/docs/STATUT_DOCUMENT_91.md) | Décision de non-import de la synthèse 91, redondante des sources déjà migrées. |
| [`aret-memory/docs/CONTRATS_OPERATIONNELS.md`](aret-memory/docs/CONTRATS_OPERATIONNELS.md) | Hooks, barrière de reprise, bundles et synchronisation Git bornée. |
| [`aret-memory/docs/PIPELINES_ARET_V1.md`](aret-memory/docs/PIPELINES_ARET_V1.md) | Catalogue fermé des pipelines, politiques d’exécution et artefacts. |

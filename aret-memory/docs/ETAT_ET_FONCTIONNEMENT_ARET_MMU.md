# ARET-MMU — État et fonctionnement (référence)

> Document de référence du serveur MCP de mémoire d'ARET. Écrit à partir du code
> réel (`aret-memory/`), pas de mémoire. Complète le `GUIDE_VULGARISE_…` (pédagogie)
> et le `CONTRAT_MCP_V1.md` (contrat outil par outil).

## 1. But

ARET-MMU est le **serveur MCP de mémoire persistante et de contrôle du travail** de
l'agent sur ARET (transpilateur statique Win32 → Linux). Il remplace le *rituel de
relecture manuelle des documents après compaction* par une reprise **déterministe,
bornée et vérifiée** : le contexte critique est réinjecté depuis une source
canonique (SQLite), et une **barrière de reprise** exige un récapitulatif structuré
avant toute action de poursuite. Objectif : plus aucune reprise « à l'aveugle », plus
aucun faux succès silencieux, discipline FIND→READ et soundness PROVEN.

## 2. Architecture — 4 piliers

1. **Mémoire vivante — SQLite** (`core/repository.py`, `schema/00*.sql`,
   `.aret-memory/aret_memory.sqlite`). Graphe versionné : composants, fonctions,
   briques, connaissances (RULE/ARCHITECTURE/…), Front, handoff, roadmap, relations,
   assets, journaux d'audit. Statuts de cycle de vie : `ACTIVE, PROVEN, OBSERVED,
   HYPOTHESIS, SUPERSEDED`. C'est la **source canonique** de la reprise.

2. **Lois autorées — `config/playbook.md`** (fichier empaqueté, chargé **directement**,
   pas régénéré depuis SQLite). Les règles de travail stables d'ARET (le playbook) sont
   **toujours autoritatives** et injectées à chaque reprise, y compris en mode dégradé.

3. **Evidence store — preuves HMAC** (`evidence/capture.py`, `evidence/adapters/`).
   Toute preuve d'oracle est signée `HMAC-SHA256` (secret `ARET_PROOF_HMAC_SECRET`,
   requis pour signer). Un `receipt_hmac` + un hash de charge rendent la preuve
   admissible et infalsifiable. Une connaissance ne passe `PROVEN` qu'avec une preuve
   admissible (PASS) — un score n'est jamais une preuve.

4. **Barrière de reprise — hooks** (`hooks/`). Hooks Claude Code : `SessionStart`,
   `PreCompact`, `PostCompact`, `PreToolUse`, `Stop`, `PostToolUse`. Ils injectent le
   dossier de reprise et **arment la garde** ; `resume_guard.py` en est le cœur
   déterministe. État local/éphémère sous `.aret-memory/runtime/resume_guard/`, jamais
   dans SQLite ni Git.

## 3. Flux de reprise

1. **SessionStart / PostCompact** (`hooks/session_start.py`, `hooks/post_compact.py`) :
   construisent le dossier via `resume_context_or_degraded(store)` — qui **ne lève
   jamais** : mémoire complète ⇒ dossier `ready`, mémoire incomplète/illisible ⇒
   dossier **DÉGRADÉ** (avec un `contract_hash` valide et le contexte bruyant). Puis
   `arm(..., ready=not degraded)` arme la barrière et le contexte est injecté.
2. **Rituel obligatoire** : produire un récapitulatif fidèle des **6 volets** (§4),
   puis appeler l'outil MCP `aret_acknowledge_resume` avec les 6 champs + le
   `resume_contract_hash` du dossier réellement injecté.
3. **PreToolUse** (`resume_guard.decision`) : en **mode dur** (dossier prêt), refuse
   toute action tant que l'acquittement n'est pas fait ; laisse passer l'appel
   d'acquittement lui-même. **Stop** (`resume_guard.stop_feedback`) pousse une unique
   continuation si l'agent tente de conclure sans récapitulatif.
4. **PostToolUse** sur `aret_acknowledge_resume` : lève la garde après un
   acquittement **complet et réussi** (6 volets non triviaux + hash concordant +
   réponse MCP `ok`).

### Modes de la barrière (leçon du deadlock — voir §9)

- **`hard`** (dossier prêt) : blocage dur jusqu'à acquittement. L'acquittement est
  alors sémantiquement possible.
- **`soft`** (dossier DÉGRADÉ / non prêt) : la barrière **est armée** (fail-loud : état
  présent, contexte bruyant injecté, nudge Stop actif) mais **ne bloque PAS dur** en
  PreToolUse. Sur une mémoire cassée, imposer un rituel rigide sans voie de sortie
  fiable = deadlock.
- **Kill-switch d'exploitation** : `ARET_MMU_BARRIER_OFF=1` (`0/false/off` = inactif)
  lève PreToolUse **et** Stop sans éditer de code — voie de sortie toujours disponible,
  même en mode dur si le serveur MCP d'acquittement n'est pas connecté.

## 4. Dossier de reprise — les 6 volets

`resume_guard.RITUAL_FIELDS` (nom, exigence, longueur min.) :

| Champ | Contenu | Min. |
|---|---|---|
| `working_rules` | règles de travail incontournables | 80 |
| `current_state` | état courant, Front et objectifs (décrire l'état DÉGRADÉ si applicable) | 60 |
| `capabilities` | outils MCP, analyse, industrialisation, pipelines | 80 |
| `git_state` | branche, commits, état Git | 40 |
| `risks_and_limits` | limites, preuves, garde-fous | 60 |
| `next_action` | prochaine action atomique proposée | 30 |

La validation est **déterministe** (présence + longueur non triviale) ; la véracité
sémantique relève de l'agent.

## 5. Capacités — 43 outils MCP

Regroupés (voir `aret_mmu_server.py` et `CONTRAT_MCP_V1.md` pour signatures) :

- **Reprise / boot** : `aret_boot`, `aret_restore`, `aret_get_front`,
  `aret_get_resume_brief`, `aret_get_resume_protocol`, `aret_acknowledge_resume`.
- **Découverte / lecture** (discipline FIND→READ) : `aret_find`, `aret_read`,
  `aret_read_batch`, `aret_get_forensics`, `aret_get_proofs`, `aret_get_related`,
  `aret_get_roadmap`, `aret_read_artifact`.
- **Écriture mémoire** : `aret_append_knowledge`, `aret_update_front`,
  `aret_replace_front`, `aret_prepare_handoff`, `aret_rebuild_front`,
  `aret_record_proof`, `aret_add_relation`, `aret_supersede_relation`.
- **Graphe** : `aret_register_component`, `aret_register_function`,
  `aret_register_brick`, `aret_update_brick`, `aret_attach_proof`,
  `aret_invalidate_proof`.
- **Oracles / pipelines** : `aret_run_oracle`, `aret_get_pipeline_catalog`,
  `aret_get_toolchain_status`, `aret_run_pipeline`, `aret_get_pipeline_runs`,
  `aret_read_pipeline_artifact`.
- **Assets** : `aret_get_assets`, `aret_register_asset`.
- **Maintenance / export** : `aret_sync_memory`, `aret_rebuild_index`,
  `aret_export_roadmap`, `aret_export`, `aret_export_bundle`, `aret_import_bundle`.

## 6. Soundness — PROVEN + HMAC

- **Écriture désactivée par défaut** : `.mcp.json` fixe `ARET_WRITE_ENABLED=false` ;
  la mémoire est lecture seule tant que l'écriture n'est pas explicitement activée
  (`--write-enabled` / env). Aucun SQL ni shell arbitraire n'est exposé.
- **PROVEN exige une preuve admissible** : signature HMAC de l'oracle, hash de charge,
  réponse PASS. Un score de heuristique ≠ preuve.
- **§0 correct ou arrêt bruyant** : `resume_context_or_degraded` n'échoue jamais en
  silence ; un dossier illisible devient un dossier DÉGRADÉ bruyant.

## 7. Migration vs Doctor (deux portes distinctes)

- **Migration** (`migration/`) : import **initial** et vérifié des sources historiques
  vers SQLite (journal 71, références 70/80/81, pilotes, trackers 82/90, doc 91,
  playbook v1.1, roadmap). Les `verify_*.py` sont **drift-proof** (pas de comptage
  d'entrées figé). Opération ponctuelle de peuplement/re-baseline.
- **Doctor** (`cli/aret_memory.py doctor` → `MemoryStore.health_report`) : **porte
  permanente** de cohérence INTERNE de la mémoire (DB-primary). `exit ≠ 0` si malsain.
  À exécuter régulièrement, pas seulement à l'import.

## 8. Configuration

- **`.mcp.json`** (racine ARET) : serveur `aret-memory` →
  `aret-memory/scripts/launch_aret_mcp.sh --memory-dir aret-memory/.aret-memory`,
  `env.ARET_WRITE_ENABLED=false`. Le launch script est idempotent (venv + `pip -e`
  restaurés au besoin ; stdout réservé au stdio MCP, logs sur stderr).
- **`.claude/settings.json`** : hooks `SessionStart`, `PreCompact`, `PostCompact`
  (injection contexte), `PreToolUse`/`Stop` (barrière), `PostToolUse` matché sur
  `mcp__aret-memory__aret_acknowledge_resume` (levée de garde).
- **Variables d'environnement** :
  - `ARET_MEMORY_DIR` — répertoire mémoire (`aret-memory/.aret-memory`).
  - `ARET_WRITE_ENABLED` — `true` pour autoriser l'écriture (défaut `false`).
  - `ARET_PROOF_HMAC_SECRET` — secret requis pour signer une preuve.
  - `ARET_MMU_BARRIER_OFF` — kill-switch d'exploitation de la barrière (§3).

## 9. Historique des incréments de durcissement

| Commit | Objet |
|---|---|
| `49b3294` | playbook = **fichier** `config/playbook.md` (lois autorées chargées direct). |
| `dee14be` | **armement fail-loud** : une mémoire cassée n'éteint plus la barrière en silence. |
| `6d3d19f` | **vérificateurs drift-proof** (plus de `378` figé). |
| `61c8cf4` | **doctor** `health_report` + CLI `doctor` (porte de cohérence interne). |
| `a87fa11` | **re-baseline** de la DB committée (381 entrées journal, vérifiée). |
| *(ce cycle)* | **barrière anti-deadlock** : mode `soft` en dégradé + kill-switch `ARET_MMU_BARRIER_OFF` ; `arm(ready)` ; tests de reproduction du deadlock. |

## 10. Leçon du deadlock (à graver)

Une barrière ne doit **jamais** pouvoir s'armer sans **voie de sortie disponible**.
Le fail-loud (contexte bruyant, nudge) est bon ; le **blocage dur** ne doit s'appliquer
que quand l'acquittement est **réellement possible** — dossier prêt **et** mécanisme
d'acquittement présent. Sinon : deadlock (vécu en live — barrière armée en dossier
non-prêt alors que l'outil MCP d'acquittement était injoignable). Défenses en place :

1. **Mode `soft`** en reprise dégradée → jamais de blocage dur sur mémoire cassée.
2. **Kill-switch** `ARET_MMU_BARRIER_OFF` → l'opérateur lève toujours la garde, même en
   mode dur si le serveur MCP n'est pas connecté.

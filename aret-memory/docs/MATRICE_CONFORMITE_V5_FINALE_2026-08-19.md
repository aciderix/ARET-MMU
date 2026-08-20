# Matrice finale de conformité ARET-MMU — Architecture V5

**Date de contrôle :** 19 août 2026
**Base examinée :** `aret-memory/.aret-memory/aret_memory.sqlite`
**Révision source de référence :** `232a6ebf1d27514a1f8a401966dbb3756ff51a8a` complétée par la livraison ARET-MMU actuellement non committée.
**Méthode :** lecture de la spécification V5 fournie, contrôle du code et des migrations, exécution de la suite de tests, contrôle MCP stdio exhaustif, compilation Python et snapshot SQLite lecture seule.

> **Verdict strict.** Le MCP ARET-MMU est **conforme aux exigences architecturales V5 implémentables**. Les mécanismes centraux — SQLite canonique, séparation FIND/READ, Active Front, Evidence Store HMAC, écritures append-first, audit, relations versionnées, hooks, Git borné, bundle portable et migration hybride — sont présents, contrôlés et testés. Le document Markdown 91 n’est pas ingéré comme doublon brut : la V5 prescrit une **vue 91 reconstruite** depuis les objets structurés, capacité effectivement livrée. [1]

Ce verdict ne prétend pas que l’état livré contient déjà des preuves d’exécution réelles de tous les oracles : le snapshot comporte zéro preuve parce que les dépendances de benchmark ne sont pas disponibles dans l’environnement de livraison. Il s’agit d’un **pré-requis d’exploitation**, non d’un écart de conception ou d’implémentation : la chaîne de création, HMAC, rattachement, promotion et invalidation de preuves est implémentée et testée. [2] [3]

## 1. Résultats de validation exécutés

| Contrôle | Résultat | Verdict |
|---|---|---|
| Suite Python | `38 passed in 3.45s` | Conforme |
| Transport MCP stdio | Inventaire exact de 32 outils et `aret_boot` opérationnel | Conforme |
| Compilation statique | `compileall` réussi sur serveur, cœur, preuves, hooks, migrations, opérations et CLI | Conforme |
| Migrations SQLite | Versions 1 à 5 présentes avec checksums SHA-256 | Conforme |
| Contrôle documentaire | Aucune mention V2 ou catalogue obsolète dans README et documents contrôlés | Conforme |
| Snapshot final | 514 connaissances sourcées, 9 fonctions, 10 briques, 35 relations, Front réel | Conforme |

## 2. Matrice de conformité V5

| Domaine V5 | Exigence vérifiée | Mise en œuvre constatée | État |
|---|---|---|---|
| Source canonique | SQLite est autoritatif ; les vues et index sont dérivés. | `MemoryStore`, SQLite WAL, FTS5 reconstructible, exports dérivés. | **Conforme** |
| Schéma et intégrité | Entités knowledge, component, function, brick, proof, relation, Front, audit et tags. | Tables `STRICT`, clés étrangères, index, séquences déterministes et 5 migrations hashées. | **Conforme** |
| Types épistémiques | Neuf catégories de connaissances et sept statuts. | Ensembles validés par le référentiel et contraintes SQL. | **Conforme** |
| `PROVEN` | Exige une preuve liée, `PASS` et admissible. | Vérification serveur + triggers SQLite à l’insertion et à la promotion. | **Conforme** |
| Append-first | Pas de réécriture sémantique silencieuse. | Trigger anti-réécriture, versions, `supersedes_id`, relation `SUPERSEDES` et audit. | **Conforme** |
| Graphe | Relations explicites, historisées et traversables. | 35 relations ; migration 004 ajoute `ACTIVE` / `SUPERSEDED` et `superseded_by`; historique opt-in. | **Conforme** |
| Roadmap structurée | Objectifs, chantiers et dépendances distingués de la capacité démontrée. | Migration 005, briques classées par jalon, cible et priorité ; lecture, mise à jour et export roadmap métier. | **Conforme** |
| Adressage | `ARET://<type>/<id>` et lecture exacte. | `knowledge`, `component`, `function`, `brick`, `proof`, `relation`, `front/current`; `aret_read` valide et lit chaque type. | **Conforme** |
| FIND ≠ READ | Découverte structurée/FTS distincte de la lecture de contenu. | `aret_find` sans contenu intégral ; `aret_read` / `aret_read_batch` adressés. | **Conforme** |
| Pagination | `READ_BATCH` borné en objets et octets, sans dépassement silencieux. | Défaut 20/65 536, plafond 100/262 144 ; refus explicite. | **Conforme** |
| Active Front | Cache chaud minimal, corrigeable et reconstructible. | `get_front`, `update_front`, `replace_front`, `rebuild_front`; audit avant/après. | **Conforme** |
| Evidence Store | Preuves hors récit, artefacts lourds hors SQLite et hashés. | Artefacts sous `artifacts/`, SHA-256 relu, HMAC, métadonnées et lecture explicite bornée. | **Conforme** |
| Oracles | Gates déterministes sans commande arbitraire. | 9 entrées fermées : difftest, transpilediff, stdcall_audit, winediff, winehash, ehdiff, gnuehdiff, funcdiff, cpudiff. | **Conforme** |
| `winehash` | Mesure distincte d’un gate de conformité. | Normalisé `UNKNOWN`, jamais promouvable vers `PROVEN`. | **Conforme** |
| Mutations | Écriture contrôlée, transactionnelle et auditée. | Mode lecture seule par défaut, `BEGIN IMMEDIATE`, validations, `_audit`. | **Conforme** |
| Audit | Toute mutation importante est explicable. | 1 126 événements observés ; acteurs, opérations, avant/après canoniques. | **Conforme** |
| Reconstruction | FTS régénérable sans LLM. | `aret_rebuild_index`, tests de suppression/reconstruction. | **Conforme** |
| Bundle | Snapshot portable, hash logique, migrations et artefacts vérifiés. | Bundle v3 avec manifest, migrations SHA-256, source device, idempotence et non-fusion. | **Conforme** |
| Transfert | Refus du merge de deux SQLite vivantes. | Import réservé à une cible vide ; import idempotent d’un même hash. | **Conforme** |
| Git | Périmètre strict `.aret-memory/**`, après transaction SQLite. | Auto-sync opt-in après commit SQLite, checkpoint WAL, root Git réel, refus hors périmètre. | **Conforme** |
| Politique Git | `auto_push=false` disponible pour développement local. | Politique livrée : `auto_commit=false`, `auto_push=false`. | **Conforme** |
| Hooks | SessionStart injecte le contexte ; Pre/PostCompact tracent sans dépendre du LLM. | Trois hooks installés ; `additionalContext` SessionStart ; checkpoints d’écriture opt-in. | **Conforme** |
| Migration hybride | Texte exact, provenance, hash, lots idempotents et vue 91 reconstruite. | 514 sources, 4 lots, importeurs 70/71/80/81/82/90 et `aret_export_reference_91`. | **Conforme** |
| Exports humains | JSON, Markdown, HTML comme vues, non comme source. | Exports déterministes, HTML échappé, bundle v3. | **Conforme** |
| Sécurité | Pas de SQL libre ni de shell libre. | Façade métier typée ; commandes d’oracle et Git bornées. | **Conforme** |

## 3. État réel du Memory Store livré

| Élément | Valeur observée | Lecture de conformité |
|---|---:|---|
| Migrations | 5 | Les cycles de vie relationnel et roadmap sont appliqués. |
| Composants | 17 | Sous-systèmes structurants initialisés. |
| Connaissances | 514 | Toutes portent une provenance documentaire structurée. |
| Sources de connaissance | 514 | Aucune connaissance migrée sans trace de source. |
| Fonctions | 9 | Symboles EH/CRT/Win32 et WinMerge récurrents adressables. |
| Briques | 10 | `M7-GUI`, `AUTO-LIFT-02`, FIBERS 01–05 et PHASE A–C, toutes classées par jalon, cible et priorité. |
| Relations | 35 | 34 `CONCERNS`, 1 `SUPERSEDES`; statut actuel `ACTIVE`. |
| Preuves | 0 | Capacité prête ; aucun benchmark probatoire n’a été exécuté dans cet environnement. |
| Événements d’audit | 1 126 | Historique des imports, bootstrap, Front et mutations. |

Le Front actif ne pointe plus vers une migration de mémoire. Il référence le sous-système **« DLL tierces C++ / Lifting »**, la brique **`AUTO-LIFT-02`**, le mur courant de lifting de DLL applicatives et cinq pages canoniques pertinentes. [4]

## 4. Qualification du document 91

La V5 ne demande pas qu’un Markdown 91 soit maintenu comme deuxième source canonique. La table de migration V5 définit le document 91 comme une **vue reconstruite automatiquement depuis `STATE`, `RULE`, `MEASUREMENT`, `BRICK` et `DECISION`**. [1]

`aret_export_reference_91` met en œuvre cette vue depuis SQLite. Le contrôleur `migration/import_doc91.py` retourne désormais `NOT_APPLICABLE` : le document 91 est confirmé comme une synthèse redondante des sources déjà migrées, non comme une provenance à archiver ou comparer. Cette décision évite de dupliquer les 514 connaissances historiques.

## 5. Écarts non bloquants et prérequis d’exploitation

| Sujet | Statut | Justification |
|---|---|---|
| Exécution réelle des neuf oracles | Pré-requis d’environnement | Wine, MinGW, Clang/LLVM, Cargo, Unicorn, corpus et binaire ARET doivent être disponibles. Le système enregistre alors une preuve ; sinon il renvoie `SKIPPED`. |
| Preuves dans le snapshot livré | Aucune preuve initiale | Aucun `PROVEN` n’est prétendu ; cela préserve l’exigence anti-hallucination. |
| UI de graphe/timeline | Évolution future V5 | La V5 la qualifie d’éventuelle et non d’exigence de V1. |
| CLI de visualisation enrichie | Partiellement souhaitable | Le CLI de maintenance est présent ; une UI/CLI exhaustive n’est pas un critère bloquant selon la section export/interface humaine. |
| Synthèse Markdown 91 | Non applicable | Elle est redondante des sources déjà migrées ; la vue 91 dérivée demeure disponible à titre de compatibilité. |

## 6. Contrôles indépendants recommandés

Un vérificateur peut reproduire l’essentiel de ce verdict depuis `aret-memory/` :

```bash
pytest -q
python3 tests/mcp_integration_check.py
python3 -m compileall -q aret_mmu_server.py core evidence hooks migration ops cli
cat docs/verification/runtime_snapshot_roadmap_v11_final.json
```

La production de premières preuves réelles doit ensuite être réalisée dans un environnement de benchmark complet, avec `ARET_WRITE_ENABLED=true` et un `ARET_PROOF_HMAC_SECRET` long et secret. Les preuves créées pourront alors être liées aux connaissances concernées et permettre la promotion contrôlée vers `PROVEN`.

## 7. Verdict final

La conclusion de Gemini est **confirmée sous une formulation techniquement précise** : la **complétude fonctionnelle V5** est atteinte et l’extension roadmap V1.1 est désormais intégrée. Aucun écart bloquant n’a été identifié lors de cette dernière passe. Les seules actions restantes sont opérationnelles — mise à disposition des dépendances d’oracle, définition du secret HMAC et commit initial de la livraison — et ne correspondent pas à des fonctionnalités absentes du MCP.

## Références

[1]: architecture/ARET-MMU_Architecture_Document_Definitif_v5_final.md "Architecture ARET-MMU V5, sections 7 à 27"
[2]: ../evidence/adapters/oracles.py "Catalogue, capture et normalisation des oracles"
[3]: ../tests/test_oracle_adapters.py "Promotion, HMAC, FAIL et SKIPPED"
[4]: verification/runtime_snapshot_roadmap_v11_final.json "Snapshot SQLite final en lecture seule avec roadmap V1.1"
[5]: ../core/repository.py "Transactions, preuve, relations, exports, bundles et audit"
[6]: ../ops/git_memory.py "Confinement Git et checkpoint WAL"
[7]: ../hooks/session_start.py "Restauration SessionStart et additionalContext"
[8]: ../tests/mcp_integration_check.py "Contrôle stdio exact de 32 outils"
[9]: ../schema/005_roadmap_bricks.sql "Métadonnées roadmap V1.1"
[10]: ../migration/bootstrap_roadmap_v11.py "Classement idempotent des briques"

# Rapport de correction de l’audit externe ARET-MMU

**Date :** 19 août 2026
**Périmètre historique :** tous les constats de l’audit externe, avec une hypothèse alors formulée sur le document 91. **Addendum du 20 août 2026 :** cette hypothèse est invalidée ; le document 91 est une synthèse redondante et non une source à importer.
**Révision source de référence :** `232a6ebf1d27514a1f8a401966dbb3756ff51a8a`.

## Synthèse de qualification

| Constat | Qualification | Traitement |
|---|---|---|
| M1 — Document 91 absent | Requalifié non applicable | Il s’agit d’une synthèse redondante des sources déjà migrées ; aucun import ne doit être exécuté. |
| M2 — Graphe initial vide | Confirmé | Bootstrap déterministe ajouté et appliqué. |
| M3 — Active Front de migration | Confirmé | Front d’ingénierie réinitialisé de manière auditée. |
| M4 — `ARET://relation/...` non lisible | Confirmé | Schéma d’adressage et lecture exacte corrigés. |
| M5 — WAL avant Git/bundles | Confirmé pour le checkpoint ; `.gitignore` déjà conforme | Checkpoint `TRUNCATE` ajouté avant bundle et commits mémoire. |
| M6 — Documentation en retard | Confirmé | Trois documents de contrat/usage réalignés. |

## Correctifs livrés

### M2 — Graphe initial contrôlé

Le module `migration/bootstrap_initial_graph.py` a été ajouté. Il est **idempotent** et n’utilise ni modèle génératif ni similarité sémantique : une relation `CONCERNS` n’est créée que depuis une connaissance `FORENSIC` qui contient une mention littérale du symbole correspondant.

Les sept symboles enregistrés sont :

| Fonction adressable | Composant | Module |
|---|---|---|
| `EH:msvcrt!__except_handler3` | `EH` | `msvcrt` |
| `EH:msvcrt!_except_handler4_common` | `EH` | `msvcrt` |
| `EH:msvcrt!_EH_prolog3_GS` | `EH` | `msvcrt` |
| `HLE:user32!GetSysColor` | `HLE` | `user32` |
| `HLE:msvcrt!wcscat_s` | `HLE` | `msvcrt` |
| `X87:msvcrt!_ftol2` | `X87` | `msvcrt` |
| `LIFT:winmerge!sub_470022` | `LIFT` | `winmerge` |

Le bootstrap a ajouté **29 relations `CONCERNS`** attestées par une mention textuelle et **une relation `SUPERSEDES`** : `ABI-0006` remplace `ABI-0005`, le premier fix étant explicitement qualifié de « REVERTÉ » dans la fiche source. Une seconde exécution a confirmé l’idempotence : zéro fonction, zéro relation et zéro réécriture Front supplémentaires.

### M3 — Active Front d’ingénierie

`MemoryStore.replace_front()` et l’outil MCP `aret_replace_front` ont été ajoutés. Ils remplacent le contexte chaud entier dans une transaction et conservent l’état précédent dans `audit_event` sous l’opération `REPLACE_FRONT`.

Le Front livré contient maintenant :

| Clé | Valeur |
|---|---|
| `subsystem` | `DLL tierces C++ / Lifting` |
| `brick` | `AUTO-LIFT-02` |
| `current_wall` | Lifting DLL applicatives tierces (LLVM, mbedTLS, ITK) et indirect call recovery |
| `next_action` | Sélection pré-lift et driver déterministe sur première bibliothèque applicative |
| `relevant_1_address` à `relevant_5_address` | `ARCH-0003`, `EH-0025`, `X87-0003`, `LIFT-0019`, `RECOV-0021` |

Les anciennes clés de suivi de migration ont été retirées du Front, sans suppression de l’historique documentaire ni des événements d’audit.

### M4 — Adressage des relations

`relation` est désormais un type reconnu dans `core/addressing.py`. Les retours de `aret_add_relation` et `aret_supersede_relation` utilisent l’adresse canonique `ARET://relation/<id>`, et `aret_read` retourne les métadonnées exactes de la relation : `id`, `from_id`, `relation_type`, `to_id`, date et acteur de création.

### M5 — Consolidation SQLite WAL

La méthode `MemoryStore.checkpoint_wal()` exécute `PRAGMA wal_checkpoint(TRUNCATE)` et refuse l’opération si SQLite indique un journal bloqué. `export_bundle()` exécute ce checkpoint avant de sérialiser le snapshot et retourne son résultat dans `wal_checkpoint`.

La couche Git exécute le même checkpoint avant un commit mémoire explicite ou automatique. Si la base est occupée, elle refuse le commit plutôt que de versionner un fichier principal insuffisamment consolidé. Les exclusions `.aret-memory/*.sqlite-wal` et `.aret-memory/*.sqlite-shm` étaient déjà présentes dans `.gitignore`; elles ont été conservées.

### M6 — Documentation réalignée

Les documents suivants décrivent désormais l’état courant :

| Document | Corrections principales |
|---|---|
| `CONTRAT_MCP_V1.md` | 29 outils, relations lisibles, `replace_front`, hooks, oracles, WAL, Git borné et bundle v3. |
| `ADAPTATEURS_ORACLES.md` | Ajout de `winehash` comme mesure `UNKNOWN`, jamais comme gate `PASS`. |
| `CONTRATS_OPERATIONNELS.md` | Hooks installés, checkpoint WAL, auto-sync opt-in, bundle v3 et non-fusion. |

## Validation exécutée

```text
31 passed in 3.03s
MCP stdio validé : 29 outils déclarés, aret_boot opérationnel.
Compilation Python : réussie.
```

Les nouveaux tests couvrent la lecture d’une relation via son adresse, le checkpoint WAL avant bundle/Git, le bootstrap de graphe attesté, son idempotence et le remplacement auditée du Front.

## Snapshot final observé

| Élément | Avant correction | Après correction |
|---|---:|---:|
| Fonctions enregistrées | 0 | 7 |
| Relations enregistrées | 0 | 30 |
| Relations `CONCERNS` | 0 | 29 |
| Relations `SUPERSEDES` | 0 | 1 |
| Connaissances | 514 | 514 |
| Sources documentaires | 514 | 514 |
| Preuves | 0 | 0 |
| Active Front | Suivi de migration | Lifting de DLL tierces / `AUTO-LIFT-02` |
| Outils MCP | 28 | 29 |

Le snapshot JSON joint à la livraison fournit la liste exacte des fonctions, la distribution des relations et le Front final.

## Statut définitif du document 91

L’hypothèse de source 91 manquante, employée au moment de cet audit, a été corrigée le 20 août 2026. Le document est une synthèse redondante des sources déjà migrées, donc non applicable à la migration. `migration/import_doc91.py` retourne désormais `NOT_APPLICABLE` et `aret_export_reference_91` reste uniquement une vue dérivée de compatibilité. Voir `STATUT_DOCUMENT_91.md`.

## Références

[1]: ../migration/bootstrap_initial_graph.py "Bootstrap idempotent du graphe"
[2]: ../core/repository.py "Relation adressable, Front, checkpoint WAL et bundle"
[3]: ../ops/git_memory.py "Checkpoint WAL avant commit mémoire"
[4]: ../../../aret_runtime_snapshot_final.json "Snapshot lecture seule après correction"

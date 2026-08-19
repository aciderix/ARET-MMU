# Rapport de traitement de l’audit approfondi ARET-MMU

**Date :** 19 août 2026
**Périmètre :** M7 à M10 de l’audit approfondi. Le document historique 91 reste volontairement hors périmètre.

## Résultat de qualification

| Référence | Constat de l’audit | Qualification | Décision |
|---|---|---|---|
| M7 | Cinq oracles essentiels absents | Confirmé | Catalogue fermé étendu à neuf oracles. |
| M8 | Relations remplacées non filtrables | Confirmé | Migration 004 et cycle de vie `ACTIVE` / `SUPERSEDED`. |
| M9 | Aucune brique enregistrée | Confirmé | Bootstrap enrichi et appliqué au Store livré. |
| M10 | Chemin Git du Memory Store imbriqué potentiellement rejeté | Déjà conforme, mais insuffisamment verrouillé par test | Test de régression ajouté ; aucun changement de logique requis. |

## M7 — Catalogue des oracles

Le dictionnaire fermé `ORACLES` contient maintenant neuf entrées. Toutes les commandes restent déterministes et écrites dans le code ; l’utilisateur MCP n’obtient aucun passage de commande shell arbitraire.

| Oracle ajouté | Commande ou script fermé | Verdict `PASS` explicite |
|---|---|---|
| `transpilediff` | `bench/difftest_transpile.sh` | Équivalence des niveaux d’optimisation du pipeline transpile. |
| `stdcall_audit` | `bench/stdcall_audit.sh` | `stdcall-pop audit: PASS`. |
| `ehdiff` | `bench/ehdiff.sh` | Équivalence MSVC EH, N/N fixtures. |
| `gnuehdiff` | `bench/gnuehdiff.sh` | Équivalence GNU/Itanium EH, N/N fixtures. |
| `cpudiff` | `cargo test --release --features unpack cpudiff` | Résultat Cargo `test result: ok`. |

Les oracles précédents restent présents : `difftest`, `winediff`, `winehash` et `funcdiff`. `winehash` demeure délibérément `UNKNOWN` : il produit une mesure à comparer à Windows, jamais une preuve de conformité promouvable.

Les tests vérifient l’existence effective des cinq sources ajoutées, les neuf noms de catalogue, chaque signature de succès et la commande Cargo CPU figée.

## M8 — Cycle de vie actif des relations

La migration `004_relation_lifecycle.sql` ajoute à `relation` les colonnes `status` et `superseded_by`, ainsi que des index de traversal actifs. Les lignes héritées deviennent `ACTIVE` grâce à la valeur par défaut.

`supersede_relation` crée d’abord une relation de remplacement active, puis marque la relation précédente `SUPERSEDED` et renseigne son identifiant de remplacement. L’opération laisse également un événement d’audit avant/après. `aret_get_related` ne retourne que les relations actives par défaut. L’historique reste lisible avec `include_inactive=true`.

> Une relation obsolète n’est plus présentée comme un fait opérationnel courant, mais elle n’est jamais supprimée : elle demeure lisible, adressable et auditée.

## M9 — Briques d’ingénierie

Le bootstrap `migration/bootstrap_initial_graph.py` enregistre maintenant les dix briques suivantes dans la table `brick` :

| État | Briques |
|---|---|
| `ACTIVE` | `M7-GUI`, `AUTO-LIFT-02` |
| `PLANNED` | `FIBERS-01` à `FIBERS-05`, `PHASE-A`, `PHASE-B`, `PHASE-C` |

Les descriptions des jalons `M7-GUI` et `AUTO-LIFT-02` s’appuient sur les documents ARET existants et le Front confirmé. Les jalons FIBERS et PHASE sont enregistrés comme planifiés, avec une provenance de décision explicitement attribuée à la demande d’audit ; aucun statut de réalisation n’a été inventé.

Deux fonctions WinMerge supplémentaires attestées ont aussi été ajoutées : `LIFT:winmerge!sub_867436` et `LIFT:winmerge!sub_85fd18`. Cinq relations `CONCERNS` fondées sur des mentions littérales de ces symboles ont été créées. Une seconde exécution du bootstrap est idempotente.

## M10 — Confinement Git imbriqué

La logique existante déterminait déjà la racine avec `git rev-parse --show-toplevel`, puis calculait le sous-arbre mémoire avec `memory_path(...).relative_to(repository)`. Avec le dépôt racine `/repo` et le Store `/repo/aret-memory/.aret-memory`, le périmètre valide est donc correctement `aret-memory/.aret-memory/`.

Le nouveau test appelle `status(repository / "aret-memory", None)` et vérifie que le statut produit le chemin Git racine correct et qu’une modification mémoire est jugée sûre. Ce scénario couvre précisément le risque M10 sans élargir la surface de confiance Git.

## Validation finale

```text
36 passed in 3.37s
MCP stdio validé : 29 outils déclarés, aret_boot opérationnel.
Compilation Python : réussie.
```

Le snapshot final confirme :

| Élément | État final |
|---|---:|
| Migrations appliquées | 4 |
| Connaissances sourcées | 514 |
| Fonctions adressables | 9 |
| Briques | 10 |
| Relations | 35 |
| Relations actives | 35 |
| Relations `CONCERNS` | 34 |
| Relations `SUPERSEDES` | 1 |
| Outils MCP | 29 |
| Document 91 migré | Non, explicitement hors périmètre |

## Références

[1]: ../evidence/adapters/oracles.py "Catalogue fermé des neuf oracles"
[2]: ../schema/004_relation_lifecycle.sql "Migration de cycle de vie relationnel"
[3]: ../core/repository.py "Traversée active et supersession append-only"
[4]: ../migration/bootstrap_initial_graph.py "Bootstrap de fonctions, relations et briques"
[5]: ../ops/git_memory.py "Confinement Git par racine de dépôt"
[6]: ../../../aret_runtime_snapshot_m7_m10_final.json "Snapshot lecture seule final"

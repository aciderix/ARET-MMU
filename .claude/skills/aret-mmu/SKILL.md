---
name: aret-mmu
description: Utiliser la mémoire persistante ARET-MMU pour toute reprise de session, analyse d’architecture, décision de roadmap, découverte reverse engineering, ajout de connaissance ou preuve d’exécution dans le dépôt ARET. Appliquer la discipline FIND puis READ, respecter le Front et ne promouvoir PROVEN qu’avec une preuve PASS admissible.
---

# Procédure ARET-MMU

Utiliser ce skill dès qu’une tâche porte sur l’état connu d’ARET, une décision d’architecture, une brique de roadmap, une hypothèse de reverse engineering, une preuve ou une reprise de contexte.

## Démarrage et reprise

1. Après `SessionStart` ou `PostCompact`, considérer la barrière de reprise comme active. Commencer exclusivement par `aret_get_resume_protocol`.
2. Lire chacun des lots retournés avec `aret_read_batch`, sans omettre les pages canoniques des documents 70, 80, 81, 82 et 90, ni les dernières entrées du journal 71.
3. Ne pas contourner la barrière : jusqu’à la lecture réussie de toutes les adresses requises, toute opération hors lecture est refusée. Ne pas tenter de conclure ; le contrôle de fin relancera une fois la reprise si elle est incomplète.
4. Une fois la barrière levée, appeler `aret_boot` puis `aret_get_resume_brief` si un contexte de travail enrichi reste nécessaire. Examiner le contexte Git injecté (branche, commits, arbre) avant toute opération de synchronisation.
5. Appeler `aret_restore` uniquement pour le contexte chaud minimal lorsque la reprise enrichie n’est pas nécessaire.
6. Appeler `aret_get_front` avant de modifier une orientation active ou une brique référencée par le Front.
7. Considérer la mémoire SQLite comme la source canonique ; le texte de conversation n’est jamais une preuve de l’état du projet.

## Lecture et découverte

1. Utiliser `aret_find` ou les vues spécialisées pour découvrir des candidats.
2. Considérer un score de recherche comme une piste, jamais comme un fait ni une preuve.
3. Lire uniquement les ressources sélectionnées avec `aret_read` ou `aret_read_batch`.
4. Utiliser `aret_get_related` avec `include_inactive=false` par défaut ; demander l’historique explicitement seulement lorsqu’il est nécessaire.
5. Utiliser `aret_get_roadmap` pour une vue stratégique compacte des briques, jalons, plateformes, priorités et bloqueurs.

## Écriture contrôlée

1. Écrire uniquement des faits confirmés, attribués et utiles à la continuité d’ARET.
2. Enregistrer une connaissance ou une décision avec les outils métier dédiés ; ne jamais tenter d’exécuter du SQL arbitraire.
3. Ne modifier le Front qu’après avoir vérifié les entités citées. La clé `brick` du Front doit toujours référencer une brique ACTIVE.
4. Préserver l’historique relationnel : remplacer une relation avec l’opération de cycle de vie appropriée au lieu de la supprimer ou de la réécrire implicitement.
5. Garder les synchronisations Git explicites et bornées à `aret-memory/.aret-memory/`. Ne jamais supposer qu’un push a été exécuté lorsque `auto_push=false`.

## Pipelines ARET, corpus et industrialisation

1. Commencer par `aret_get_pipeline_catalog` puis `aret_get_toolchain_status` avant de proposer un test, une génération ou un corpus.
2. Appeler `aret_run_pipeline` avec `dry_run=true` avant toute exécution réelle ; lire le plan, les prérequis et la politique retournés.
3. Les pipelines `GENERATE` exigent `dry_run=false` et `confirm_apply=true`. Présenter le plan et le diff attendu avant l’application.
4. Les pipelines `NETWORK` exigent `confirm_network=true` pour tout téléchargement réel ; seules les sources et profils fermés du catalogue sont admis.
5. Les pipelines `SENSITIVE` exigent `confirm_sensitive=true`. Une capture de snapshot suspend un processus et ne doit être demandée qu’avec un PID et une plage mémoire explicitement validés.
6. Après une exécution réelle, consulter `aret_get_pipeline_runs` et `aret_read_pipeline_artifact`. Distinguer un verdict de pipeline d’une preuve admissible `PROVEN`.
7. Utiliser `aret_get_assets` pour connaître les corpus, PE32, DLL, IAT maps et snapshots disponibles. `aret_register_asset` exige toujours `confirm_import=true` ; aucun chemin hors dépôt/Store n’est accepté.
8. Les walls et sweeps priorisent le travail par impact mesuré ; ils ne prouvent jamais la correction comportementale. Toute correction doit ensuite passer les oracles appropriés.

## Preuves et statut PROVEN

1. Exécuter un oracle autorisé avec `aret_run_oracle` lorsque la validation repose sur une exécution reproductible.
2. Vérifier résultat, artefact, hash et reçu avant d’attacher une preuve.
3. Ne jamais déclarer une connaissance `PROVEN` sur la base d’une intuition, d’un score, d’une sortie non vérifiée ou d’une preuve sans reçu admissible.
4. Utiliser les outils d’invalidation lorsqu’une preuve n’est plus valable afin de préserver l’audit et la cohérence transactionnelle.

## Garde-fous opérationnels

- Ne pas importer le document 91 : il est `NOT_APPLICABLE`, car il constitue une synthèse redondante des documents déjà migrés.
- Préserver la séparation stricte entre découverte, lecture exacte, preuves et audit.
- Après une mutation significative, relire la ressource, le pipeline, l’asset ou la roadmap concernée afin de vérifier l’état canonique réellement enregistré.
- Avant de conclure une tâche, indiquer clairement ce qui est observé, ce qui est inféré et ce qui est prouvé.

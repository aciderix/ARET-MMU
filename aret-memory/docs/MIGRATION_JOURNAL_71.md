# Migration exhaustive du journal 71

## Résultat

Le journal chronologique du document 71 est désormais migré dans ARET-MMU de manière déterministe. Le parseur ne repose ni sur un LLM, ni sur une recherche sémantique : il repère uniquement les titres `### AAAA-MM-JJ — …` dans la section `## 3. Journal chronologique`, puis conserve chaque bloc Markdown exact jusqu’au titre daté suivant.

| Mesure | Valeur contrôlée |
|---|---:|
| Entrées datées analysées | 378 |
| Plage documentaire couverte | Lignes 382–8 719 du document 71 |
| Références de provenance 71 en base | 378 |
| Plages dupliquées | 0 |
| Connaissances canoniques totales après migration pilote + 71 | 382 |
| Entrées FTS5 dérivées | 382 |
| Lot de migration | `MIG-J71-232A6EBF` |
| Révision source | `232a6ebf1d27514a1f8a401966dbb3756ff51a8a` |

Le contrôle `verify_journal_71.py` relit chaque plage du fichier source, compare le contenu stocké, le hash de provenance et le hash de contenu, puis vérifie l’absence de doublons, le statut du lot et la cohérence de l’index FTS5. Il a produit un résultat `ok: true`.

> Les 378 objets issus du journal restent des **faits documentés** : aucun n’est créé avec le statut `PROVEN`. Une mention historique d’oracle, de test ou de résultat bit-identique est conservée dans le texte source, mais ne devient pas une nouvelle preuve admissible sans objet `proof` produit par un adaptateur de confiance.

## Règles de découpage et de qualification

La migration privilégie l’absence de surinterprétation. Chaque entrée conserve son titre, sa date comme `effective_at`, ses tags explicites, le contenu original et une référence structurée `knowledge_source`.

| Information | Règle appliquée |
|---|---|
| Frontière d’entrée | Titre daté de niveau `###` de la section chronologique du 71. |
| Contenu | Copie exacte du Markdown, sans résumé ni reformulation. |
| Provenance | Dépôt, commit, chemin, lignes, section et SHA-256 de l’extrait. |
| Type par défaut | `FORENSIC` et `OBSERVED`. |
| `MEASUREMENT` | Seulement si le titre contient un marqueur littéral tel que « mesuré », « mesure », « sweep », « régression » ou « différentiel ». |
| `DISCOVERY` | Seulement si le titre contient explicitement « découverte » ou un constat de mur. |
| `DECISION` | Seulement si le titre contient explicitement « décision ». |
| `PROVEN` | Interdit pendant la migration documentaire. |
| Composant | Déduit uniquement des tags écrits dans le titre (`[HLE]`, `[RECOV]`, `[LIFT]`, etc.) ; autrement `J71`. |

Cette classification est délibérément conservative : elle sert à la découverte et au regroupement, mais le texte original et sa provenance demeurent l’autorité pour toute lecture ou qualification ultérieure.

## Active Front de migration

Le Front n’essaie pas d’inférer le chantier logiciel réel de l’utilisateur. Il décrit uniquement l’état de la migration : `MIGRATION-J71-01`, le nombre total d’entrées migrées (`378`) et les cinq pointeurs les plus récents du journal. Cette distinction évite qu’un mécanisme administratif se fasse passer pour l’état opérationnel d’ARET.

## Commandes reproductibles

```bash
cd aret-memory

# Voir les 378 entrées et la classification, sans écrire.
python3 migration/import_journal_71.py --dry-run

# Migrer le journal ou rejouer sans créer de doublon.
python3 migration/import_journal_71.py

# Vérifier contenu, hashes, provenance, FTS5 et statut du lot.
python3 migration/verify_journal_71.py \
  --output .aret-memory/exports/verification_journal_71_<commit>.json

# Consulter l’état chaud de la migration et une entrée exacte.
python3 cli/aret_memory.py --memory-dir .aret-memory show-front
python3 cli/aret_memory.py --memory-dir .aret-memory read ARET://knowledge/RECOV-0001
```

## Préparation de la migration 82 et 90

La prochaine tranche ne doit pas reprendre le même découpage que le journal. Les documents 82 et 90 sont des **trackers vivants** et des **mesures de corpus** : leurs sections ont une sémantique métier plus stable et doivent donc devenir des objets spécialisés.

| Source | Unité de découpage initiale | Types cibles prudents | Effet sur le Front |
|---|---|---|---|
| 82 — Suivi de l’industrialisation | Générateur, phase, jalon et prochain cran | `STATE`, `BRICK`, `DECISION`, `MEASUREMENT` | Mettre à jour les briques et jalons actifs après revue. |
| 90 — Corpus sources | Sweep daté, source de corpus, résultat mesuré | `MEASUREMENT`, `DISCOVERY`, `STATE` | Alimenter les priorités de mesures, jamais les déclarer prouvées seules. |
| 70 — Référence synthétique | Règle, état, chiffres de référence | `RULE`, `STATE`, `MEASUREMENT` | Consolider uniquement après réconciliation avec 71/82/90. |
| 80/81 — Architecture et industrialisation | Décision ou bloc d’architecture stable | `ARCHITECTURE`, `DECISION`, `BRICK` | Créer des relations explicites vers les composants et les briques. |

Le document 82 contient déjà une distinction exploitable entre générateurs ré-exécutables, phases et prochains crans. Le document 90 doit conserver ses données de sweep sous forme de mesures séparées des conclusions. Une migration ultérieure devra donc introduire un parseur par section, pas simplement une découpe uniforme de titres.

## Références

[1]: https://github.com/aciderix/Automatic-reverse-engineering-toolkit/blob/232a6ebf1d27514a1f8a401966dbb3756ff51a8a/docs/vision/71-journal-de-bord.md "ARET 71 — Journal de bord"
[2]: https://github.com/aciderix/Automatic-reverse-engineering-toolkit/blob/232a6ebf1d27514a1f8a401966dbb3756ff51a8a/docs/vision/82-suivi-industrialisation.md "ARET 82 — Suivi de l’industrialisation"
[3]: https://github.com/aciderix/Automatic-reverse-engineering-toolkit/blob/232a6ebf1d27514a1f8a401966dbb3756ff51a8a/docs/vision/90-corpus-sources.md "ARET 90 — Corpus sources"

# Migration des trackers 82 et 90

## Périmètre migré

Les documents 82 et 90 sont désormais intégrés au Memory Store sous forme de sections non chevauchantes. Contrairement au journal 71, ces documents sont des trackers et des mesures : le découpage utilise les titres Markdown de niveaux `##` et `###`, en excluant les titres conteneurs sans contenu propre. Chaque objet conserve son bloc Markdown original et une provenance structurée complète.

| Document | Nature | Sections migrées | Composant | Types employés |
|---|---|---:|---|---|
| 82 — Suivi de l’industrialisation | Générateurs, jalons et état de chantiers | 33 | `INDUS` | `RULE`, `STATE`, `MEASUREMENT`, `OBSERVATION` |
| 90 — Corpus sources | Sources de binaires, sweeps et murs mesurés | 17 | `CORPUS` | `RULE`, `STATE`, `MEASUREMENT` |
| **Total** | — | **50** | — | — |

Le lot `MIG-8290-232A6EBF` est lié à la révision `232a6ebf1d27514a1f8a401966dbb3756ff51a8a`. Il ne crée aucun statut `PROVEN` : les passages documentant des oracles ou des résultats restent des observations migrées, distinctes des objets de preuve HMAC du MCP.

## Politique de qualification

La classification est délibérément locale au titre de la section et ne tente pas d’interpréter le texte. Les intitulés contenant « principe », « invariant » ou « doctrine » deviennent des règles actives. Les termes explicites « mesure », « sweep », « re-mesure », « mur », « résidu », « faisabilité », « portée » ou « échantillon » produisent des mesures observées. Les entrées de roadmap et d’état explicite deviennent des états ; le reste demeure une observation.

> Cette catégorisation facilite FIND et l’Active Front, mais elle ne remplace pas la lecture de l’extrait exact ni sa provenance. Toute promotion épistémique future doit passer par le mécanisme de preuves contrôlées.

## Contrôles réalisés

| Contrôle | Résultat |
|---|---|
| Sections attendues du 82 | 33 en source, 33 dans le Store |
| Sections attendues du 90 | 17 en source, 17 dans le Store |
| Plages de provenance dupliquées | 0 |
| Hash source et hash contenu | Vérifiés pour chaque objet |
| Connaissances canoniques après migration | 432 |
| Index FTS5 dérivé | 432 entrées, reconstruit depuis le canonique |
| Idempotence | Une seconde exécution n’ajoute aucun objet |
| Tests de régression du projet | 8 réussis, plus intégration MCP stdio |

Le vérificateur `migration/verify_trackers_82_90.py` produit un rapport JSON de contrôle dans `.aret-memory/exports/` et échoue si une plage, un hash, le statut de lot, l’index FTS ou la règle d’absence de `PROVEN` diffère de l’attendu.

## Commandes reproductibles

```bash
cd aret-memory

# Examiner le plan sans écrire.
python3 migration/import_trackers_82_90.py --dry-run

# Migrer les sections non encore présentes.
python3 migration/import_trackers_82_90.py

# Contrôler toute la migration.
python3 migration/verify_trackers_82_90.py \
  --output .aret-memory/exports/verification_trackers_82_90_<commit>.json
```

## Couverture mémoire cumulée

| Source | Couverture actuelle | Objets sourcés |
|---|---|---:|
| 70 — Référence | Migration pilote de règles et état | 2 |
| 71 — Journal chronologique | Migration exhaustive de la section 3 | 378 |
| 80 — Architecture | Migration pilote d’une orientation représentative | 1 |
| 81 — Industrialisation | Migration pilote d’une décision structurante | 1 |
| 82 — Suivi de l’industrialisation | Migration structurée des sections non conteneurs | 33 |
| 90 — Corpus sources | Migration structurée des sections non conteneurs | 17 |
| **Total** | — | **432** |

Les prochaines sources à traiter en priorité sont les sections restantes des documents 70, 80 et 81, car elles constituent encore une couverture pilote. Leur migration devra maintenir le même niveau de prudence : séparation entre texte historique, règles, états, mesures et preuves d’exécution.

## Références

[1]: https://github.com/aciderix/Automatic-reverse-engineering-toolkit/blob/232a6ebf1d27514a1f8a401966dbb3756ff51a8a/docs/vision/82-suivi-industrialisation.md "ARET 82 — Suivi de l’industrialisation"
[2]: https://github.com/aciderix/Automatic-reverse-engineering-toolkit/blob/232a6ebf1d27514a1f8a401966dbb3756ff51a8a/docs/vision/90-corpus-sources.md "ARET 90 — Corpus sources"

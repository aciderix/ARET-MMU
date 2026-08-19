# Migration exhaustive des références 70, 80 et 81

## Résultat

Les documents de référence 70, 80 et 81 sont désormais couverts par des objets ARET-MMU sourcés. L’importeur découpe les sections Markdown de niveaux `##` et `###`, préserve leur contenu textuel exact et soustrait les extraits déjà importés durant la migration pilote. Il ne duplique donc ni le principe sacré du 70, ni l’orientation fibers du 80, ni le principe directeur de l’industrialisation du 81.

| Document | Rôle | Objets sourcés présents | Validation |
|---|---|---:|---|
| 70 — Référence, état, méthode et reste | Doctrine, états, roadmap et méthode | 55 | Toutes les lignes substantielles des sections migrables sont couvertes. |
| 80 — Orientations architecturales | Contraintes, orientations et architecture fibers | 10 | Toutes les lignes substantielles des sections migrables sont couvertes. |
| 81 — Industrialisation | Chantiers, décisions et journal d’industrialisation | 21 | Toutes les lignes substantielles des sections migrables sont couvertes. |
| **Total** | — | **86** | Aucun doublon de provenance. |

Le lot `MIG-708081-232A6EBF` est rattaché à la révision `232a6ebf1d27514a1f8a401966dbb3756ff51a8a`. Les contenus issus de la documentation demeurent des règles, états, observations, décisions ou architectures ; ils ne deviennent jamais `PROVEN` sans objet de preuve contrôlé.

## Méthode de continuité avec la migration pilote

Les premiers objets créés dans la migration pilote couvrent des plages à forte valeur. L’importeur principal détecte ces plages dans `knowledge_source`, divise uniquement les sections qui les contiennent et crée les fragments restants. Les lignes vides et séparateurs Markdown seuls sont ignorés, car ils ne portent aucune connaissance durable. Le vérificateur contrôle ensuite que toute ligne substantielle des sections migrables est couverte par une provenance, qu’elle provienne du pilote ou de l’import exhaustif.

> Cette stratégie maintient l’append-first : aucun objet existant n’est réécrit ou supprimé pour « nettoyer » la migration. Les compléments sont ajoutés comme nouveaux objets précisément sourcés.

## Classification prudente

| Situation de titre | Type appliqué | Statut |
|---|---|---|
| Principe, doctrine, invariant, limite dure ou règle | `RULE` | `ACTIVE` |
| Mesure, sweep, oracle, état terrain, échantillon ou mur | `MEASUREMENT` | `OBSERVED` |
| Décision, orientation, retenu ou verdict | `DECISION` | `ACTIVE` |
| Roadmap, plan, phase, état, chantier ou milestone | `STATE` | `ACTIVE` |
| Document 80 : cadre et architecture retenue | `ARCHITECTURE` | `ACTIVE` |
| Autre section | `OBSERVATION` | `OBSERVED` |

La règle est fondée sur les marqueurs explicites des titres. Elle n’interprète pas le corps du texte, qui reste la référence exacte de lecture.

## Couverture documentaire centrale

| Source | Objets sourcés | État |
|---|---:|---|
| 70 | 55 | Couverture exhaustive des sections migrables |
| 71 | 378 | Couverture exhaustive du journal chronologique §3 |
| 80 | 10 | Couverture exhaustive des sections migrables |
| 81 | 21 | Couverture exhaustive des sections migrables |
| 82 | 33 | Tracker migré par sections non conteneurs |
| 90 | 17 | Corpus migré par sections non conteneurs |
| **Total canonique** | **514** | FTS5 dérivé reconstruit et conforme |

## Commandes reproductibles

```bash
cd aret-memory

# Examiner les fragments restant à migrer dans le Store courant.
python3 migration/import_references_70_80_81.py --dry-run

# Migrer les fragments absents puis vérifier sources, contenu et couverture.
python3 migration/import_references_70_80_81.py
python3 migration/verify_references_70_80_81.py \
  --output .aret-memory/exports/verification_references_70_80_81_<commit>.json
```

Le contrôle vérifie la cohérence entre les objets et leurs lignes source, les hashes de contenu, l’absence de provenance dupliquée, la couverture de chaque ligne substantielle, le statut du lot et la reconstruction FTS5.

## Prochaine couche d’intégration

La mémoire documentaire centrale est maintenant suffisamment structurée pour passer de l’import à l’exploitation opérationnelle. Les étapes suivantes prévues par l’architecture sont l’intégration des hooks `SessionStart`/`PreCompact`/`PostCompact`, une politique Git limitée à `.aret-memory/`, les adaptateurs d’oracles réels et les mécanismes de Memory Bundle pour le multi-device.

## Références

[1]: https://github.com/aciderix/Automatic-reverse-engineering-toolkit/blob/232a6ebf1d27514a1f8a401966dbb3756ff51a8a/docs/vision/70-reference-etat-methode-reste.md "ARET 70 — Référence, état, méthode et reste"
[2]: https://github.com/aciderix/Automatic-reverse-engineering-toolkit/blob/232a6ebf1d27514a1f8a401966dbb3756ff51a8a/docs/vision/80-orientations-architecturales.md "ARET 80 — Orientations architecturales"
[3]: https://github.com/aciderix/Automatic-reverse-engineering-toolkit/blob/232a6ebf1d27514a1f8a401966dbb3756ff51a8a/docs/vision/81-industrialisation.md "ARET 81 — Industrialisation"

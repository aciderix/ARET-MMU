# Migration pilote ARET-MMU — documents 70, 71, 80 et 81

## Objet et résultat

Cette migration pilote valide le passage contrôlé de la documentation historique vers le **Memory Store ARET-MMU**. Elle ne résume ni ne reformule les sources : le champ `content` conserve exactement le bloc Markdown sélectionné, tandis que la provenance est stockée dans `knowledge_source` avec le dépôt, le commit, le chemin, la plage de lignes, la section et le hash SHA-256 de l’extrait.

> Une entrée documentaire est une **observation historique ou un état documenté**, pas une preuve d’exécution nouvellement produite. La migration ne crée donc aucune connaissance `PROVEN` et aucune preuve synthétique.

La migration a été effectuée sur la révision `232a6ebf1d27514a1f8a401966dbb3756ff51a8a` du dépôt ARET. Elle a créé **9 objets de connaissance**, leurs **9 références de provenance**, un lot `MIG-PILOT-232A6EBF`, l’Active Front de migration et les événements d’audit associés.

| Adresse | Type / statut | Source exacte | Rôle migré |
|---|---|---|---|
| `ARET://knowledge/CORE-0001` | `RULE` / `ACTIVE` | 70, lignes 42–63 | Principe sacré : correct ou arrêt bruyant. |
| `ARET://knowledge/CORE-0002` | `STATE` / `OBSERVED` | 70, lignes 240–249 | État des portes de régression documenté. |
| `ARET://knowledge/FIBER-0001` | `ARCHITECTURE` / `ACTIVE` | 80, lignes 33–47 | Threads coopératifs par fibers. |
| `ARET://knowledge/INDUS-0001` | `DECISION` / `ACTIVE` | 81, lignes 18–35 | Mesurer avant de coder et conserver « correct ou abort ». |
| `ARET://knowledge/HLE-0001` | `FORENSIC` / `OBSERVED` | 71, lignes 8570–8607 | Incrément FS volumes et chemins Unicode. |
| `ARET://knowledge/HLE-0002` | `FORENSIC` / `OBSERVED` | 71, lignes 8609–8629 | Incrément Shell PIDL. |
| `ARET://knowledge/HLE-0003` | `FORENSIC` / `OBSERVED` | 71, lignes 8631–8655 | Incrément d’introspection process. |
| `ARET://knowledge/HLE-0004` | `FORENSIC` / `OBSERVED` | 71, lignes 8657–8681 | Incrément CRT, registre et crypto. |
| `ARET://knowledge/RECOV-0001` | `FORENSIC` / `OBSERVED` | 71, lignes 8683–8719 | Recovery sound de spirv-cross par pointeur de fonction matérialisé. |

## Évolution du modèle de données

La migration introduit la version de schéma 2. La migration `002_document_provenance.sql` ajoute `effective_at` aux connaissances et les deux tables suivantes.

| Table | Fonction |
|---|---|
| `migration_batch` | Rend un import identifiable, hashé, auditable et contrôlable à une révision donnée du dépôt source. |
| `knowledge_source` | Associe une connaissance à un extrait documentaire précis et immuable dans la révision source. |

Le serveur applique désormais toutes les migrations SQL numérotées dans l’ordre et refuse une version de migration dont le checksum changerait après application. Lors d’un `aret_read`, la clé `sources` restitue les références de provenance ; elle n’est donc ni cachée dans un bloc Markdown ni déduite par le modèle.

## Exécuter ou vérifier la migration

Depuis le répertoire `aret-memory/` du dépôt ARET, les commandes suivantes prévisualisent puis effectuent l’import. Le script est idempotent : une seconde exécution sur la même révision reconnaît les plages déjà importées et ne crée aucun doublon.

```bash
# Prévisualisation : aucune écriture SQLite.
python3 migration/import_pilot.py --dry-run

# Import vers .aret-memory/.
python3 migration/import_pilot.py

# Vérification des objets et de l’Active Front.
python3 cli/aret_memory.py --memory-dir .aret-memory show-front
python3 cli/aret_memory.py --memory-dir .aret-memory read ARET://knowledge/RECOV-0001
python3 cli/aret_memory.py --memory-dir .aret-memory export --format json --name controle_migration_pilote
```

Le rapport dérivé est écrit dans `.aret-memory/exports/migration_pilot_<commit-court>.json`. Il liste les adresses créées, le manifest hash, les sources importées et les éventuels objets déjà présents.

## Contrôles réalisés

| Contrôle | Résultat attendu | Résultat constaté |
|---|---|---|
| Contenu stocké | Identique aux lignes sources | Conforme, contrôlé par hash SHA-256. |
| Provenance | Dépôt, commit, chemin, lignes, section, hash | 9 références structurées présentes. |
| Idempotence | Aucun doublon à la seconde exécution | Conforme : les 9 extraits sont ignorés comme déjà importés. |
| Audit | Début et fin de lot, objets, sources et Front audités | Conforme. |
| Recherche | FTS5 reconstructible depuis les données canoniques | Couverte par la suite de tests du Memory Store. |
| MCP | Outils déclarés et bootstrap utilisable sur stdio | Test d’intégration réussi. |

La suite intégrée compte **6 tests réussis**, dont le test de migration qui vérifie le contenu exact d’un extrait, sa source et l’idempotence du lot. Le test d’intégration MCP vérifie en plus l’initialisation et la déclaration des outils.

## Poursuite recommandée

L’ordre suivant préserve le modèle hybride défini par l’architecture mémoire : commencer par les objets déjà atomiques et datés, conserver les textes narratifs tels quels, puis seulement granulariser après validation humaine des frontières métier.

| Priorité | Source | Représentation initiale recommandée | Raison |
|---|---|---|---|
| 1 | 71 §3, du plus récent au plus ancien | `FORENSIC`, `OBSERVATION`, `DECISION`, `DISCOVERY` | Les entrées sont déjà datées, taguées et proches du format objet. |
| 2 | 82, tracker vivant | `STATE`, `BRICK`, `MEASUREMENT`, `DECISION` | Il doit alimenter l’Active Front et les chantiers actifs. |
| 3 | 90, corpus et sweeps | `MEASUREMENT`, `DISCOVERY`, `DECISION` | Les données de priorisation doivent rester distinguées des conclusions. |
| 4 | 70 | `RULE`, `STATE`, `MEASUREMENT` | Référence synthétique ; migrer les sections seulement après comparaison avec 71/82. |
| 5 | 80/81 | `ARCHITECTURE`, `DECISION`, `BRICK` | Textes narratifs à conserver d’abord sous forme de blocs sourcés. |
| 6 | 50, archive historique | `FORENSIC` / `OBSERVATION` | À traiter uniquement sur demande ou lorsqu’une information manque dans 71. |

Les documents sources restent intacts. Ils ne quittent le chemin opérationnel qu’après une migration complète, des exports de contrôle, une revue humaine et la démonstration que chaque objet durable reste adressable et sourcé.

## Références

[1]: https://github.com/aciderix/Automatic-reverse-engineering-toolkit/blob/232a6ebf1d27514a1f8a401966dbb3756ff51a8a/docs/vision/70-reference-etat-methode-reste.md "ARET 70 — Référence état, méthode et reste"
[2]: https://github.com/aciderix/Automatic-reverse-engineering-toolkit/blob/232a6ebf1d27514a1f8a401966dbb3756ff51a8a/docs/vision/71-journal-de-bord.md "ARET 71 — Journal de bord"
[3]: https://github.com/aciderix/Automatic-reverse-engineering-toolkit/blob/232a6ebf1d27514a1f8a401966dbb3756ff51a8a/docs/vision/80-orientations-architecturales.md "ARET 80 — Orientations architecturales"
[4]: https://github.com/aciderix/Automatic-reverse-engineering-toolkit/blob/232a6ebf1d27514a1f8a401966dbb3756ff51a8a/docs/vision/81-industrialisation.md "ARET 81 — Industrialisation"

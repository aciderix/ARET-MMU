# Statut définitif du document 91

Le document 91 a été initialement évoqué comme une éventuelle source Markdown à migrer. Cette hypothèse est désormais **invalidée** : il s’agissait d’une synthèse demandée à une autre IA, reprenant les informations importantes déjà présentes dans les documents 70, 71, 80, 81, 82, 83 et les sources associées.

> **Décision de gouvernance :** le document 91 n’est ni une source canonique, ni une source historique attendue, ni un prérequis de complétude. Il ne doit pas être importé dans le Memory Store.

## Conséquence dans ARET-MMU

Le Memory Store contient déjà les connaissances extraites et sourcées des documents d’origine. Une importation du document 91 créerait une redondance narrative, rendrait la provenance moins précise et pourrait introduire des divergences entre la synthèse et les sources qu’elle résume.

L’outil `aret_export_reference_91` est conservé uniquement comme **vue dérivée de compatibilité**. Il construit à la demande une synthèse lisible depuis les objets canoniques `STATE`, `RULE`, `MEASUREMENT`, `DECISION` et `BRICK`. Cette vue ne constitue pas une source, ne modifie pas la base et ne suppose l’existence d’aucun fichier Markdown 91.

| Élément | Statut |
|---|---|
| Import Markdown 91 | Non applicable ; explicitement désactivé. |
| `migration/import_doc91.py` | Contrôleur informatif : il retourne `NOT_APPLICABLE` et n’importe rien. |
| `aret_export_reference_91` | Conservé comme synthèse dérivée optionnelle. |
| Complétude V5 | Non affectée : les sources détaillées ont déjà été migrées avec provenance. |

## Utilisation recommandée

Pour consulter l’état consolidé, utilisez `aret_export_reference_91` ou les vues métier plus spécifiques comme `aret_get_roadmap`, `aret_find` puis `aret_read`. Pour vérifier l’origine d’une information, remontez toujours à la connaissance et à sa provenance structurée, jamais à une synthèse.

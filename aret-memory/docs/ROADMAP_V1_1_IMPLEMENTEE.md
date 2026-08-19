# Roadmap structurée ARET-MMU V1.1

**Statut :** implémentée et validée dans la livraison roadmap.
**Motivation :** réduire les multiples appels `find` / `get_related` nécessaires pour reconstituer l’avancement d’un sous-système ou d’une stratégie produit, tout en conservant SQLite comme source canonique et en refusant une `ROADMAP.md` manuelle divergente.

> Cette extension ne corrige pas une défaillance de la V1. Elle ajoute une vue métier compacte et des métadonnées de portefeuille plus faciles à filtrer, tout en conservant les objets canoniques, les relations et les preuves de la V1.

## 1. Capacités V1.1 livrées

| Objectif | Résultat attendu |
|---|---|
| Classer les briques | Filtrer sans ambiguïté par jalon, priorité et plateforme cible. |
| Lire une roadmap rapidement | Obtenir l’arbre exact des briques, états, bloqueurs et décisions connexes dans une réponse bornée. |
| Exporter une vue humaine | Générer une roadmap Markdown dérivée de SQLite, jamais éditée comme source de vérité. |
| Préserver les invariants V1 | Aucune écriture SQL libre, aucune suppression historique, aucun statut de capacité inventé. |

## 2. Migration 005 appliquée

La table `brick` de V1 contenait l’identité, le composant, le titre, l’état et la description. La migration 005 ajoute trois métadonnées de classement.

```sql
ALTER TABLE brick ADD COLUMN milestone TEXT;
ALTER TABLE brick ADD COLUMN target_platform TEXT;
ALTER TABLE brick ADD COLUMN priority INTEGER NOT NULL DEFAULT 3
    CHECK (priority BETWEEN 1 AND 5);

CREATE INDEX idx_brick_roadmap
    ON brick(milestone, target_platform, priority, state, component_id);
```

| Colonne | Valeur exemple | Interprétation |
|---|---|---|
| `milestone` | `M7`, `M8`, `V2`, `PHASE-B` | Jalon d’intégration ou horizon de livraison. |
| `target_platform` | `x86-pe32`, `x64-win11`, `x86-elf`, `wasm32-wasi` | Cible principale de la brique. Une brique transverse peut rester `NULL`. |
| `priority` | 1 à 5 | 1 = blocage immédiat ; 3 = planifié normal ; 5 = horizon lointain. |

La migration n’ajoute ni date artificielle, ni responsable imaginaire, ni statut de capacité. Les informations de conception et de dépendance continuent de vivre dans les connaissances et les relations canoniques.

## 3. Outil MCP livré : `aret_get_roadmap`

### Signature

```python
aret_get_roadmap(
    milestone: str | None = None,
    component_id: str | None = None,
    target_platform: str | None = None,
    include_done: bool = False,
    max_items: int = 50,
) -> dict
```

### Contrat

L’outil serait **en lecture seule**. Il ne devine aucune dépendance : il retourne uniquement les briques, les relations et les objets explicitement stockés dans SQLite.

| Champ retourné | Source canonique |
|---|---|
| Identité, titre, état, priorité, jalon, plateforme | Table `brick`. |
| Composant associé | Table `component` / clé de brique. |
| Décisions et architectures parentes | Relations `IMPLEMENTS`, `INFORMED_BY`, `APPLIES_TO` actives. |
| Bloqueurs | Relations `BLOCKED_BY` actives. |
| Preuves et capacité démontrée | Relations `VERIFIED_BY`, fiches `STATE` et preuves admissibles. |
| Résumé de comptage | Calcul déterministe à partir des résultats retournés. |

### Bornes et sûreté

- `max_items` reste borné par les limites globales du MCP ;
- seules les relations `ACTIVE` sont utilisées par défaut ;
- `include_done=false` masque les briques `DONE` sans les supprimer ;
- aucune traversal récursive non bornée n’est autorisée ;
- la réponse compacte vise moins de 1 000 tokens dans le cas normal ;
- une absence de résultat est retournée explicitement.

### Exemple de réponse

```json
{
  "filters": {"target_platform": "wasm32-wasi", "include_done": false},
  "summary": {"planned": 2, "active": 1, "blocked": 1, "done": 0},
  "bricks": [
    {
      "id": "TARGET-WASM-01",
      "state": "ACTIVE",
      "priority": 1,
      "milestone": "M8",
      "target_platform": "wasm32-wasi",
      "blockers": ["ARET://knowledge/EXCEPTIONS-PORTABILITY-01"],
      "implements": ["ARET://knowledge/ARCH-WASM-BACKEND"]
    }
  ]
}
```

## 4. Outil d’export livré : `aret_export_roadmap`

### Signature

```python
aret_export_roadmap(
    milestone: str | None = None,
    component_id: str | None = None,
    target_platform: str | None = None,
    include_done: bool = False,
    name: str = "roadmap",
) -> dict
```

L’outil génère un Markdown ou HTML dans le répertoire d’exports. Le fichier est une **vue dérivée** : il ne doit jamais être modifié à la main pour devenir une seconde source de vérité.

Le document exporté doit comporter :

1. les filtres appliqués et la date de génération ;
2. le résumé par état (`PLANNED`, `ACTIVE`, `BLOCKED`, `DONE`) ;
3. les briques avec priorité, jalon et plateforme ;
4. les bloqueurs actifs et les décisions connexes ;
5. les adresses ARET permettant une lecture détaillée ;
6. le hash logique de l’état source, pour détecter une dérive d’export.

## 5. Critères d’acceptation V1.1 validés

| Test | Critère |
|---|---|
| Migration | Les briques existantes reçoivent les valeurs par défaut sans perte. |
| Validation de priorité | Les valeurs hors 1–5 sont refusées. |
| Filtrage | Les filtres jalon, composant et plateforme sont déterministes. |
| Graphe actif | Une relation `SUPERSEDED` ne crée pas de faux bloqueur dans la roadmap. |
| Borne | Une roadmap trop large est refusée ou paginée explicitement. |
| Export | Deux exports du même état donnent la même vue logique. |
| Absence | Une plateforme sans brique retourne une réponse explicite vide. |
| Non-régression | Les 29 outils V1, les 3 outils roadmap et les invariants `PROVEN` continuent de passer. |

## 6. Mise en œuvre réalisée

| Élément | État livré |
|---|---|
| Migration 005 | Appliquée au Store livré ; migration checksumée et incluse dans les bundles. |
| Métadonnées | Dix briques existantes classées de manière idempotente par jalon, cible et priorité. |
| Cycle de vie | `aret_update_brick` met à jour l’état et le classement avec audit. |
| Garde-fou Front | Une brique affichée dans le Front doit être `ACTIVE`; elle ne peut être désactivée avant remplacement du Front. |
| Lecture | `aret_get_roadmap` retourne une vue bornée et relations actives uniquement. |
| Export | `aret_export_roadmap` écrit une vue Markdown hashée dans les exports. |
| Tests | Tests de migration, filtrage, relations, export, priorité, Front et MCP stdio. |

## 7. Évolutions ultérieures

Une V1.2 éventuelle pourra ajouter une UI de portefeuille ou des vues d’impact plus riches lorsque le volume le justifiera. Les champs `responsable`, `date cible` et estimation de charge restent volontairement hors du canonique V1.1 afin de ne pas simuler une précision de planification inexistante.

## Références

[1]: MEMOIRE_STRATEGIQUE_CAPACITES_ET_ROADMAP.md "Convention V1 de mémoire stratégique"
[2]: ../core/repository.py "Briques, relations et lecture déterministe"
[3]: ../../../upload/pasted_content.txt "Recommandation Gemini sur la roadmap V1.1"

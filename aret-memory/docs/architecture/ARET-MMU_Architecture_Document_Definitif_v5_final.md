<br/>**ARET-MMU**

**Architecture définitive de mémoire persistante, contextuelle et probatoire pour ARET**

_De la mémoire documentaire monolithique à un Memory Store structuré, adressable et indépendant du LLM_

**Décision centrale —** La mémoire d'ARET ne doit plus être une collection de gros fichiers Markdown chargés en bloc, ni une mémoire sémantique probabiliste. Elle devient une base de connaissances structurée et persistante, servie par un MCP déterministe : SQLite est la source canonique, un index FTS facilite la découverte, des adresses stables permettent la récupération exacte, l'Active Front fournit la RAM chaude, et les preuves des oracles sont stockées séparément des affirmations.

Date : 19 août 2026
Statut : architecture cible v4 — consolidée après revue technique, prête à être prototypée

# Sommaire

- 1\. Résumé exécutif
- 2\. Problème à résoudre
- 3\. Analyse des quatre propositions explorées
- 4\. Décision d'architecture finale
- 5\. Principes fondamentaux
- 6\. Modèle conceptuel de la mémoire
- 7\. Modèle de données détaillé
- 8\. Statuts épistémiques et provenance
- 9\. Système d'adressage et pagination
- 10\. Active Front : la mémoire chaude
- 11\. Evidence Store : séparer mémoire et preuve
- 12\. Serveur MCP et contrat des outils
- 13\. Recherche déterministe : découverte vs récupération
- 14\. Écriture et gouvernance des mutations
- 15\. Audit, versionnage et reconstruction
- 16\. Migration des documents existants
- 17\. Cycle de vie d'une session Claude Code
- 18\. Reprise après compression / perte de contexte
- 19\. Exemple complet de diagnostic ARET
- 20\. Interface humaine et exports
- 21\. Sécurité et garde-fous
- 22\. Performance et coût de contexte
- 23\. Tests et critères d'acceptation
- 24\. Organisation du dépôt
- 25\. Feuille de route d'implémentation
- 26\. Évolutions futures
- 27\. Décisions finales et non-décisions

# 1\. Résumé exécutif

Décision désormais explicite : SQLite est la mémoire canonique d'ARET. Les anciens documents Markdown 70/71/80/81/91 ne font plus partie du chemin opérationnel cible ; ils servent de sources de migration initiale puis peuvent être archivés ou supprimés après validation des contrôles de migration.

Le problème n'est pas seulement que le contexte de Claude Code devient trop volumineux. Le problème architectural est que l'historique de travail d'ARET a progressivement été transformé en mémoire implicite de conversation : pour reprendre un projet après une compression, une expiration de session ou une interruption, il faut réinjecter de très grandes quantités de contexte. Cette stratégie fonctionne tant que la fenêtre de contexte reste confortable ; elle devient fragile dès que le projet dépasse cette échelle.

La solution proposée ici consiste à sortir définitivement la mémoire du projet du contexte du LLM. Les informations durables vivent dans un Memory Store local, structuré et versionné. Claude ne reçoit qu'un petit noyau de démarrage, le Front Actuel et les données paginées nécessaires à la tâche en cours. Le serveur MCP fournit l'interface entre le raisonnement et la mémoire.

La proposition finale combine quatre idées complémentaires : l'adressage/pagination de C-MMU, l'architecture ARET-MMU, la mémoire chaude Active Front de MemCore, et le typage épistémique de S.M.A.R.T. À cela s'ajoute une cinquième couche essentielle : l'Evidence Store, qui empêche de confondre ce qu'ARET sait avec ce qu'ARET a réellement prouvé.

| **Principe**     | **Décision finale**                                                                                              |
| ---------------- | ---------------------------------------------------------------------------------------------------------------- |
| Source de vérité | SQLite ARET Memory Store, pas des fichiers Markdown de référence.                                                |
| Recherche        | Index et FTS5 pour découvrir des éléments ; jamais utilisé comme preuve de pertinence.                           |
| Récupération     | Adresse stable + READ exact ; contenu brut et métadonnées.                                                       |
| Mémoire chaude   | Active Front minimal, toujours lisible en premier après reprise.                                                 |
| Statut           | Chaque connaissance porte un type et un statut épistémique.                                                      |
| Preuve           | Les résultats des oracles sont des objets séparés, produits par les outils eux-mêmes.                            |
| Écriture         | Append-first, mutations contraintes, auditées ; pas de réécriture libre par Claude.                              |
| Git              | Versionnage du schéma, des migrations et éventuellement des exports ; l'état logique est historisé dans la base. |
| Formats humains  | Markdown/HTML/JSON comme vues/export, pas comme stockage canonique.                                              |
| Indépendance     | La mémoire doit survivre à Claude, à une conversation, à une compression et à un changement d'outil.             |

# 2\. Problème à résoudre

## 2.1. Le modèle actuel

Le modèle documentaire de départ est efficace pour écrire et relire, mais il concentre des natures d'information différentes dans des documents numérotés. Le contexte nécessaire pour reprendre une tâche peut alors contenir des centaines de pages dont une petite partie seulement est utile à l'instant T.

Conversation / contexte Claude

↓

documents 70 / 71 / 80 / 81 / 91

↓

contexte massif

↓

attention diluée / compression

↓

risque de perte ou de reprise imparfaite

## 2.2. Les contraintes ARET

- Pas de mémoire sémantique qui pourrait associer deux fonctions ressemblantes sans preuve explicite.
- Pas de résumé LLM intermédiaire utilisé comme source de vérité.
- Pas d'information historique présumée correcte parce qu'elle "semble probable".
- Pas de perte silencieuse : une donnée absente doit être explicitement absente.
- Les résultats d'oracles restent distincts des déclarations de l'agent.
- La mémoire doit être indépendante de la durée de vie d'une session Claude.
- Le système doit être observable, reconstructible et auditable.

# 3\. Analyse des quatre propositions explorées

| **Proposition** | **Idée clé**                                  | **Évaluation**                                                                                                                                                                                                                  |
| --------------- | --------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| ARET-MMU        | Pagination de documents via MCP               | Très bonne fondation. Introduit le modèle "mémoire virtuelle". Faiblesse : trop centré sur la structure actuelle des MD et pas assez sur le statut des connaissances.                                                           |
| C-MMU           | Adressage canonique + séparation FIND/READ    | Meilleure formalisation du mécanisme de pagination. Introduit une propriété critique : découvrir n'est pas récupérer.                                                                                                           |
| MemCore         | SQLite + Active Front + écritures structurées | Très bonne idée pour la mémoire chaude et la discipline d'écriture. Faiblesse : tendance à faire de SQLite un remplacement direct des documents sans assez séparer mémoire, état et preuve.                                     |
| S.M.A.R.T.      | Mémoire typée par contrat                     | Très bonne idée pour distinguer règles, architecture, forensics, hypothèses, observations et états. Faiblesse : migration trop directe des fichiers vers une DB plate ; ontologie encore trop proche du découpage documentaire. |

La proposition définitive ne choisit donc pas un gagnant unique. Elle fusionne les primitives les plus robustes et refuse les hypothèses les plus fragiles de chacune.

# 4\. Décision d'architecture finale

## 4.1. Vision

CLAUDE

│

MCP

│

┌───────┴───────┐

│ ARET-MMU │

└───────┬───────┘

│

┌────────────────────┼────────────────────┐

│ │ │

▼ ▼ ▼

FRONT FIND READ

chaud découverte exact

│ │ │

└────────────────────┼────────────────────┘

▼

ARET MEMORY STORE

SQLite

│

┌───────────────────┼───────────────────┐

▼ ▼ ▼

Knowledge Evidence Audit

Store Store Log

## 4.2. Choix structurants

- La mémoire canonique est un store SQLite structuré ; le contenu narratif peut rester en Markdown dans le champ content, tandis que les propriétés métier (type, statut, tags, relations, provenance, dates, hashes) restent hors texte et sont contraintes par le schéma.
- SQLite est autoritatif ; FTS5, caches et index auxiliaires sont dérivés et reconstructibles. La suppression d'un index ne doit jamais détruire la connaissance.
- Les gros artefacts de preuve (logs, dumps, traces) restent sur le filesystem. SQLite ne conserve que leurs métadonnées, résultats, chemins et hashes.
- La découverte et la récupération sont explicitement séparées : FIND peut utiliser FTS5 et des filtres structurés ; READ/READ_BATCH chargent uniquement des objets adressés.
- Le protocole MCP fournit un outil READ_BATCH bornable par nombre d'objets et taille maximale afin de limiter les round-trips et les explosions de contexte.
- Une connaissance PROVEN est contrainte par la présence d'au moins une preuve admissible PASS ; Claude ne peut pas promouvoir librement un objet en PROVEN.
- Les connaissances historiques ne sont pas écrasées : les corrections utilisent de nouvelles versions et des relations SUPERSEDES.
- Les opérations d'écriture sont append-only et transactionnelles ; les commits Git restent hors du serveur mémoire et constituent une étape distincte.
- SQLite devient la source canonique de la mémoire persistante.
- Les anciens Markdown 70/71/80/81/91 sont migrés et deviennent de simples artefacts historiques ou exports éventuels.
- Un index secondaire est reconstruit à partir de SQLite ; toute donnée indexée doit pouvoir être régénérée.
- Les objets de connaissance sont identifiables, typés, versionnés et reliés entre eux.
- Les preuves d'exécution sont stockées séparément des connaissances et idéalement produites automatiquement.

Les hooks Claude Code sont un composant d'intégration du plugin ARET-MMU : SessionStart assure le bootstrap et la restauration, PreCompact prépare les checkpoints, et PostCompact assure la traçabilité de la compaction. Ils complètent le MCP sans devenir la source de vérité mémoire.

- Le protocole MCP offre des opérations métier de haut niveau, pas du SQL brut.

# 5\. Principes fondamentaux

| **Principe**                                      | **Interprétation**                                                                          |
| ------------------------------------------------- | ------------------------------------------------------------------------------------------- |
| P1 — La mémoire survit au LLM                     | Une session peut disparaître sans perte d'état du projet.                                   |
| P2 — Le modèle n'est pas la base                  | Claude est consommateur et opérateur de la mémoire, jamais sa source de vérité.             |
| P3 — Découverte ≠ récupération                    | Une recherche identifie des candidats ; une lecture adressée récupère exactement la donnée. |
| P4 — Rien de prouvé = rien d'affirmé comme prouvé | Le statut PROVEN exige une preuve exploitable.                                              |
| P5 — Les preuves sont externes au texte narratif  | Un test PASS est un objet d'évidence, pas une phrase saisie par l'agent.                    |
| P6 — Append-first                                 | L'histoire ne doit pas être réécrite arbitrairement.                                        |
| P7 — Les mutations sont transactionnelles         | Une écriture partielle ou incohérente ne doit pas laisser la base dans un état invalide.    |
| P8 — Reconstructible                              | Tout index/cache/vue doit être recréable depuis les données canoniques.                     |
| P9 — Observable                                   | Chaque mutation importante doit être auditée.                                               |
| P10 — Le contexte est un cache                    | Le contenu injecté dans Claude doit être considéré comme RAM temporaire.                    |

# 6\. Modèle conceptuel de la mémoire

La mémoire ARET n'est plus un "journal". Elle devient un petit système d'information d'ingénierie. Le journal, l'architecture, l'état courant et les forensics sont des vues spécialisées sur des objets structurés.

ARET KNOWLEDGE GRAPH

RULE ────── applies_to ──────> COMPONENT

│

├──── supersedes ───────────> RULE

│

└──── verified_by ──────────> PROOF

FORENSIC ── concerns ───────> FUNCTION

│

└──── caused_by ─────────> DECISION

OBSERVATION ── evolves_to ───> PROVEN_KNOWLEDGE

BRICK ── blocked_by ─────────> OPEN_WALL

Cette structure permet de remplacer le découpage documentaire "70 = état, 71 = journal, 80 = architecture" par un modèle métier. Les numéros de documents cessent d'être des concepts du système.

# 7\. Modèle de données détaillé

## 7.1. Entités principales

| **Objet**   | **Rôle**                                                                         |
| ----------- | -------------------------------------------------------------------------------- |
| knowledge   | Unité de connaissance durable : règle, décision, forensic, observation, etc.     |
| component   | Sous-système ARET : EH, ABI, GUI, GDI, loader, runtime C++, etc.                 |
| function    | Fonction ou symbole concret : \__except_handler3, \_except_handler4_common, etc. |
| brick       | Brique de travail planifiée et mesurable.                                        |
| proof       | Résultat d'un oracle ou d'une validation outillée.                               |
| relation    | Lien typé entre deux objets de connaissance ou entités.                          |
| front_state | État courant de travail, très petit et fortement volatile.                       |
| audit_event | Historique des mutations du Memory Store.                                        |
| tag         | Taxonomie normalisée de recherche et de regroupement.                            |

## 7.2. Schéma logique proposé

knowledge(

id TEXT PRIMARY KEY,

type TEXT NOT NULL,

status TEXT NOT NULL,

title TEXT NOT NULL,

content TEXT NOT NULL,

component_id TEXT,

created_at TEXT NOT NULL,

updated_at TEXT NOT NULL,

supersedes_id TEXT,

version INTEGER NOT NULL DEFAULT 1,

content_hash TEXT NOT NULL

)

knowledge_tag(

knowledge_id TEXT,

tag TEXT,

PRIMARY KEY (knowledge_id, tag)

)

relation(

id TEXT PRIMARY KEY,

from_id TEXT NOT NULL,

relation_type TEXT NOT NULL,

to_id TEXT NOT NULL,

created_at TEXT NOT NULL

)

proof(

id TEXT PRIMARY KEY,

kind TEXT NOT NULL,

command TEXT,

result TEXT NOT NULL,

stdout_ref TEXT,

stderr_ref TEXT,

artifact_path TEXT,

artifact_hash TEXT,

environment TEXT,

started_at TEXT,

finished_at TEXT,

created_by TEXT NOT NULL

)

proof_link(

knowledge_id TEXT,

proof_id TEXT,

PRIMARY KEY (knowledge_id, proof_id)

)

Contrainte métier critique : un objet knowledge ne peut être marqué PROVEN que s'il possède au moins un proof_link vers une preuve admissible dont result vaut PASS selon la politique d'ARET. Cette invariant doit être appliquée côté serveur et couverte par des tests.

Les chemins d'artefacts lourds sont relatifs à un répertoire d'artefacts dédié ; artifact_hash est le lien d'intégrité entre la métadonnée SQLite et le fichier physique.

front_state(

key TEXT PRIMARY KEY,

value TEXT NOT NULL,

updated_at TEXT NOT NULL,

updated_by TEXT NOT NULL

)

audit_event(

id TEXT PRIMARY KEY,

timestamp TEXT NOT NULL,

actor TEXT NOT NULL,

operation TEXT NOT NULL,

entity_type TEXT NOT NULL,

entity_id TEXT NOT NULL,

payload_before TEXT,

payload_after TEXT

)

# 8\. Statuts épistémiques et provenance

La mémoire doit indiquer non seulement le contenu d'une information, mais sa nature et son degré de consolidation.

| **Type**     | **Usage**                                         | **Exemple**                                                |
| ------------ | ------------------------------------------------- | ---------------------------------------------------------- |
| RULE         | Invariant ou contrainte normative                 | Un appel indirect non résolu doit avorter bruyamment.      |
| ARCHITECTURE | Choix structurel du système                       | Modèle shared-stack et conventions de passage de contexte. |
| DECISION     | Choix effectué et justifié                        | Préférence pour telle stratégie d'auto-lift.               |
| FORENSIC     | Analyse d'un problème passée ou en cours          | Cause racine d'une dérive ESP.                             |
| OBSERVATION  | Fait observé mais pas encore démontré causalement | Cette séquence apparaît dans les traces.                   |
| HYPOTHESIS   | Piste volontairement non prouvée                  | Le thunk pourrait être responsable.                        |
| STATE        | État courant d'un sous-système                    | EH brick 3 actif.                                          |
| MEASUREMENT  | Mesure brute ou agrégée                           | 1676 PE analysés, 133 clean.                               |
| DISCOVERY    | Découverte factuelle issue d'une exploration      | Import récurrent identifié dans le corpus.                 |

| **Statut**  | **Signification**                                                        |
| ----------- | ------------------------------------------------------------------------ |
| ACTIVE      | Actuellement pertinent.                                                  |
| PROVEN      | Confirmé par au moins une preuve référencée.                             |
| OBSERVED    | Observé mais pas encore causalement démontré.                            |
| HYPOTHESIS  | Hypothèse de travail.                                                    |
| SUPERSEDED  | Remplacé par une connaissance plus récente.                              |
| OBSOLETE    | N'est plus applicable.                                                   |
| CONFLICTING | Conflit explicite non résolu ; doit empêcher une conclusion silencieuse. |

Règle critique : PROVEN n'est pas une valeur que Claude peut obtenir en remplissant librement un champ. Le passage à PROVEN doit être relié à un ou plusieurs objets proof dont le résultat est acceptable selon la politique d'ARET.

# 9\. Système d'adressage et pagination

La mémoire doit posséder des identifiants stables, indépendants des numéros des anciens documents.

ARET://knowledge/EH-0042

ARET://component/EH

ARET://function/msvcrt!\__except_handler3

ARET://brick/EH-03

ARET://proof/P-884

ARET://front/current

## 9.1. Rôle de FIND

FIND est une opération de découverte. Elle peut combiner tags exacts, type, statut, composant, fonction, période, texte et FTS5. Le classement éventuel des résultats ne transforme jamais le résultat en preuve.

## 9.2. Rôle de READ

La primitive READ_BATCH(addresses\[\], max_items, max_bytes) complète READ. Elle récupère plusieurs pages déterministes en un seul round-trip MCP et refuse explicitement toute requête dépassant les bornes configurées.

FIND peut retourner des identifiants et des scores de découverte, mais READ_BATCH ne dépend d'aucun score : il restitue les adresses demandées et leur contenu exact.

READ reçoit une adresse connue et renvoie exactement l'objet correspondant, accompagné de son identité, de son statut, de sa provenance et de son hash. READ est le véritable équivalent d'un chargement de page.

# 10\. Active Front : la mémoire chaude

L'Active Front est volontairement minuscule. Son but n'est pas de résumer tout ARET, mais de dire où se trouve le travail immédiatement utile.

CURRENT FRONT

Subsystem: C++ EH

Brick: EH-03

Current wall: \__except_handler3

Last proven increment: EH-042

Known blocker: ...

Next measured action: ...

Relevant addresses:

ARET://knowledge/EH-042

ARET://knowledge/ABI-019

ARET://brick/EH-03

L'Active Front doit être considéré comme du cache chaud. S'il est perdu ou corrompu, il doit pouvoir être reconstruit ou corrigé sans perte de l'historique profond.

# 11\. Evidence Store : séparer mémoire et preuve

Les sorties volumineuses ne doivent jamais être stockées directement dans SQLite. Le modèle canonique conserve des références d'artefacts : chemin, hash, taille, type, et éventuellement un aperçu borné.

Un appel de preuve léger retourne par défaut : proof_id, kind, PASS/FAIL, exit_code, command, timestamps, artifact_path, artifact_hash et metadata d'environnement. La lecture du fichier lourd nécessite une opération explicite.

Cette séparation permet de conserver une base SQLite petite, rapide et facilement sauvegardable tout en gardant les journaux complets pour l'audit forensic.

C'est une exigence centrale de l'architecture finale. Le récit du projet et la preuve expérimentale sont deux catégories différentes.

KNOWLEDGE

EH-042

status = PROVEN

content = "..."

│

├── VERIFIED_BY ──> P-884 (difftest PASS)

├── VERIFIED_BY ──> P-885 (winediff PASS)

└── VERIFIED_BY ──> P-886 (funcdiff PASS)

Un proof doit idéalement contenir la commande, l'environnement, les horaires, le résultat, les sorties pertinentes et/ou une référence vers un artefact. Les preuves reproductibles et rejouables sont privilégiées.

**Règle anti-hallucination —** Claude peut proposer qu'une connaissance soit "prouvée", mais le serveur ne doit pas accepter ce statut sur la seule base d'un texte saisi par Claude.

# 12\. Serveur MCP et contrat des outils

Le serveur MCP est une façade métier. Claude ne doit pas manipuler directement SQL. Les outils exposés doivent correspondre aux concepts ARET.

| **Outil**                           | **But**                                                                     | **Lecture/écriture** |
| ----------------------------------- | --------------------------------------------------------------------------- | -------------------- |
| aret_boot()                         | Retourne doctrine minimale + métadonnées de fonctionnement du Memory Store. | Lecture              |
| aret_get_front()                    | Retourne l'Active Front.                                                    | Lecture              |
| aret_find(...)                      | Découvre des connaissances par critères structurés.                         | Lecture              |
| aret_read(address)                  | Charge exactement une ressource adressée.                                   | Lecture              |
| aret_get_forensics(...)             | Récupère les forensics d'un composant ou d'une fonction.                    | Lecture              |
| aret_get_proofs(knowledge_id)       | Retourne les preuves associées.                                             | Lecture              |
| aret_get_related(id, relation_type) | Traverse le graphe de relations.                                            | Lecture              |
| aret_append_knowledge(...)          | Ajoute une entrée structurée.                                               | Écriture contrôlée   |
| aret_update_front(...)              | Met à jour le Front, avec audit.                                            | Écriture contrôlée   |
| aret_record_proof(...)              | Enregistre une preuve produite par un outil de confiance.                   | Écriture contrôlée   |
| aret_export(...)                    | Produit une vue humaine ou machine.                                         | Lecture/export       |

## 12.1. aret_boot()

Le bootstrap doit rester très petit. Il n'est pas un résumé du projet. Il doit dire : qui est ARET, quelles sont les règles non négociables, comment interroger la mémoire, et où trouver le Front. Le détail est chargé ensuite.

## 12.2. aret_find()

Exemples de critères : component=EH, tag=ABI, type=FORENSIC, status=PROVEN, function=\__except_handler3, text=callee-pop, date range. Une requête vide ou ambiguë doit retourner explicitement "aucun résultat" plutôt que d'inventer.

## 12.3. aret_read()

## 12.4. aret_read_batch()

Charge plusieurs adresses connues dans un seul appel MCP. Les résultats sont indépendants, identifiés par adresse et soumis à des bornes max_items/max_bytes. Aucun résumé LLM n'est effectué.

## 12.5. aret_get_related()

Retourne les relations explicitement stockées pour un objet : VERIFIED_BY, SUPERSEDES, INFORMED_BY, BLOCKED_BY, IMPLEMENTS, DERIVED_FROM, etc. La relation elle-même est versionnée.

## 12.6. aret_get_proof() / aret_read_artifact()

aret_get_proof() retourne les métadonnées d'une preuve. aret_read_artifact() est réservé à la lecture explicite d'un artefact et peut lui-même être borné par taille.

READ est le syscall principal de pagination. Il ne fait pas de résumé. Il renvoie le contenu stocké et ses métadonnées, éventuellement avec une enveloppe courte.

# 13\. Recherche déterministe : découverte vs récupération

| **Étape**         | **Question**                                   | **Mécanisme**                                                    |
| ----------------- | ---------------------------------------------- | ---------------------------------------------------------------- |
| 1\. Découverte    | Quels objets pourraient être pertinents ?      | Tags, composants, texte exact, FTS5, filtres.                    |
| 2\. Sélection     | Quelle ressource vais-je réellement utiliser ? | L'agent choisit explicitement une adresse ou plusieurs adresses. |
| 3\. Récupération  | Quel est le contenu exact de cette ressource ? | READ adressé.                                                    |
| 4\. Qualification | Quel est son statut ?                          | Métadonnées type/status/provenance.                              |
| 5\. Preuve        | Cette information a-t-elle été validée ?       | Lien vers Evidence Store.                                        |

Cette séparation évite de confondre une recherche utile avec une preuve de vérité. C'est la transposition directe du principe "mesurer, pas deviner" au système de mémoire.

# 14\. Écriture et gouvernance des mutations

## 14.1. Phase initiale : lecture seule

Le premier prototype doit être read-only. L'objectif initial est de vérifier que le système retrouve mieux et coûte moins de contexte, sans introduire de nouveau risque sur la mémoire durable.

## 14.2. Phase suivante : append contrôlé

Claude

│

├── propose une observation / décision

▼

aret_append_knowledge(...)

│

├── validation schéma

├── normalisation tags

├── attribution ID

├── transaction

└── audit event

▼

ARET Memory Store

## 14.3. Pas de réécriture libre

Une mise à jour importante doit créer une nouvelle version ou un nouvel objet, puis marquer l'ancien comme SUPERSEDED. Cela conserve la traçabilité et évite qu'un agent réécrive silencieusement l'histoire.

## 14.4. Synchronisation Git contrôlée et automatique

Le stockage mémoire est placé dans un répertoire dédié du repository de travail, par défaut \`.aret-memory/\`. Après une mutation durable validée (connaissance appendée, preuve enregistrée et, lorsque requis, Active Front mis à jour), le composant de synchronisation ARET-MMU peut automatiquement versionner et pousser uniquement \`.aret-memory/\*\*\`. Il ne doit jamais stage, commit ou push du code source ou d'autres fichiers de travail appartenant à Claude. Le commit mémoire est donc automatique mais strictement borné au namespace ARET-MMU et intervient après validation transactionnelle et contrôles d'intégrité. Une politique \`auto_push=false\` reste disponible pour les environnements sans accès distant ou pour le développement local.

# 15\. Audit, versionnage et reconstruction

L'architecture cible doit permettre de reconstruire l'état et d'expliquer comment une donnée est arrivée dans le système.

- Chaque mutation importante génère un audit_event.
- Chaque objet de connaissance possède un hash de contenu.
- Les relations sont historisées.
- Les proofs référencent des commandes/artefacts lorsque possible.
- L'index FTS5 est régénérable.
- Le schéma SQL est versionné par migrations.

## 15.1. Reconstruction

Une propriété fondamentale : si l'index de recherche est supprimé, il doit être possible de le reconstruire intégralement à partir des tables canoniques. La reconstruction ne doit pas demander un LLM.

## 15.2. Persistance dans le repository et transfert inter-appareils

La persistance d'ARET-MMU ne doit pas être limitée à une machine ni à une VM cloud. Dans le mode opérationnel cible, la mémoire canonique locale est stockée directement dans un répertoire dédié du repository de travail : \`.aret-memory/\`. Le repository devient ainsi le canal primaire de persistance et de transport entre Claude Code Web, les environnements locaux et les autres postes autorisés. Une propriété de conception explicite est la capacité à fermer complètement Claude Code sur un appareil, ouvrir un environnement vierge sur un autre appareil et retrouver la même mémoire durable sans transférer la conversation LLM.

Le stockage canonique reste la base SQLite structurée placée sous \`.aret-memory/\`. Le repository Git est le mécanisme de persistance et de transport primaire : un clone ou un \`git pull\` récupère la mémoire durable exactement comme le code. Pour un transfert hors Git, une récupération d'urgence, une migration vers un autre repository ou un changement futur de backend, ARET-MMU fournit aussi un « Memory Bundle » portable contenant au minimum la base, le schéma/migrations applicables, un manifeste de version et les métadonnées nécessaires à la reconstruction des index. Les artefacts de preuve référencés peuvent être inclus dans le bundle ou exportés avec leurs hashes afin d'être recopiés indépendamment.

Le bundle doit être auto-décrit : memory_format_version, schema_version, db_hash, manifest_hash, created_at, source_device_id et liste des artefacts. db_hash désigne un hash logique/canonique du contenu structuré, et non une dépendance aux octets internes d'un fichier SQLite. Après import, ARET-MMU recalcule les hashes et refuse une importation incohérente.

Le système ne doit pas faire de synchronisation concurrente de deux copies SQLite vivantes. En revanche, plusieurs environnements peuvent utiliser le même repository comme canal de transport tant qu'une seule révision mémoire est publiée à la fois. La synchronisation Git est donc une synchronisation versionnée de snapshots/commits, pas un partage de fichier SQLite en écriture. Les conflits Git sur \`.aret-memory/\` doivent être détectés et refusés par l'outillage plutôt que résolus comme de simples conflits texte. Une future synchronisation multi-appareils temps réel pourra reposer sur un journal append-only d'événements ou un backend conçu pour résoudre les versions concurrentes, sans fusion binaire aveugle de SQLite.

Le changement d'appareil ne transfère donc pas le contexte de conversation. Il transfère l'état durable d'ARET : Active Front, connaissances, relations, preuves, audit et pointeurs. La session Claude elle-même reste jetable.

Flux cible normal : appareil A / Claude Code Web → mutation mémoire validée → \`.aret-memory/\` mis à jour → commit mémoire dédié → push Git → appareil B / nouvel environnement → \`git clone\` ou \`git pull\` → vérification de l'état mémoire → installation/activation ARET-MMU → \`SessionStart\[startup\]\` → \`restore()\` → reprise du travail. Flux de secours : \`aret export-bundle\` → fichier bundle signé/hashé → transfert sécurisé → \`aret import-bundle\` → vérification d'intégrité → reconstruction des index → \`SessionStart\[startup\]\` → reprise.

# 16\. Migration des documents existants

La migration des 70/71/80/81/91 ne doit pas être une conversion aveugle. Le but est de conserver le contenu et de l'augmenter d'une identité structurée.

| **Ancien document**            | **Nouvelle représentation principale**                                                |
| ------------------------------ | ------------------------------------------------------------------------------------- |
| 70 — état / stratégie          | STATE, BRICK, MEASUREMENT, DECISION                                                   |
| 71 — journal                   | FORENSIC, OBSERVATION, DECISION, DISCOVERY + dates + relations                        |
| 80 — architecture              | ARCHITECTURE + RULE + relations avec COMPONENT/FUNCTION                               |
| 81 — industrialisation / suivi | BRICK, COMPONENT, STATE, MEASUREMENT                                                  |
| 91 — référence consolidée      | Vue reconstruite automatiquement depuis STATE + RULE + MEASUREMENT + BRICK + DECISION |

## 16.1. Stratégie de migration

La migration est volontairement hybride au démarrage. Le journal 71 est découpé finement en objets individuels (FORENSIC, DECISION, OBSERVATION, PROOF_REFERENCE). Les documents plus narratifs 70, 80 et 91 peuvent d'abord devenir des objets ARCHITECTURE/STATE plus larges afin d'éviter une réécriture risquée.

Cette forme intermédiaire n'est pas la cible finale : la granularisation progressive est autorisée une fois les frontières métier et les relations démontrées. L'architecture ne dépend jamais de l'existence future des numéros 70/71/80/81/91.

Le champ content peut contenir le Markdown original pour conserver lisibilité et syntaxe de code, mais cette représentation textuelle n'est pas utilisée comme substitut aux colonnes structurées ni aux relations.

1. Parser les titres, dates, tags, sections et champs connus.
2. Créer des objets temporaires avec provenance vers l'emplacement d'origine.
3. Conserver le texte original dans le champ content lors de la première migration, sans reformulation.
4. Dédupliquer uniquement lorsque l'équivalence est démontrable ; sinon conserver deux objets avec relation potentielle.
5. Créer les relations de type SUPERSEDES lorsque la documentation les permet explicitement.
6. Calculer les hashes de contenu.
7. Construire l'index FTS5.
8. Comparer des exports de contrôle pour vérifier l'absence de pertes.
9. Après validation humaine, archiver les anciens MD hors du chemin opérationnel.

# 17\. Cycle de vie d'une session Claude Code

1\. SessionStart\[startup | resume | clear\]

↓

2\. Hook ARET-MMU → restore()

↓

3\. Core Context + Active Front injectés via additionalContext

↓

4\. Tâche utilisateur

↓

5\. FIND des connaissances pertinentes

↓

6\. READ / READ_BATCH des pages exactes

↓

7\. Modification du code

↓

8\. Exécution des oracles

↓

9\. RECORD des preuves

↓

10\. APPEND de la nouvelle connaissance / décision

↓

11\. UPDATE du Front

↓

12\. Fin de session

Le point important est que l'agent n'a pas besoin de charger l'ensemble de la mémoire pour commencer. Le bootstrap et la restauration du contexte chaud sont pris en charge au niveau Claude Code par les hooks ; les pages froides restent chargées à la demande via MCP.

# 18\. Reprise après compression / perte de contexte

## 18.1. Principe : la reprise doit être déclenchée par le runtime, pas par la mémoire du modèle

L'architecture cible ne repose plus sur une instruction du type « souviens-toi d'appeler aret_boot() ». Claude Code dispose d'un cycle de hooks explicite autour de la compaction : PreCompact avant la compaction, PostCompact après celle-ci, et SessionStart avec source=compact lors de la reprise après une compaction. La restauration du contexte utile est donc une responsabilité du mécanisme d'intégration ARET-MMU, et non une promesse comportementale faite au modèle.

## 18.2. Hook d'intégration installé avec ARET-MMU

Le paquet/plugin ARET-MMU installe les hooks Claude Code nécessaires. Le serveur MCP reste responsable de la mémoire et des opérations métier ; les hooks sont le mécanisme d'intégration au cycle de vie Claude Code. L'installation ne suppose donc pas que le serveur MCP puisse, à lui seul, modifier la configuration de Claude Code.

## 18.3. Démarrage et reprise normale

SessionStart\[startup | resume | clear\] → appel de l'opération de restauration ARET-MMU → récupération de l'Active Front et du Core Context → injection de additionalContext dans le contexte Claude.

Le contenu injecté reste minimal : règles invariantes, état chaud, pointeurs vers les pages pertinentes et version/hash de l'état mémoire. Le hook ne charge jamais le journal complet ni un sous-système entier par défaut.

## 18.4. Compaction automatique ou manuelle

PreCompact\[auto | manual\] peut enregistrer un checkpoint léger : identifiant de session, version du Front, état de la mémoire et métadonnées de l'événement. Son rôle est la traçabilité et la préparation de la reprise, pas l'injection de texte dans le nouveau contexte.

Après la compaction, SessionStart\[compact\] est le point d'entrée principal de restauration. Le hook appelle ARET-MMU et ajoute le résultat sous forme de additionalContext. Cette étape est déterministe du côté du système : elle ne dépend pas de la décision du modèle de penser à appeler manuellement aret_boot().

PostCompact\[auto | manual\] sert à enregistrer le résultat de la compaction et, si nécessaire, son compact_summary dans l'audit. PostCompact ne constitue pas le mécanisme d'injection : Claude Code ne lui permet pas de modifier le résultat de la compaction ni d'utiliser additionalContext à cet endroit.

## 18.5. Sources officielles prises en compte

La spécification s'appuie sur la documentation officielle Claude Code des hooks : SessionStart supporte les sources startup, resume, clear, compact et fork ; SessionStart peut fournir additionalContext ; PreCompact et PostCompact distinguent manual et auto ; PostCompact reçoit compact_summary mais ne dispose pas du contrôle de décision ni d'un mécanisme d'injection équivalent à SessionStart. Source : <https://code.claude.com/docs/en/hooks>

## 18.6. Flux cible

SESSION

↓

SessionStart\[startup/resume/clear\]

↓

ARET-MMU restore()

↓

Core Context + Active Front → additionalContext

↓

CLAUDE

Lors d'une compaction :

PreCompact\[auto/manual\] → checkpoint

↓

COMPACTION

↓

SessionStart\[compact\] → restore() → additionalContext

↓

CLAUDE reprend avec une mémoire chaude reconstruite

↘ PostCompact\[auto/manual\] → audit du compact_summary

## 18.7. Propriété de sûreté

Même si Claude oublie complètement l'existence d'ARET-MMU, la mémoire durable n'est pas perdue : elle vit dans SQLite et les artefacts de preuve. L'oubli du modèle peut dégrader une action locale ou retarder la découverte d'une page, mais il ne doit jamais supprimer ni réécrire silencieusement la mémoire canonique.

## 18.8. Fresh Session Handoff et transfert inter-appareils

La notion de reprise ne se limite pas à une nouvelle conversation sur la même machine. ARET-MMU définit explicitement un scénario « Fresh Session Handoff » : une session Claude totalement neuve doit pouvoir reprendre le travail à partir du Memory Store sans récupérer l'historique conversationnel précédent.

Sur le même appareil, SessionStart\[startup|resume|clear|compact\] recharge le Core Context et l'Active Front. Sur un appareil différent, la même mécanique s'applique après importation d'un Memory Bundle validé. La source de continuité est donc ARET-MMU, jamais le contexte de la session précédente.

Séquence cross-device : (1) la session A termine ou atteint un point de handoff ; (2) Active Front, preuves et état mémoire sont persistés ; (3) aret export-bundle produit un artefact portable ; (4) le bundle est transféré vers l'appareil B ; (5) ARET-MMU importe et vérifie le bundle ; (6) SessionStart\[startup\] déclenche restore() ; (7) additionalContext injecte le minimum nécessaire ; (8) Claude peut appeler FIND puis READ/READ_BATCH pour recharger les pages froides.

Le handoff est considéré réussi si, sur l'appareil B avec un contexte Claude vierge, un simple clone/pull du repository restaure un Memory Store cohérent et permet de retrouver au minimum : le même Active Front, les mêmes règles invariantes, les connaissances marquées PROVEN avec leurs preuves, les relations essentielles et les identifiants adressables des éléments de mémoire. Les tests ne demandent pas que la conversation soit reproduite.

Une conversation, même très longue, n'est donc jamais une dépendance de transport. Elle peut disparaître, être compactée ou rester sur l'appareil A sans compromettre la continuité du projet.

# 19\. Exemple complet de diagnostic ARET

Scénario : WinMerge rencontre une nouvelle dérive ESP dans une fonction liée au sous-système EH.

1\. Claude lit l'Active Front et constate que le Front courant est EH-03.

2\. Il recherche les forensics PROVEN sur le composant EH et les fonctions voisines.

3\. Il sélectionne explicitement trois adresses de connaissances.

4\. Il lit les pages exactes.

5\. Il inspecte le code et pose une hypothèse HYPOTHESIS, sans la classer PROVEN.

6\. Il exécute les portes ARET pertinentes.

7\. Les outils produisent les proofs P-901, P-902, etc.

8\. Le système rattache les proofs à la connaissance et autorise le passage à PROVEN.

9\. Claude append la nouvelle forensic, puis met à jour l'Active Front.

KNOWLEDGE EH-057

status: PROVEN

type: FORENSIC

tags: \[EH, ABI\]

title: ESP drift caused by ...

PROOFS

P-901 difftest: PASS

P-902 winediff: PASS

P-903 funcdiff: PASS

RELATIONS

EH-057 SUPERSEDES EH-041

EH-057 CONCERNS \__except_handler3

# 20\. Interface humaine et exports

La base n'a pas besoin d'être lisible directement pour être exploitable. En revanche, une interface humaine est souhaitable pour audit et maintenance.

- CLI : aret-memory list/find/read/show-front/show-proof/export.
- Export Markdown : pour produire des vues lisibles ponctuelles.
- Export HTML : pour navigation locale et revue humaine.
- Export JSON : pour outils et sauvegardes structurées.
- Éventuellement une UI web locale : graphe de relations, timeline, front, preuves.

Ces vues sont dérivées. Elles ne remplacent pas le stockage canonique.

# 21\. Sécurité et garde-fous

| **Risque**                      | **Garde-fou**                                                |
| ------------------------------- | ------------------------------------------------------------ |
| Claude invente un statut PROVEN | Statut calculé à partir de proofs valides.                   |
| Claude réécrit l'histoire       | Append/versioning ; interdiction de mise à jour destructive. |
| Données hors contexte           | Recherche suivie d'une lecture adressée.                     |
| Index corrompu                  | Index reconstructible.                                       |
| Base incohérente                | Transactions SQLite + contraintes SQL.                       |
| Outil MCP trop puissant         | API métier minimale ; pas de SQL arbitraire.                 |
| Commit accidentel               | Pas de commit Git implicite depuis MCP.                      |
| Conflit de connaissances        | Statut CONFLICTING + alerte explicite.                       |
| Dérive d'un export              | Hash et provenance conservés sur l'objet canonique.          |

# 22\. Performance et coût de contexte

La métrique cible n'est pas seulement "tokens minimaux". La métrique principale est le plus petit ensemble de connaissances correctement typées et suffisamment prouvées pour accomplir la prochaine action. Le système optimise donc la qualité du contexte, pas seulement son volume.

Les appels séquentiels nombreux sont à éviter : READ_BATCH est le mécanisme recommandé dès qu'un résultat FIND identifie plusieurs pages nécessaires.

L'objectif n'est pas de promettre un facteur fixe de réduction des tokens, car la consommation dépend de la tâche et du modèle. L'objectif architectural est de rendre le coût approximativement proportionnel aux données réellement nécessaires, plutôt qu'à la taille totale de l'historique.

| **Mode**           | **Ordre de grandeur conceptuel**                                   |
| ------------------ | ------------------------------------------------------------------ |
| Boot               | Quelques centaines de tokens.                                      |
| Front              | Quelques centaines de tokens.                                      |
| Lecture ciblée     | De quelques centaines à quelques milliers de tokens selon l'objet. |
| Recherche          | Petite réponse structurée, contenant IDs/adresses et métadonnées.  |
| Historique complet | Exceptionnel, sur demande explicite seulement.                     |

Le système doit éviter le réflexe "renvoyer tout le sous-système". Il faut préférer plusieurs lectures ciblées et explicites à un gros dump, tant que cela n'augmente pas excessivement le nombre d'appels.

# 23\. Tests et critères d'acceptation

## 23.1. Tests de mémoire

- Insertion → lecture exacte : le contenu relu est identique au contenu stocké.
- Index supprimé → reconstruction sans perte.
- Recherche tag exact → aucun faux positif dû à une similarité sémantique.
- Objet inconnu → réponse explicite "introuvable".
- Mutation → audit event présent.
- Versionnement → ancienne version conservée.

## 23.2. Tests de preuve

- Impossible de passer PROVEN sans preuve admissible.
- Suppression de proof → statut réévalué si la politique l'exige.
- Hash d'artefact conservé.

## 23.3. Tests de reprise

## 23.4. Tests de pagination et d'API MCP

- READ d'une adresse connue → contenu et hash identiques au contenu stocké.
- READ_BATCH → même résultat logique qu'une série de READ unitaires.
- Dépassement max_items/max_bytes → refus explicite, jamais dépassement silencieux.
- FIND → READ → READ_BATCH conserve la séparation découverte/récupération.

## 23.5. Tests du Memory Store lui-même

- Invariant PROVEN sans preuve admissible → transaction rejetée.
- SUPERSEDES → ancienne connaissance conservée et non effacée.
- Preuve invalidée → statut des connaissances liées réévalué selon politique.
- Base reconstruite depuis sauvegarde/snapshot → mêmes IDs, hashes et relations.
- Aucune opération destructive sur l'historique sans procédure administrative explicite.
- Session vide + boot + front → reprise du projet compréhensible.
- Contexte artificiellement amputé → lecture de pages permet la continuité.
- Base intacte avec cache conversationnel nul → aucune perte de connaissance durable.

## 23.6. Tests de transfert inter-appareils

- Exporter un Memory Bundle depuis A puis l'importer sur B doit restaurer le même db_hash logique/canonique et les mêmes identifiants canoniques.
- Un bundle tronqué, corrompu ou modifié doit être refusé avant activation.
- Après import, l'index FTS5 doit être reconstruit et produire les mêmes résultats déterministes qu'avant export pour un jeu de requêtes de référence.
- Les connaissances PROVEN doivent conserver leurs relations VERIFIED_BY et les preuves référencées doivent conserver leurs hashes.
- Une nouvelle session vide sur B doit retrouver l'Active Front sans nécessiter l'historique de A.
- Deux imports successifs du même bundle doivent être idempotents ou explicitement refusés selon une politique documentée.
- La synchronisation simultanée de deux SQLite vivants par simple copie de fichier doit être explicitement considérée comme un scénario interdit/non supporté en V1.

 \`git clone\` / \`git pull\` sur un repository valide restaure \`.aret-memory/\` et permet un démarrage neuf sans conversation précédente.

 Le sync automatique ne stage et ne pousse jamais de fichiers hors du namespace \`.aret-memory/\`.

 Une modification de code non liée à la mémoire n'est jamais incluse dans le commit mémoire automatique.

 Un conflit Git touchant \`.aret-memory/\` déclenche un refus de synchronisation et demande une résolution explicite.

 \`auto_push=false\` désactive le push automatique sans désactiver la persistance locale de la mémoire.

# 24\. Organisation du dépôt

aret-memory/
├── .aret-memory/
│ ├── aret_memory.sqlite
│ ├── manifest.json
│ └── artifacts/
├── schema/001_initial.sql
├── mcp/ (server.py, tools.py, policies.py)
├── sync/ (git_sync.py, conflict_guard.py)
├── core/ (model.py, repository.py, search.py, addressing.py)
├── evidence/ (adapters/, capture.py)
├── cli/aret-memory
├── export/ (markdown.py, html.py, json.py)
├── migration/ (import_70.py … import_91.py)
└── tests/ (repository, addressing, search, proofs, recovery)

# 25\. Feuille de route d'implémentation

| **Phase** | **Objectif**        | **Sortie**                                                                          |
| --------- | ------------------- | ----------------------------------------------------------------------------------- |
| Phase 0   | Décisions et schéma | Définir types, statuts, IDs, relations, politiques de proof.                        |
| Phase 1   | Read-only MCP       | boot, front, find, read. Aucune écriture.                                           |
| Phase 2   | Migration pilote    | Importer un sous-ensemble du journal + état + architecture et comparer les exports. |
| Phase 3   | Active Front        | Construire le Front à partir des objets structurés.                                 |
| Phase 4   | Evidence            | Brancher capture des difftest/Wine/winediff/funcdiff.                               |
| Phase 5   | Write contrôlé      | append knowledge, update front, record proof.                                       |
| Phase 6   | Migration complète  | Importer 70/71/80/81/91.                                                            |
| Phase 7   | Exports/UI          | CLI + HTML éventuellement.                                                          |
| Phase 8   | Durcissement        | Tests de reconstruction, corruption, conflits, reprise et politique de statuts.     |

La règle d'industrialisation doit rester la même que pour ARET : ne pas commencer par l'usine complète. Commencer par un brick minimal, mesurer, vérifier, puis élargir.

# 26\. Évolutions futures

- Graphe de dépendances et impact analysis sur les connaissances.
- Règles de dépréciation automatique des hypothèses anciennes.
- Snapshots signés ou hashés de l'état mémoire.
- Synchronisation entre plusieurs branches ou postes, avec gestion explicite des conflits.
- Connecteurs supplémentaires vers les sorties d'outils ARET.
- UI de forensic montrant chaîne Observation → Hypothesis → Fix → Proof → Proven.
- Export de rapports de référence reconstruits automatiquement.
- Policy engine pour interdire certaines mutations selon le statut des objets.

# 27\. Décisions finales et non-décisions

## 27.1. Décisions

- READ_BATCH fait partie du protocole cible pour réduire les round-trips MCP.
- Les logs/dumps/traces lourds restent hors SQLite ; seuls résultats, métadonnées, chemins et hashes sont canoniques dans la base.
- La migration initiale est hybride : journal granulaire, architecture narrative temporairement plus large, puis granularisation progressive.
- Le champ content peut rester en Markdown à l'intérieur de la base sans réintroduire les fichiers Markdown monolithiques comme mémoire primaire.
- La promotion PROVEN est un invariant de données, pas une simple convention de prompt.
- ARET-MMU possède sa propre suite de regression gates et ses propres invariants de soundness.
- Le stockage canonique de la mémoire est une base SQLite structurée.

 \`.aret-memory/\` fait partie du repository de travail et constitue le canal primaire de persistance inter-environnements.

 Après validation d'un incrément mémoire, ARET-MMU peut committer et pousser automatiquement uniquement \`.aret-memory/\*\*\`, jamais le code source ou les autres fichiers de travail.

- Les anciens gros Markdown ne font plus partie de l'architecture opérationnelle cible.
- Le MCP est la façade d'accès pour Claude.
- C-MMU fournit le modèle d'adressage et de pagination.
- L'Active Front fournit la mémoire chaude.
- Les types/statuts de S.M.A.R.T. fournissent la qualification épistémique.
- L'Evidence Store sépare les preuves des récits.
- L'index FTS5 est dérivé et reconstructible.
- Les écritures commencent en read-only puis append-only contrôlé.
- La mémoire doit survivre à Claude, aux conversations, aux redémarrages et aux changements d'appareil.

Les hooks Claude Code font partie de l'architecture d'intégration : SessionStart\[startup|resume|clear|compact\] déclenche la restauration ; PreCompact\[auto|manual\] prépare les checkpoints ; PostCompact\[auto|manual\] trace le résultat de la compaction.

PostCompact n'est pas utilisé comme mécanisme d'injection de contexte ; SessionStart\[compact\] est le point de restauration car SessionStart permet additionalContext.

Le plugin ARET-MMU installe les hooks ; le serveur MCP reste l'autorité métier sur la mémoire et ne dépend pas de la capacité à modifier lui-même la configuration Claude Code.

- Le transfert inter-appareils est une capacité native via Git et \`.aret-memory/\` ; le Memory Bundle reste le mécanisme de secours/migration. La V1 privilégie des révisions mémoire atomiques et séquentielles plutôt qu'une synchronisation concurrente de SQLite.
- La reprise sur une nouvelle machine ne transfère pas la conversation : un clone/pull du repository restaure la mémoire persistante, puis \`SessionStart\[startup\]\` reconstruit le contexte chaud. Le Memory Bundle est utilisé seulement lorsque le repository n'est pas disponible ou pour un transfert/migration hors Git.

## 27.2. Non-décisions

- Aucune dépendance au comportement volontaire du modèle pour déclencher la restauration après compaction : le plugin utilise les hooks Claude Code disponibles.
- Aucun engagement sur un format exact de configuration Claude Code sans validation de la version réellement utilisée.
- Aucune utilisation d'embeddings ou de RAG sémantique comme source de vérité.
- Aucune écriture concurrente sur un même SQLite par simple partage de fichier en V1. La persistance multi-appareils normale passe par Git et des commits mémoire dédiés ; toute évolution vers une synchronisation simultanée devra traiter les conflits au niveau des événements/versions.
- Aucun remplacement futur de la preuve par une note narrative de l'agent.

**Conclusion**

## Révision v5 — 19 août 2026

Ajout de la persistance canonique dans \`.aret-memory/\` au sein du repository de travail, de la synchronisation Git automatique et bornée aux données mémoire, du scénario Claude Code Web → machine locale, tout en conservant le Memory Bundle comme mécanisme de secours et de migration.

Cette version intègre la revue externe : lecture batch, externalisation des artefacts lourds, migration hybride, relations explicites, invariants PROVEN, bornes de pagination et tests spécifiques du Memory Store. Elle confirme également que SQLite est la mémoire canonique et que les anciens Markdown sont uniquement des sources de migration puis des exports optionnels. Elle remplace en outre l'ancien bootstrap fondé sur une instruction du modèle par une intégration de hooks Claude Code pour le bootstrap et la restauration après compaction.

La proposition définitive n'est pas une "mémoire pour Claude". C'est une infrastructure de connaissance pour ARET dans laquelle Claude devient un utilisateur intelligent mais non souverain de la mémoire. Le système sépare le stockage durable, l'état chaud, la découverte, la récupération exacte, les relations, et la preuve expérimentale. Cela permet de supprimer les documents monolithiques sans sacrifier l'auditabilité ni le principe "rien de prouvé = rien de deviné". La reprise après compaction est intégrée au cycle de vie Claude Code par SessionStart/PreCompact/PostCompact, ce qui réduit encore la dépendance à la mémoire implicite du modèle.

La conséquence la plus importante est conceptuelle : la longévité du projet ne dépend plus de la continuité d'une conversation. Si Claude oublie, compresse, redémarre ou change de session, l'état d'ARET reste présent, adressable et vérifiable.
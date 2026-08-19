# Contrat des adaptateurs d’oracles ARET-MMU

## Séparation des responsabilités

Un adaptateur ne reçoit jamais une commande shell arbitraire d’un client MCP. Il sélectionne un oracle dans une liste fermée, exécute son script depuis le dépôt ARET configuré, conserve la sortie dans un artefact hashé et construit le reçu HMAC attendu par le Memory Store. Le serveur reste le seul composant qui inscrit la preuve et qui peut associer cette preuve à une connaissance.

| Couche | Responsabilité | Interdiction |
|---|---|---|
| Adaptateur | Préflight, exécution déterministe, capture et signature locale | Interpréter une sortie libre comme une nouvelle connaissance |
| Evidence Store | Conserver métadonnées, hash, reçu, artefact et audit | Stocker les gros logs dans SQLite |
| Memory Store | Lier une preuve et autoriser `PROVEN` si l’invariant est satisfait | Promouvoir sur simple demande textuelle |
| Client MCP | Choisir un oracle et une connaissance à examiner | Fournir une commande non validée ou une signature |

## Oracles supportés

| Nom MCP | Script ARET | Dépendances minimales | Verdict PASS | Verdict SKIP |
|---|---|---|---|---|
| `difftest` | `bench/difftest.sh` | `bash`, `gcc`, binaire ARET | `differential equivalence: N/N functions`, avec `N > 0` | Dépendance absente ou sortie de skip explicite |
| `winediff` | `bench/winediff.sh` | `bash`, Wine, MinGW 32 bits, binaire ARET | `OS-API (Wine) equivalence: N/N programs`, avec `N > 0` | Toolchain ou corpus indisponible, ou skip explicite |
| `funcdiff` | `bench/funcdiff.sh` | `bash`, Cargo et corpus fonctionnel | `funcdiff corpus gate: PASS` | Dépendance/corpus indisponible, ou skip explicite |

Un script qui retourne une erreur, qui ne produit pas le résumé attendu ou dont le compteur est incomplet ne devient jamais `PASS`. Les cas indéterminés sont enregistrés `ERROR`; un échec mesuré est `FAIL`; un prérequis objectivement absent est `SKIPPED`.

## Artefact et reçu

Chaque exécution produit un fichier JSON sous `.aret-memory/artifacts/oracles/<oracle>/`. Il contient la commande réellement exécutée, les timestamps UTC, le code de retour, les sorties stdout/stderr, le verdict normalisé et l’environnement reproductible minimal. Son SHA-256 est inscrit dans le proof ; le reçu HMAC signe exactement l’enveloppe contrôlée par `MemoryStore.record_proof`.

L’absence de `ARET_PROOF_HMAC_SECRET` n’empêche pas la capture d’un résultat, mais le proof est alors conservé comme **non admissible**. Il ne peut pas produire ni justifier un statut `PROVEN`.

## Liaison et promotion

L’adaptateur peut recevoir l’identifiant d’une connaissance existante. Après enregistrement, le serveur ajoute `proof_link` et une relation `VERIFIED_BY`. Une promotion optionnelle ne s’exécute que si le nouveau proof est simultanément `PASS` et admissible. Toute autre combinaison est soit liée sans promotion, soit refusée si la promotion était demandée.

> Une preuve `FAIL`, `ERROR` ou `SKIPPED` est une donnée de diagnostic utile ; elle n’est jamais une justification de vérité et ne supprime ni ne réécrit la connaissance liée.

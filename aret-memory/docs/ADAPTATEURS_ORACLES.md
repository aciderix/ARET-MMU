# Adaptateurs d’oracles ARET-MMU

## Contrat de sûreté

L’Evidence Store exécute uniquement des oracles **codés dans un catalogue fermé**. Le client ne transmet ni shell, ni chemin de script, ni argument non validé. Il sélectionne un nom ; l’adaptateur résout la commande approuvée, contrôle les dépendances, borne le délai, capture la sortie dans un artefact JSON hashé et enregistre une preuve HMAC.

> Un oracle indisponible produit `SKIPPED`, pas un échec inventé. Un succès ne promeut une connaissance que s’il est `PASS` et si le reçu HMAC local est valide.

## Catalogue actuel

| Nom | Commande fermée | Objet contrôlé | Dépendances principales | Verdict positif reconnu |
|---|---|---|---|---|
| `difftest` | `bash bench/difftest.sh` | Équivalence différentielle de fonctions | `bash`, `gcc`, binaire ARET | `differential equivalence: N/N functions`, N > 0 |
| `transpilediff` | `bash bench/difftest_transpile.sh` | Pipeline transpile et hash comportemental | `bash`, `gcc`, binaire ARET | `transpile-pipeline equivalence: N/N opt-levels`, N > 0 |
| `stdcall_audit` | `bash bench/stdcall_audit.sh` | Cohérence des callee-pops `__stdcall` | `bash`, `python3`, `i686-w64-mingw32-nm` | `stdcall-pop audit: PASS` |
| `winediff` | `bash bench/winediff.sh` | Équivalence Win32 face à Wine | `bash`, Wine, MinGW i686, binaire ARET | `OS-API (Wine) equivalence: N/N programs`, N > 0 |
| `winehash` | `bash bench/winoracle/wine_hashes.sh` | Empreintes de corpus Wine à comparer au runner Windows | `bash`, Wine, MinGW i686 | `UNKNOWN`, volontairement non promouvable |
| `ehdiff` | `bash bench/ehdiff.sh` | SEH/EH MSVC et C++ | `bash`, `clang`, `lld-link`, `llvm-dlltool`, Wine, binaire ARET | `MSVC EH differential: N/N fixtures`, N > 0 |
| `gnuehdiff` | `bash bench/gnuehdiff.sh` | EH GNU/Itanium C++ | `bash`, `i686-w64-mingw32-g++`, Wine, binaire ARET | `GNU/Itanium C++ EH differential: N/N fixtures`, N > 0 |
| `funcdiff` | `bash bench/funcdiff.sh` | Fermeture de lift et optimisations sur corpus | `bash`, Cargo | `funcdiff corpus gate: PASS` |
| `cpudiff` | `cargo test --release --features unpack cpudiff` | Instructions et séquences CPU comparées à Unicorn | Cargo | `test result: ok` |

Les neuf commandes sont déclarées dans `evidence/adapters/oracles.py`. `cpudiff` est le seul oracle sans script shell : sa commande Cargo complète est tout de même stockée de façon statique dans le catalogue. Aucun paramètre utilisateur ne peut la modifier.

## Exécution et preuves

```text
aret_run_oracle(
  oracle="ehdiff",
  repository_path="/chemin/vers/Automatic-reverse-engineering-toolkit",
  knowledge_id="EH-0025",
  promote=false
)
```

Une fixture, lorsqu’elle est admise, est réduite à `[A-Za-z0-9_.-]` et ajoutée uniquement à l’oracle prévu. La sortie inclut le résultat normalisé, les dépendances manquantes, le timeout effectif, la référence de l’artefact et l’identifiant de preuve.

L’artefact est stocké sous :

```text
.aret-memory/artifacts/oracles/<oracle>/<horodatage>_<identifiant>.json
```

`aret_read_artifact` revalide son SHA-256 avant lecture. Les sorties lourdes sont ainsi hors SQLite, alors que la preuve conserve les métadonnées, le hash, le résultat et le reçu HMAC.

## Promotion

Une preuve `FAIL`, `ERROR`, `SKIPPED` ou `UNKNOWN` peut être conservée et liée pour l’audit mais ne permet pas une promotion. `winehash` est une mesure spécifique : même lorsqu’il retrouve toutes les empreintes attendues, son statut reste `UNKNOWN` jusqu’à comparaison par le runner Windows externe.

## Vérification locale

```bash
cd aret-memory
pytest -q tests/test_oracle_adapters.py tests/test_oracle_catalog.py
python3 evidence/adapters/oracles.py --help
```

Les tests vérifient le catalogue, l’existence des sources de chaque oracle, les signatures explicites de succès, les dépendances manquantes, le refus de promotion et la commande CPU figée. [1]

## Références

[1]: ../evidence/adapters/oracles.py "Catalogue fermé et normalisation des oracles"
[2]: ../tests/test_oracle_catalog.py "Tests du catalogue des neuf oracles"

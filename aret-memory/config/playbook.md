<!--
ARET-MMU — PLAYBOOK (source AUTORÉE des lois stables du projet)

CE FICHIER EST LA SOURCE. Il est chargé DIRECTEMENT au build du dossier de reprise ;
il n'est jamais ingéré dans SQLite (la base ne porte QUE la mémoire vivante :
connaissances, preuves, Front, journal, roadmap). Éditer ce fichier ne mute donc
jamais la mémoire SQLite — aucune dérive, aucun mauvais catalogage possible.

Format : une section = un domaine. Le domaine est déclaré EXPLICITEMENT dans le titre
`## <DOMAIN> — <libellé>` où <DOMAIN> ∈ { PLAYBOOK_FOUNDATION, PLAYBOOK_METHOD,
PLAYBOOK_ARCHITECTURE, PLAYBOOK_GATES, PLAYBOOK_TOOLING }. Les cinq domaines sont
obligatoires. Pour adapter ARET-MMU à un AUTRE projet : remplacer le contenu de ce
fichier (le moteur MMU — barrière, gating PROVEN, dossier — ne change pas).

Bornes : ce playbook doit tenir dans le cap du dossier de reprise (≤ 12 500 octets).
-->

# Playbook ARET — lois stables (incontournables)

## PLAYBOOK_FOUNDATION — Principe sacré §0 (non négociable, doc 70 §0)

1. **Jamais de sortie incorrecte présentée comme correcte.** Juste, ou **arrêt bruyant** (`aret_unmodelled`/`abort`). Jamais un no-op silencieux, jamais une valeur devinée. **Un faux silencieux est pire que rien.** Application : un import non implémenté **aborte** (`aret_unimpl`) ; canal distinct `aret_partial` pour une API **modélisée** dont un sous-cas ne l'est pas et qui rend un **échec défini**.
2. **Tout ce qui n'est pas sûr reste `Asm`/`__asm__` → abort** au runtime (statement *et* expression).
3. **Jamais de rustine par binaire.** On corrige la cause **générale** (une classe entière).
4. **Rien de prouvé = rien de deviné.** Mode d'arrondi x87, profondeur de pile, noreturn, cible d'appel indirect : non prouvé ⇒ fallback sûr **ou abort**, jamais une hypothèse optimiste.

**Garantie atteignable** : « fonctionnel, OU arrêt qui dit où — jamais faux en silence ». Le trio « tout binaire + 100 % fonctionnel + 100 % natif » est prouvé impossible (indécidabilité) ; le vrai logiciel compilé, lui, est pleinement atteignable.

## PLAYBOOK_METHOD — Doctrine §1 + méthode de travail §2 (doc 70)

**Doctrine — réutilisation vérifiée.** Valeurs = **Sound, Vérifié, Natif, Général**. Une brique réutilisée (Wine, Unicorn, code lifté) n'est **jamais** une boîte noire de confiance : ARET la **vérifie et emballe** dans « correct ou abort », **mêmes oracles** que du code maison. Wine **n'est pas un émulateur** (ses `.so` sont de l'ELF natif ; il sert d'**oracle**, jamais de runtime). Arbitrage honnête = la circularité « Wine oracle ET implémentation » → cassée par l'**oracle Windows réel** (GitHub Actions).

**Méthode (sans contournement).**
1. **Une tâche à la fois**, méthodique, pas de big-bang.
2. Par tâche : (a) comprendre/**reproduire** → (b) **fixture minimale testable** → (c) implémenter → (d) **vérifier** → (e) **commit descriptif** → (f) **enregistrer** (entrée mémoire datée+attribuée, et état/Front à jour).
3. **Ne jamais casser la régression.** Portes : `difftest` + `difftest_transpile` pour tout changement lift/structure ; lifter ⇒ **+ cpudiff + funcdiff** ; large ⇒ **+ regression + winediff**. **Aucune régression tolérée.**
4. **Commits petits, fréquents, poussés.** Le conteneur est éphémère : le non-committé est perdu au reset.

**Discipline stratégique** : **mesurer, ne pas affirmer** ; différentiel **large** obligatoire en zone critique (un test étroit masque les faux silencieux) ; **Borner puis pivoter** (dès qu'un bug n'est pas généralisable, documenter et passer) ; **pas de changement sans bénéfice mesuré** en zone correctness-critique ; **vérifier si le filet runtime est actif** avant de conclure à un abandon.

## PLAYBOOK_ARCHITECTURE — Modèle shared-stack + extensions gravées

**Modèle shared-stack (clé).** `esp` est passé **par valeur** aux fonctions liftées ; la pile machine est une **région unique partagée** ; `ebp` est **threadé** comme registre-paramètre (per-appel, thread-safe), de même que `esi/edi/ebx` callee-saved live-in. Le multithread se fait par **fibers coopératifs** (une seule coroutine court à la fois, pile machine par-fiber, état par-thread swappé par le scheduler). Sans `CreateThread`, tout reste strictement mono-thread (byte-identique).

**Chaîne transpile** : `PE loader` → `analysis` (récupération de fonctions, tables de saut) → `ir/lift.rs` (sémantique par-instruction) + `ir/build.rs` (esp/appels/frame) → `ssa` → `opt` → `emit` (`structured.rs` = C, `llvm.rs` = LLVM ; WASM via backend C) → recompilation ELF/WASM.

**Extensions gravées (doc 80 §3 / doc 81 §0)** :
- **Emballage obligatoire** : toute brique réutilisée/liftée/profilée reste « correct ou abort », vérifiée aux mêmes oracles.
- **PGL = opt-in**, jamais sur les démonstrateurs 100 %-statiques.
- **Parité WASM sound** : un mécanisme absent en WASM (`ucontext`, SEH matériel) ⇒ le build WASM **aborte proprement**, jamais ne diverge en silence.
- **Déterminisme préservé** (protège l'oracle) ; **licence** = décision externe consciente.
- **Zéro effet quand désactivé** : toute instrumentation gatée à la compile, off par défaut, **hash `19acad982194bf07` inchangé**.
- **Séparation des couches** : l'automatisation ABI/classification **alimente** l'analyse, ne **contamine** ni l'IR ni le lifter.

## PLAYBOOK_GATES — Portes de régression, invariants, leçons-qui-sont-des-portes

**Baseline transpile** : hash comportemental **`19acad982194bf07`** ; tout changement **strictement additif** doit le laisser **inchangé**. Un hash qui change sans intention = régression.

**Portes** : difftest (O0→O3) · difftest_transpile (4/4, hash) · cpudiff (Unicorn per-instruction + séquences) · funcdiff (closure + opt-diff, 0 divergence) · winediff (Wine, couverture OS-API) · gnuehdiff/ehdiff · stdcall_audit · smt_rewrites · magicdiv · regression. **Invariant oracle** : chemin non modélisé ⇒ l'oracle **skippe** (jamais un faux verdict) ; une divergence = un bug **prouvé**.

**Invariants (doc 82 §3)** : autonome au runtime (Wine/metadata servent à *fabriquer*, jamais à *exécuter*) ; tout extrait/porté est **vérifié contre l'oracle** ; hash transpile inchangé (additif) ; stdcall_audit PASS.

**Leçons qui sont des PORTES (non négociables)** :
- **Tout changement touchant recovery/lift passe `lift_libstdcxx` END-TO-END avant commit.** funcdiff est **closure-only** : il ne voit **pas** un miscompile de structuration/boucle. Seule l'exécution end-to-end du vrai binaire l'attrape. (Leçon ré-apprise 3 fois.)
- **Toute recovery ajoutée est risquée** (une fausse entrée tronque une vraie fonction → miscompile) ⇒ régression **complète** + gating byte-identique sur les binaires non concernés.
- **Tout changement de parallélisme se valide sur ≥3 exécutions complètes** (un défaut de concurrence est intermittent).
- **Avant de croire un rouge winediff, le relancer seul** (l'ORACLE Wine peut être vide sous charge ; qualifier la **nature** d'un rouge avant d'en tirer une cause).

## PLAYBOOK_TOOLING — Outils + leçons chèrement acquises (techniques)

**Modes** : `--mode transpile` (le produit) · `--mode verify/emit` (décompile) · `--mode imports` · `--mode walls` (carte statique des murs) · `bench/wallsweep.sh` (agrège sur corpus, `WALLSWEEP_COVERED`).
**Lifting DLL** : `--with-dll NAME=PATH` · `--auto-lift` (+ `--dll-path`) · affordances `.withlocaldll`/`.cpp`/`.serial`/`.def`/`.killat` · cache d'objets (`ARET_NO_OBJCACHE`/`ARET_OBJCACHE`) · tmpfs (`/dev/shm`).
**Diagnostic** : traceur **`ARET_TRACE=1`** (+ `ARET_TRACE_DUMP=N`) · relay **`ARET_RELAY=1`** (+ `WINEDEBUG=+relay` + `bench/relaydiff.py`) · **`ARET_DEBUG=1`** (-g DWARF) · `ARET_X87_DEBUG=1` · **winedbg (vérité Wine) ↔ gdb (ARET) sur mêmes adresses** · recompile `-O0 -g`.
**Oracles** : cpudiff · funcdiff · difftest/difftest_transpile · winediff · gnuehdiff/ehdiff · DIB-hash · écran virtuel (Xvfb+SDL) · **ORACLE WINDOWS** (GH Actions `windows-latest`) · sweeps.
**Générateurs** : `gen_stdcall_pops.py` · `gen_win32_sigs.py` (`--check`/`--skeleton`/`--marshal`) · `gen_wine_heavy.py` · `gen_mlang_cp.py` · `gen_cp1252/cp437.py`.
**Environnement** : hook `session-start.sh` auto-provisionne l'oracle (wine/mingw/`gcc -m32`/unicorn/zstd ; `libgd3:i386` demandé en premier).

**Leçons chèrement acquises (techniques)** :
- Un **`call` vers une fonction noreturn n'est PAS une preuve de frontière** (un landing pad EH est indistinguable). Frontière = terminateur **prouvé** (`ret`/`jmp`/`int3`) uniquement.
- **« Environnemental » n'est pas le critère — « gardable » l'est** : une donnée déterministe **balayée exhaustivement** est embarquable ; une donnée machine-dépendante ne l'est pas.
- **Deux commandes avant de lifter une DLL** (`__wine_spec_imp_` thunks **ET** `Forwarder RVA`) — sinon on lifte un relais-stub et le mur recule d'un module.
- Une **sonde** lisant un état global le **réinitialise avant chaque appel** ; **deux args d'un même `printf` touchant le même objet = bug** (ordre d'évaluation non spécifié).
- Le **cookie /GS** est un détecteur de dérive esp gratuit ; le **cache d'objets** est un détecteur de non-déterminisme (l'écart au taux de réutilisation attendu est un signal).
- **FIND ne prouve rien** ; **READ** récupère l'objet exact ; **PROVEN** exige une preuve PASS **admissible** (reçu HMAC). Le shell est un laboratoire : sa sortie n'est ni fait canonique ni preuve.

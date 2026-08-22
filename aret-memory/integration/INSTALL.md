# Intégration ARET-MMU dans un projet Claude Code

Ce dossier contient **tout le câblage** nécessaire pour activer la mémoire ARET-MMU
(serveur MCP + barrière de reprise) dans un projet Claude Code. Le paquet Python
(`aret-memory/`) porte la logique ; ces fichiers portent l'activation.

> Disposition attendue par défaut : le paquet est vendored sous
> `<racine-du-projet>/aret-memory/`. Rendre ce chemin configurable (pour toute
> autre disposition) est un chantier ultérieur — voir « Généralisation » en bas.

## Contenu

| Fichier | Destination dans le projet |
|---|---|
| `mcp.snippet.json` | fusionner dans le `.mcp.json` à la racine du projet |
| `claude/settings.snippet.json` | fusionner dans `.claude/settings.json` |
| `claude/hooks/*.sh` (7 fichiers) | copier dans `.claude/hooks/` |

Les 6 wrappers `aret-mmu-*.sh` sourcent le helper commun `aret-mmu-env.sh`, qui
expose `PYTHONPATH` vers le paquet (import **sans installation** : ni pip ni réseau
requis pour les hooks) et préfère `aret-memory/.venv/bin/python` s'il existe. C'est
ce qui garantit un démarrage fiable en **session web/cloud**, où le venv n'existe pas
encore quand `SessionStart` se déclenche.

## Étapes

1. **Prérequis** : Python 3.11+. Le paquet vendored sous `aret-memory/`.
2. **Copier les hooks** :
   ```bash
   mkdir -p .claude/hooks
   cp aret-memory/integration/claude/hooks/*.sh .claude/hooks/
   chmod +x .claude/hooks/aret-mmu-*.sh
   ```
3. **Fusionner** `mcp.snippet.json` dans `.mcp.json` (racine) et
   `claude/settings.snippet.json` dans `.claude/settings.json`. Si ces fichiers
   n'existent pas, créez-les avec le contenu du snippet.
4. **Vérifier** : ouvrez une session Claude Code à la racine du projet, approuvez le
   serveur `aret-memory` (`/mcp`), puis appelez `aret_boot`. À chaque démarrage/
   compaction, les hooks injectent le Resume Dossier et arment la barrière ; produisez
   le récapitulatif des six volets puis appelez `aret_acknowledge_resume`.

## Session web/cloud (Claude Code on the web)

Le `.mcp.json` et les hooks font partie du clone → ils se chargent automatiquement.
Sur `claude.ai/code`, réglez l'environnement une fois :

- **Network access = `Trusted`** (le lanceur MCP fait un `pip install -e` au premier
  démarrage ; avec `None` il échoue). Les hooks, eux, n'ont pas besoin du réseau.
- **Variables d'environnement** utiles :
  - `ARET_WRITE_ENABLED=true` pour autoriser l'écriture (défaut lecture seule).
  - `ARET_PROOF_HMAC_SECRET=…` pour signer les preuves `PROVEN` (jamais communiqué au modèle).
  - `ARET_MMU_BARRIER_OFF` — **sortie de secours** : `1`/`true`/`yes`/`on` désactive la
    barrière ; absente ou `0` = barrière active (normal). À n'utiliser que pour se
    débloquer si l'acquittement MCP est indisponible.

Optionnel, pour accélérer/fiabiliser le premier démarrage cloud (mis en cache), un
**Setup script** d'environnement :
```bash
cd "$CLAUDE_PROJECT_DIR/aret-memory" && python3 -m venv .venv && . .venv/bin/activate && pip install -e .
```

## Généralisation (chantier ultérieur, non fait ici)

Pour rendre le MMU adaptable à **toute** disposition de projet (paquet ailleurs que
`./aret-memory`, ou installé en paquet pip), l'évolution prévue est :
- une variable `ARET_MMU_HOME` pointant vers le paquet, avec repli sur le chemin
  vendored actuel (`aret_mmu_dir="${ARET_MMU_HOME:-${CLAUDE_PROJECT_DIR:-$(pwd)}/aret-memory}"`) ;
- une commande `aret-memory install-claude --project-dir .` qui pose les wrappers et
  fusionne les snippets automatiquement.

Ces éléments ne sont **pas** implémentés ici : ce dossier fournit le nécessaire
fonctionnel tel qu'utilisé par ARET aujourd'hui.

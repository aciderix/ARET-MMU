"""Armement FAIL-LOUD de la barrière de reprise.

Défaut historique (fail-open) : quand le dossier de reprise ne pouvait pas être
construit (mémoire vivante incomplète, ex. aucun handoff préparé), le hook
SessionStart/PostCompact LEVAIT avant d'armer la barrière → aucune garde n'était
posée → l'agent poursuivait SANS rituel, en silence. Ces tests verrouillent le
correctif : une mémoire incomplète produit un contexte DÉGRADÉ bruyant ET la
barrière est armée dans TOUS les cas.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from core.repository import MemoryStore

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def run_hook(name: str, memory_dir: Path, payload: dict[str, object] | None = None) -> dict[str, object]:
    body = {"memory_dir": str(memory_dir), **(payload or {})}
    completed = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "hooks" / name)],
        input=json.dumps(body), text=True, capture_output=True, check=True,
    )
    return json.loads(completed.stdout)


def _incomplete_store(memory_dir: Path) -> None:
    """Store valide mais SANS handoff préparé ⇒ dossier NON prêt (le playbook, lui,
    reste disponible depuis le fichier autoré empaqueté)."""
    store = MemoryStore(memory_dir, write_enabled=True)
    store.register_component("CORE", "Noyau", "Test", "test")
    store.update_front({
        "subsystem": "test", "current_wall": "validation",
        "last_action": "fixture incomplète", "next_action": "préparer le handoff",
    }, "test")
    # PAS de prepare_handoff : le contrat vivant est incomplet.


def _guard_state(memory_dir: Path) -> dict:
    guard_dir = memory_dir / "runtime" / "resume_guard"
    files = list(guard_dir.glob("*.json")) if guard_dir.is_dir() else []
    assert files, "aucune barrière armée : fail-open silencieux (régression)"
    return json.loads(files[0].read_text(encoding="utf-8"))


def test_session_start_arms_and_injects_even_when_dossier_not_ready(tmp_path: Path) -> None:
    memory_dir = tmp_path / "incomplete"
    _incomplete_store(memory_dir)

    started = run_hook("session_start.py", memory_dir, {"session_id": "sess-degraded"})

    assert started["ok"] is True                       # le hook ne tombe plus
    assert started["result"]["degraded"] is True       # état dégradé signalé
    context = started["hookSpecificOutput"]["additionalContext"]
    assert "REPRISE DÉGRADÉE" in context                # bruyant
    assert "aret_acknowledge_resume" in context         # rituel/barrière présents
    assert "arrêt bruyant" in context                   # les LOIS restent injectées (playbook fichier)

    state = _guard_state(memory_dir)                    # la barrière EST armée
    assert state["status"] == "awaiting_recap"
    assert len(state["resume_contract_hash"]) == 64


def test_post_compact_also_arms_when_dossier_not_ready(tmp_path: Path) -> None:
    memory_dir = tmp_path / "incomplete2"
    _incomplete_store(memory_dir)
    resumed = run_hook("post_compact.py", memory_dir, {"session_id": "sess-pc"})
    assert resumed["ok"] is True
    assert resumed["result"]["degraded"] is True
    assert "REPRISE DÉGRADÉE" in resumed["hookSpecificOutput"]["additionalContext"]
    state = _guard_state(memory_dir)
    assert state["status"] == "awaiting_recap"


def test_resume_context_or_degraded_never_raises(tmp_path: Path) -> None:
    sys.path.insert(0, str(PROJECT_ROOT / "hooks"))
    from common import resume_context_or_degraded  # import après ajout du chemin hooks

    memory_dir = tmp_path / "incomplete3"
    _incomplete_store(memory_dir)
    store = MemoryStore(memory_dir, write_enabled=True)
    context, degraded = resume_context_or_degraded(store)  # ne doit jamais lever
    assert degraded is True
    assert len(context["resume_dossier"]["contract_hash"]) == 64
    assert context["resume_dossier"]["ready"] is False

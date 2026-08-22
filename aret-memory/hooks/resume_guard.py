"""Garde déterministe de reprise ARET-MMU.

Le contexte de reprise est injecté depuis SQLite au démarrage et après compaction.
Le garde n'impose pas une relecture des documents ingérés : il exige uniquement
un récapitulatif structuré de ce contexte avant toute action de poursuite.
Son état est local et éphémère, sous `.aret-memory/runtime/`, jamais dans
SQLite ni Git.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


RITUAL_FIELDS: tuple[tuple[str, str, int], ...] = (
    ("working_rules", "règles de travail incontournables", 80),
    ("current_state", "état courant, Front et objectifs", 60),
    ("capabilities", "outils MCP, analyse, industrialisation et pipelines", 80),
    ("git_state", "branche, commits et état Git", 40),
    ("risks_and_limits", "limites, preuves et garde-fous", 60),
    ("next_action", "prochaine action proposée", 30),
)


_TRUTHY = {"1", "true", "yes", "on"}


def barrier_disabled() -> bool:
    """Kill-switch d'exploitation : une voie de sortie TOUJOURS disponible.

    Une barrière ne doit jamais pouvoir s'armer sans issue. Même en mode dur,
    si l'acquittement MCP est inatteignable (serveur non connecté), l'opérateur
    doit pouvoir lever la garde sans éditer de code : `ARET_MMU_BARRIER_OFF=1`.
    Vaut pour PreToolUse comme pour Stop.
    """
    return os.environ.get("ARET_MMU_BARRIER_OFF", "").strip().lower() in _TRUTHY


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def session_identity(payload: dict[str, Any]) -> str | None:
    """Retourne une identité de session explicite, ou None lorsqu’aucun scope n’est fourni."""
    for field in ("session_id", "transcript_path", "cwd"):
        value = str(payload.get(field) or "").strip()
        if value:
            return f"{field}:{value}"
    return None


def session_key(payload: dict[str, Any]) -> str:
    raw = session_identity(payload) or "unscoped"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def runtime_dir(memory_dir: Path) -> Path:
    path = memory_dir / "runtime" / "resume_guard"
    path.mkdir(parents=True, exist_ok=True)
    return path


def state_path(memory_dir: Path, payload: dict[str, Any]) -> Path:
    return runtime_dir(memory_dir) / f"{session_key(payload)}.json"


def load_state(memory_dir: Path, payload: dict[str, Any]) -> dict[str, Any] | None:
    path = state_path(memory_dir, payload)
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(value, dict) or value.get("version") != 3:
        return None
    return value


def _write_state(memory_dir: Path, payload: dict[str, Any], state: dict[str, Any]) -> None:
    path = state_path(memory_dir, payload)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    temporary.replace(path)


def arm(memory_dir: Path, payload: dict[str, Any], reason: str, resume_contract_hash: str, ready: bool = True) -> dict[str, Any]:
    """Arme une confirmation liée à l’empreinte du dossier réellement injecté.

    `ready` distingue deux modes, et c'est la leçon du deadlock vécu :
      - mode "hard" (dossier prêt) : le PreToolUse refuse toute action jusqu'à
        l'acquittement rituel — l'acquittement est alors sémantiquement possible.
      - mode "soft" (dossier DÉGRADÉ / non prêt) : la barrière reste ARMÉE et le
        contexte bruyant est injecté (fail-loud préservé), mais le PreToolUse NE
        BLOQUE PAS dur. Sur une mémoire cassée, imposer un rituel rigide sans
        voie de sortie fiable = deadlock. On avertit fort, on ne verrouille pas.
    """
    if len(resume_contract_hash) != 64 or any(char not in "0123456789abcdef" for char in resume_contract_hash):
        raise ValueError("Empreinte Resume Dossier invalide : hash SHA-256 hexadécimal requis")
    armed_at = utc_now()
    state = {
        "version": 3,
        "armed_at": armed_at,
        "reason": reason,
        "status": "awaiting_recap",
        "mode": "hard" if ready else "soft",
        "required_fields": [field for field, _, _ in RITUAL_FIELDS],
        "resume_contract_hash": resume_contract_hash,
        "acknowledged_at": None,
        "recap": None,
    }
    _write_state(memory_dir, payload, state)
    return state


def recap_from_input(payload: dict[str, Any]) -> dict[str, Any] | None:
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return None
    return tool_input


def validate_recap(recap: dict[str, Any]) -> dict[str, str]:
    """Valide une attestation de reprise sans prétendre juger sa sémantique.

    La validité factuelle du récapitulatif relève de l'agent ; le contrôle
    déterministe garantit les six volets du rituel et des contenus non triviaux.
    """
    normalized: dict[str, str] = {}
    failures: list[str] = []
    for field, label, minimum in RITUAL_FIELDS:
        value = recap.get(field)
        text = value.strip() if isinstance(value, str) else ""
        if len(text) < minimum:
            failures.append(f"{label} ({minimum} caractères minimum)")
        else:
            normalized[field] = text[:4000]
    if failures:
        raise ValueError("Récapitulatif de reprise incomplet : " + "; ".join(failures))
    return normalized


def is_resume_acknowledgement(payload: dict[str, Any]) -> bool:
    return str(payload.get("tool_name", "")).endswith("__aret_acknowledge_resume")


def _tool_succeeded(payload: dict[str, Any]) -> bool:
    response = payload.get("tool_response")
    if response is None:
        return True
    if isinstance(response, dict):
        if response.get("is_error") is True or response.get("isError") is True:
            return False
        structured = response.get("structured_content") or response.get("structuredContent")
        if isinstance(structured, dict) and structured.get("ok") is False:
            return False
    if isinstance(response, str) and '"ok":false' in response.replace(" ", "").lower():
        return False
    return True


def acknowledge(memory_dir: Path, payload: dict[str, Any]) -> dict[str, Any] | None:
    """Lève la garde seulement après une attestation MCP complète et réussie."""
    state = load_state(memory_dir, payload)
    if session_identity(payload) is None:
        return state
    if state is None or not is_resume_acknowledgement(payload) or not _tool_succeeded(payload):
        return state
    recap = recap_from_input(payload)
    if recap is None:
        return state
    try:
        normalized = validate_recap(recap)
    except ValueError:
        return state
    if recap.get("resume_contract_hash") != state.get("resume_contract_hash"):
        return state
    state["status"] = "acknowledged"
    state["acknowledged_at"] = utc_now()
    state["recap"] = normalized
    _write_state(memory_dir, payload, state)
    return state


def ritual_prompt(resume_contract_hash: str) -> str:
    fields = "; ".join(label for _, label, _ in RITUAL_FIELDS)
    return (
        "Le contexte de reprise a déjà été injecté depuis SQLite canonique : ne relisez pas les documents source. "
        "Avant toute action de poursuite, produisez un récapitulatif fidèle couvrant : " + fields + ". "
        "Puis appelez aret_acknowledge_resume avec les six champs correspondants et "
        f"resume_contract_hash={resume_contract_hash}."
    )


def decision(memory_dir: Path, payload: dict[str, Any]) -> dict[str, Any] | None:
    if barrier_disabled():
        return None
    state = load_state(memory_dir, payload)
    if state is None:
        return None
    if state.get("mode") == "soft":
        # Reprise DÉGRADÉE : le contexte bruyant a déjà été injecté à l'armement
        # (SessionStart/PostCompact) et le nudge Stop reste actif ; on n'impose
        # PAS de blocage dur sans voie de sortie fiable — c'est ce qui a deadlocké.
        return None
    if session_identity(payload) is None:
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": "BARRIÈRE DE REPRISE ARET-MMU : identité de session absente ; reprise refusée fail-closed.",
            }
        }
    if state.get("acknowledged_at"):
        return None
    if is_resume_acknowledgement(payload):
        return None
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": "BARRIÈRE DE REPRISE ARET-MMU : le récapitulatif rituel doit être confirmé avant toute action de poursuite.",
            "additionalContext": ritual_prompt(str(state.get("resume_contract_hash", ""))),
        }
    }


def stop_feedback(memory_dir: Path, payload: dict[str, Any]) -> dict[str, Any] | None:
    """Force une unique continuation lorsque l'agent tente de conclure sans récapitulatif.

    Actif en mode dur ET en mode soft (dégradé) : le nudge est informatif et
    borné à une seule passe (stop_hook_active) — il avertit sans jamais bloquer.
    Le kill-switch d'exploitation le désarme aussi.
    """
    if barrier_disabled():
        return None
    state = load_state(memory_dir, payload)
    if state is None or state.get("acknowledged_at") or payload.get("stop_hook_active") is True:
        return None
    return {
        "hookSpecificOutput": {
            "hookEventName": "Stop",
            "additionalContext": "BARRIÈRE DE REPRISE ARET-MMU ACTIVE : ne concluez pas et ne poursuivez pas encore. " + ritual_prompt(str(state.get("resume_contract_hash", ""))),
        }
    }


def memory_dir_from_env() -> Path:
    configured = os.environ.get("ARET_MEMORY_DIR") or ".aret-memory"
    return Path(configured).expanduser().resolve()

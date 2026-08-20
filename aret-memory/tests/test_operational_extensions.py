from __future__ import annotations

import json
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from core.repository import AretError, MemoryStore
from ops.git_memory import GitMemoryError, commit, status


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PLAYBOOK_PADDING = (
    " Cette règle est stable, s’applique à tout incrément, exige une preuve reproductible et "
    "interdit tout succès silencieux, toute valeur inventée ou toute conclusion non auditée."
)


def run_hook(name: str, memory_dir: Path, payload: dict[str, object] | None = None) -> dict[str, object]:
    body = {"memory_dir": str(memory_dir), **(payload or {})}
    completed = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "hooks" / name)],
        input=json.dumps(body), text=True, capture_output=True, check=True,
    )
    return json.loads(completed.stdout)


def populated_store(memory_dir: Path) -> MemoryStore:
    store = MemoryStore(memory_dir, write_enabled=True)
    store.register_component("CORE", "Noyau", "Test", "test")
    store.append_knowledge(
        knowledge_type="OBSERVATION", status="OBSERVED", title="Objet de test", content="Contenu canonique.",
        component_id="CORE", function_id=None, brick_id=None, tags=["TEST"], proof_ids=[], supersedes_id=None, actor="test",
    )
    playbook = (
        ("PLAYBOOK_FOUNDATION", "Règle fondatrice", "Juste ou arrêt bruyant, jamais de valeur inventée."),
        ("PLAYBOOK_METHOD", "Méthode", "Mesurer, reproduire, vérifier et documenter chaque incrément."),
        ("PLAYBOOK_ARCHITECTURE", "Architecture", "Wine est une source et un oracle, jamais une dépendance runtime."),
        ("PLAYBOOK_GATES", "Gates", "Les oracles requis valident chaque modification pertinente."),
        ("PLAYBOOK_TOOLING", "Outils", "Les outils de mesure sont utilisés avant toute conclusion."),
    )
    for domain, title, content in playbook:
        tags = ["CORE_PLAYBOOK", domain]
        if domain == "PLAYBOOK_ARCHITECTURE":
            tags.append("PLAYBOOK_SHARED_STACK")
        store.append_knowledge(
            knowledge_type="ARCHITECTURE" if domain == "PLAYBOOK_ARCHITECTURE" else "RULE",
            status="ACTIVE", title=title, content=content + PLAYBOOK_PADDING, component_id="CORE", function_id=None,
            brick_id=None, tags=tags, proof_ids=[], supersedes_id=None, actor="test",
        )
    store.update_front({
        "subsystem": "test", "current_wall": "validation", "last_action": "fixture initialisée",
        "next_action": "Confirmer le handoff", "relevant_1_address": "ARET://knowledge/CORE-0001",
    }, "test")
    store.prepare_handoff(
        work_summary="La fixture de reprise a préparé un playbook et un handoff actifs.",
        verified_results="Les objets de test ont été enregistrés dans SQLite canonique.",
        open_risks="Aucun risque bloquant de fixture n’est connu.",
        deferred_items="Aucun élément de fixture n’est différé.",
        next_action="Exécuter le hook et confirmer le rituel de reprise.",
        technical_checkpoint_state="NONE",
        relevant_addresses=["ARET://knowledge/CORE-0001"], actor="test",
    )
    return store


def test_hooks_are_read_only_and_return_structured_context(tmp_path: Path) -> None:
    memory_dir = tmp_path / "source"
    populated_store(memory_dir)
    started = run_hook("session_start.py", memory_dir)
    compacted = run_hook("pre_compact.py", memory_dir, {"audit_limit": 3})
    resumed = run_hook("post_compact.py", memory_dir)
    assert started["ok"] is True
    assert compacted["ok"] is True
    assert resumed["ok"] is True
    assert started["result"]["front"]["relevant_addresses"] == ["ARET://knowledge/CORE-0001"]
    assert compacted["result"]["read_after_resume"] == ["ARET://knowledge/CORE-0001"]
    assert resumed["result"]["relevant_addresses"] == ["ARET://knowledge/CORE-0001"]
    assert started["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert resumed["hookSpecificOutput"]["hookEventName"] == "PostCompact"
    assert "RITUEL OBLIGATOIRE AVANT TOUTE POURSUITE" in resumed["hookSpecificOutput"]["additionalContext"]


def test_git_memory_commit_is_explicit_and_scope_limited(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    subprocess.run(["git", "init"], cwd=repository, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "aret@example.test"], cwd=repository, check=True)
    subprocess.run(["git", "config", "user.name", "ARET Test"], cwd=repository, check=True)
    memory = repository / "aret-memory" / ".aret-memory"
    memory.mkdir(parents=True)
    (memory / "state.txt").write_text("canonique", encoding="utf-8")

    initial = status(repository, "aret-memory/.aret-memory")
    assert initial["safe_to_commit_memory_only"] is True
    result = commit(repository, "aret-memory/.aret-memory", "Sauvegarde mémoire", True)
    assert result["committed"] is True

    (repository / "hors_perimetre.txt").write_text("interdit", encoding="utf-8")
    with pytest.raises(GitMemoryError, match="hors du Memory Store"):
        commit(repository, "aret-memory/.aret-memory", "Doit échouer", True)


def test_bundle_round_trip_is_verified_idempotent_and_non_merging(tmp_path: Path) -> None:
    source_dir = tmp_path / "source"
    source = populated_store(source_dir)
    artifact = source.artifacts_dir / "diagnostic.txt"
    artifact.write_text("preuve externe", encoding="utf-8")
    bundle = source.export_bundle("round_trip")

    target_dir = tmp_path / "target"
    target = MemoryStore(target_dir, write_enabled=True)
    imported = target.import_bundle(bundle["path"], "test")
    assert imported["imported"] is True
    assert target.read("ARET://knowledge/CORE-0001")["content"] == "Contenu canonique."
    assert (target.artifacts_dir / "diagnostic.txt").read_text(encoding="utf-8") == "preuve externe"
    assert target.import_bundle(bundle["path"], "test")["idempotent"] is True

    source.append_knowledge(
        knowledge_type="OBSERVATION", status="OBSERVED", title="Objet suivant", content="Nouvelle version.",
        component_id="CORE", function_id=None, brick_id=None, tags=["TEST"], proof_ids=[], supersedes_id=None, actor="test",
    )
    different_bundle = source.export_bundle("different")
    with pytest.raises(AretError, match="n’est pas vide"):
        target.import_bundle(different_bundle["path"], "test")

    tampered = tmp_path / "altered.bundle.zip"
    with zipfile.ZipFile(bundle["path"], "r") as original, zipfile.ZipFile(tampered, "w") as altered:
        for member in original.infolist():
            data = original.read(member.filename)
            if member.filename == "snapshot.json":
                data = b"{}\n"
            altered.writestr(member, data)
    fresh = MemoryStore(tmp_path / "fresh", write_enabled=True)
    with pytest.raises(AretError, match="snapshot"):
        fresh.import_bundle(tampered, "test")

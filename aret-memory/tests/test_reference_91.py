from __future__ import annotations

import pytest

from core.repository import MemoryStore
from migration.import_doc91 import Document91Unavailable, inspect_source


def test_reference_91_is_reconstructed_from_canonical_objects(tmp_path) -> None:
    store = MemoryStore(tmp_path / ".aret-memory", write_enabled=True)
    store.register_component("CORE", "Core", "", "test")
    store.register_brick("BRICK-1", "Brique de référence", "PLANNED", "CORE", "", "test")
    store.append_knowledge(
        knowledge_type="STATE", status=None, title="État de référence", content="Le contenu canonique.",
        component_id="CORE", function_id=None, brick_id=None, tags=None, proof_ids=None,
        supersedes_id=None, actor="test",
    )

    exported = store.export_reference_91("reference_91_test")
    content = (tmp_path / ".aret-memory" / "exports" / "reference_91_test.md").read_text(encoding="utf-8")

    assert exported["format"] == "reference_91"
    assert exported["knowledge_count"] == 1
    assert "# 91 — Référence ARET reconstruite" in content
    assert "État de référence" in content
    assert "BRICK-1" in content


def test_doc91_import_preparation_refuses_to_invent_missing_source(tmp_path) -> None:
    with pytest.raises(Document91Unavailable, match="Document 91 indisponible"):
        inspect_source(tmp_path / "docs" / "vision" / "91-reference-consolidee.md")

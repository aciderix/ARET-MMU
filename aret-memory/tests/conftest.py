"""Configuration des tests ARET-MMU.

Le serveur MCP est autonome. Cinq tests d’intégration vérifient toutefois les importeurs
contre les documents, corpus et scripts du dépôt ARET principal, volontairement exclu de
ce dépôt public. Ils sont exécutés automatiquement lorsque le checkout courant contient
ces sources ; dans un clone MCP isolé, ils sont signalés comme `skipped` avec une raison
explicite plutôt que d’échouer de manière trompeuse.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest


EXTERNAL_SOURCE_TESTS = {
    "test_document_migration.py",
    "test_journal71_migration.py",
    "test_references_70_80_81_migration.py",
    "test_trackers_82_90_migration.py",
    "test_oracle_catalog.py",
}


def external_aret_repository() -> Path:
    """Retourne le dépôt ARET externe demandé par l’environnement, ou le parent historique."""
    configured = os.environ.get("ARET_SOURCE_REPOSITORY")
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parents[2]


def source_ready(root: Path) -> bool:
    return (
        (root / ".git").exists()
        and (root / "docs" / "vision" / "70-reference-etat-methode-reste.md").is_file()
        and (root / "docs" / "vision" / "71-journal-de-bord.md").is_file()
        and (root / "bench" / "difftest.sh").is_file()
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    root = external_aret_repository()
    if source_ready(root):
        return
    reason = (
        "nécessite le dépôt ARET principal séparé (définissez ARET_SOURCE_REPOSITORY "
        "vers un checkout ARET complet pour exécuter les tests d’import et de catalogue externes)"
    )
    marker = pytest.mark.skip(reason=reason)
    for item in items:
        if Path(str(item.fspath)).name in EXTERNAL_SOURCE_TESTS:
            item.add_marker(marker)

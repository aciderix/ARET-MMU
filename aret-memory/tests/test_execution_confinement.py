from __future__ import annotations

from pathlib import Path

import aret_mmu_server as server
from core.repository import MemoryStore


def _write_script(path: Path, marker: Path, label: str, output: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        f"printf '%s\\n' {label!r} >> {str(marker)!r}\n"
        f"printf '%s\\n' {output!r}\n",
        encoding="utf-8",
    )
    path.chmod(0o755)


def _repository(path: Path, marker: Path, label: str) -> Path:
    binary = path / "target" / "release" / "aret"
    binary.parent.mkdir(parents=True, exist_ok=True)
    binary.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    binary.chmod(0o755)
    _write_script(path / "bench" / "difftest.sh", marker, label, "differential equivalence: 1/1 functions")
    _write_script(path / "bench" / "regression.sh", marker, label, "regression gate: PASS")
    return path


def _configured_server(monkeypatch, repository: Path) -> None:
    memory_dir = repository / "aret-memory" / ".aret-memory"
    monkeypatch.setattr(server, "store", MemoryStore(memory_dir, write_enabled=True))


def test_oracle_repository_path_and_resolved_script_stay_under_configured_repository(tmp_path: Path, monkeypatch) -> None:
    marker = tmp_path / "executed.log"
    configured = _repository(tmp_path / "configured", marker, "CONFIGURED")
    outside = _repository(tmp_path / "outside", marker, "OUTSIDE")
    _configured_server(monkeypatch, configured)

    allowed = server.aret_run_oracle("difftest")
    assert allowed["ok"] is True
    assert marker.read_text(encoding="utf-8").splitlines() == ["CONFIGURED"]

    for candidate in (outside, configured / ".." / "outside"):
        refused = server.aret_run_oracle("difftest", repository_path=str(candidate))
        assert refused["ok"] is False
        assert "dépôt ARET configuré" in refused["error"]["message"]

    repository_link = configured / "outside-link"
    repository_link.symlink_to(outside, target_is_directory=True)
    refused_link = server.aret_run_oracle("difftest", repository_path=str(repository_link))
    assert refused_link["ok"] is False

    configured_script = configured / "bench" / "difftest.sh"
    configured_script.unlink()
    configured_script.symlink_to(outside / "bench" / "difftest.sh")
    refused_script = server.aret_run_oracle("difftest")
    assert refused_script["ok"] is False
    assert "hors du dépôt ARET configuré" in refused_script["error"]["message"]
    assert marker.read_text(encoding="utf-8").splitlines() == ["CONFIGURED"]


def test_pipeline_repository_path_and_resolved_script_stay_under_configured_repository(tmp_path: Path, monkeypatch) -> None:
    marker = tmp_path / "executed.log"
    configured = _repository(tmp_path / "configured", marker, "CONFIGURED")
    outside = _repository(tmp_path / "outside", marker, "OUTSIDE")
    _configured_server(monkeypatch, configured)

    allowed = server.aret_run_pipeline("run_regression_gate", dry_run=False)
    assert allowed["ok"] is True
    assert marker.read_text(encoding="utf-8").splitlines() == ["CONFIGURED"]

    for candidate in (outside, configured / ".." / "outside"):
        refused = server.aret_run_pipeline("run_regression_gate", dry_run=False, repository_path=str(candidate))
        assert refused["ok"] is False
        assert "dépôt ARET configuré" in refused["error"]["message"]

    repository_link = configured / "outside-link"
    repository_link.symlink_to(outside, target_is_directory=True)
    refused_link = server.aret_run_pipeline("run_regression_gate", dry_run=False, repository_path=str(repository_link))
    assert refused_link["ok"] is False

    configured_script = configured / "bench" / "regression.sh"
    configured_script.unlink()
    configured_script.symlink_to(outside / "bench" / "regression.sh")
    refused_script = server.aret_run_pipeline("run_regression_gate", dry_run=False)
    assert refused_script["ok"] is False
    assert "hors du dépôt ARET configuré" in refused_script["error"]["message"]
    assert marker.read_text(encoding="utf-8").splitlines() == ["CONFIGURED"]

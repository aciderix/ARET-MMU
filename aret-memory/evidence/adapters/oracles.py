"""Adaptateurs déterministes des oracles ARET vers l’Evidence Store.

Les scripts sont choisis dans une liste fermée. Aucune commande arbitraire ni secret de
signature n’est accepté depuis un client MCP.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.repository import AretError, MemoryStore
from evidence.capture import create_receipt


@dataclass(frozen=True)
class OracleSpec:
    name: str
    kind: str
    script: str | None
    dependencies: tuple[str, ...]
    timeout_seconds: int
    accepts_fixture: bool = False
    requires_aret_binary: bool = False
    command: tuple[str, ...] | None = None


ORACLES: dict[str, OracleSpec] = {
    "difftest": OracleSpec("difftest", "DIFFTEST", "bench/difftest.sh", ("bash", "gcc"), 1800, requires_aret_binary=True),
    "transpilediff": OracleSpec("transpilediff", "TRANSPILEDIFF", "bench/difftest_transpile.sh", ("bash", "gcc"), 1800, requires_aret_binary=True),
    "stdcall_audit": OracleSpec("stdcall_audit", "STDCALL_AUDIT", "bench/stdcall_audit.sh", ("bash", "python3", "i686-w64-mingw32-nm"), 1800),
    "winediff": OracleSpec("winediff", "WINEDIFF", "bench/winediff.sh", ("bash", "wine", "i686-w64-mingw32-gcc"), 3600, True, True),
    "winehash": OracleSpec("winehash", "WINEHASH", "bench/winoracle/wine_hashes.sh", ("bash", "wine", "i686-w64-mingw32-gcc"), 3600, requires_aret_binary=False),
    "ehdiff": OracleSpec("ehdiff", "EHDIFF", "bench/ehdiff.sh", ("bash", "clang", "lld-link", "llvm-dlltool", "wine"), 3600, requires_aret_binary=True),
    "gnuehdiff": OracleSpec("gnuehdiff", "GNUEHDIFF", "bench/gnuehdiff.sh", ("bash", "i686-w64-mingw32-g++", "wine"), 3600, requires_aret_binary=True),
    "funcdiff": OracleSpec("funcdiff", "FUNCDIFF", "bench/funcdiff.sh", ("bash", "cargo"), 1800),
    "cpudiff": OracleSpec("cpudiff", "CPUDIFF", "src/cpudiff.rs", ("cargo",), 3600, command=("cargo", "test", "--release", "--features", "unpack", "cpudiff")),
}


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def repository_revision(repository: Path) -> str:
    result = subprocess.run(["git", "-C", str(repository), "rev-parse", "HEAD"], text=True, capture_output=True, check=False)
    return result.stdout.strip() if result.returncode == 0 else "UNKNOWN"


def _repository_file(repository: Path, relative_path: str, label: str) -> Path:
    """Résout un fichier d’oracle et refuse toute sortie du dépôt configuré."""
    root = repository.resolve()
    candidate = (root / relative_path).resolve()
    if candidate != root and root not in candidate.parents:
        raise AretError(f"{label} résolu hors du dépôt ARET configuré")
    return candidate


def required_tools(spec: OracleSpec, repository: Path) -> list[str]:
    missing = [tool for tool in spec.dependencies if shutil.which(tool) is None]
    if spec.requires_aret_binary and not _repository_file(repository, "target/release/aret", "Binaire ARET").is_file():
        missing.append("target/release/aret")
    if spec.script and not _repository_file(repository, spec.script, "Script d’oracle").is_file():
        missing.append(spec.script)
    return missing


def normalise_result(spec: OracleSpec, exit_code: int | None, stdout: str, stderr: str, missing: list[str], timed_out: bool) -> str:
    if missing:
        return "SKIPPED"
    if timed_out:
        return "ERROR"
    output = f"{stdout}\n{stderr}"
    # Un script peut signaler quelques fixtures SKIP tout en échouant globalement.
    # Le code de sortie non nul reste alors un FAIL observable ; il ne doit jamais
    # être masqué par une ligne SKIP partielle dans la sortie.
    if exit_code is not None and exit_code != 0:
        return "FAIL"
    if spec.name == "difftest":
        match = re.search(r"differential equivalence:\s*(\d+)\s*/\s*(\d+)\s+functions", output)
        if exit_code == 0 and match and int(match.group(1)) == int(match.group(2)) and int(match.group(2)) > 0:
            return "PASS"
    elif spec.name == "transpilediff":
        match = re.search(r"transpile-pipeline equivalence:\s*(\d+)\s*/\s*(\d+)\s+opt-levels", output)
        if exit_code == 0 and match and int(match.group(1)) == int(match.group(2)) and int(match.group(2)) > 0:
            return "PASS"
    elif spec.name == "stdcall_audit" and exit_code == 0 and re.search(r"stdcall-pop audit:\s*PASS", output):
        return "PASS"
    elif spec.name == "winediff":
        match = re.search(r"OS-API \(Wine\) equivalence:\s*(\d+)\s*/\s*(\d+)\s+programs", output)
        if exit_code == 0 and match and int(match.group(1)) == int(match.group(2)) and int(match.group(2)) > 0:
            return "PASS"
    elif spec.name == "ehdiff":
        match = re.search(r"MSVC EH differential:\s*(\d+)\s*/\s*(\d+)\s+fixtures", output)
        if exit_code == 0 and match and int(match.group(1)) == int(match.group(2)) and int(match.group(2)) > 0:
            return "PASS"
    elif spec.name == "gnuehdiff":
        match = re.search(r"GNU/Itanium C\+\+ EH differential:\s*(\d+)\s*/\s*(\d+)\s+fixtures", output)
        if exit_code == 0 and match and int(match.group(1)) == int(match.group(2)) and int(match.group(2)) > 0:
            return "PASS"
    elif spec.name == "funcdiff" and exit_code == 0 and re.search(r"funcdiff corpus gate:\s*PASS", output):
        return "PASS"
    elif spec.name == "cpudiff" and exit_code == 0 and re.search(r"test result:\s*ok", output):
        return "PASS"
    elif spec.name == "winehash" and exit_code == 0 and re.search(r"\bOK\s+[0-9a-f]{64}\b", output):
        # Cette sortie est une mesure Wine à comparer au runner Windows, pas un gate de conformité.
        return "UNKNOWN"
    if re.search(r"^SKIP(?:PED)?\b", output, flags=re.MULTILINE):
        return "SKIPPED"
    return "ERROR"


def safe_fixture(value: str | None) -> str | None:
    if value is None:
        return None
    candidate = value.strip()
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", candidate):
        raise AretError("Nom de fixture invalide")
    return candidate


def run_oracle(
    store: MemoryStore,
    repository: Path,
    oracle_name: str,
    knowledge_id: str | None = None,
    promote: bool = False,
    fixture: str | None = None,
    timeout_seconds: int | None = None,
    actor: str = "aret-oracle-adapter",
) -> dict[str, Any]:
    store._require_write()
    name = oracle_name.strip().lower()
    if name not in ORACLES:
        raise AretError("Oracle inconnu : choisir difftest, winehash, winediff ou funcdiff")
    spec = ORACLES[name]
    fixture = safe_fixture(fixture)
    if fixture and not spec.accepts_fixture:
        raise AretError(f"L’oracle {name} n’accepte pas de sélection de fixture")
    limit = timeout_seconds if timeout_seconds is not None else spec.timeout_seconds
    if not isinstance(limit, int) or limit < 1 or limit > spec.timeout_seconds:
        raise AretError(f"timeout_seconds doit être compris entre 1 et {spec.timeout_seconds} pour {name}")
    repository = repository.expanduser().resolve()
    if not repository.is_dir():
        raise AretError("Dépôt ARET introuvable")
    missing = required_tools(spec, repository)
    script_path = _repository_file(repository, str(spec.script), "Script d’oracle") if spec.script else None
    aret_binary = _repository_file(repository, "target/release/aret", "Binaire ARET")
    command = list(spec.command) if spec.command else ["bash", str(script_path)]
    if fixture:
        command.append(fixture)
    started = utc_now()
    started_monotonic = time.monotonic()
    stdout = ""
    stderr = ""
    exit_code: int | None = None
    timed_out = False
    if not missing:
        environment = {"PATH": os.environ.get("PATH", ""), "LC_ALL": "C", "TZ": "UTC", "ARET": str(aret_binary)}
        try:
            completed = subprocess.run(command, cwd=repository, env=environment, text=True, capture_output=True, timeout=limit, check=False)
            stdout, stderr, exit_code = completed.stdout, completed.stderr, completed.returncode
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            stdout = exc.stdout if isinstance(exc.stdout, str) else (exc.stdout or b"").decode("utf-8", errors="replace")
            stderr = exc.stderr if isinstance(exc.stderr, str) else (exc.stderr or b"").decode("utf-8", errors="replace")
    finished = utc_now()
    result = normalise_result(spec, exit_code, stdout, stderr, missing, timed_out)
    command_text = " ".join(json.dumps(part) if re.search(r"\s", part) else part for part in command)
    environment_summary = {
        "adapter": "aret-mmu-oracles/1",
        "oracle": spec.name,
        "repository": str(repository),
        "repository_revision": repository_revision(repository),
        "script": spec.script or "<commande-cargo-fermée>",
        "fixture": fixture or "",
        "timeout_seconds": limit,
        "missing_dependencies": missing,
        "timed_out": timed_out,
        "duration_seconds": round(time.monotonic() - started_monotonic, 3),
    }
    artifact = {
        "format": "aret-oracle-artifact/v1",
        "oracle": spec.name,
        "kind": spec.kind,
        "command": command_text,
        "result": result,
        "exit_code": exit_code,
        "started_at": started,
        "finished_at": finished,
        "environment": environment_summary,
        "stdout": stdout,
        "stderr": stderr,
    }
    artifact_rel = f"oracles/{spec.name}/{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}_{uuid4().hex[:12]}.json"
    artifact_path = store.artifacts_dir / artifact_rel
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    artifact_hash = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
    receipt_payload = {
        "kind": spec.kind,
        "command": command_text,
        "result": result,
        "exit_code": exit_code,
        "artifact_path": artifact_rel,
        "artifact_hash": artifact_hash,
        "environment": environment_summary,
        "started_at": started,
        "finished_at": finished,
    }
    secret = store.proof_hmac_secret
    receipt = create_receipt(receipt_payload, secret) if secret else {"payload_hash": "", "receipt_hmac": ""}
    proof = store.record_proof(
        **receipt_payload,
        stdout_ref=artifact_rel,
        stderr_ref=artifact_rel,
        receipt_hmac=receipt["receipt_hmac"],
        actor=actor,
    )
    attachment = None
    if knowledge_id:
        attachment = store.attach_proof(knowledge_id, proof["id"], actor, promote=promote)
    elif promote:
        raise AretError("promotion demandée sans knowledge_id")
    return {
        "proof": proof,
        "artifact": {"path": artifact_rel, "sha256": artifact_hash},
        "execution": {"oracle": spec.name, "result": result, "exit_code": exit_code, "missing_dependencies": missing, "timed_out": timed_out},
        "attachment": attachment,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Exécuter un oracle ARET et enregistrer sa preuve")
    parser.add_argument("oracle", choices=sorted(ORACLES))
    parser.add_argument("--repository", type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument("--memory-dir", type=Path, default=Path(__file__).resolve().parents[2] / ".aret-memory")
    parser.add_argument("--knowledge-id")
    parser.add_argument("--promote", action="store_true")
    parser.add_argument("--fixture")
    parser.add_argument("--timeout-seconds", type=int)
    parser.add_argument("--write-enabled", action="store_true")
    args = parser.parse_args()
    if not args.write_enabled:
        raise SystemExit("--write-enabled est requis pour enregistrer une preuve")
    os.environ["ARET_MEMORY_DIR"] = str(args.memory_dir)
    os.environ["ARET_WRITE_ENABLED"] = "true"
    try:
        result = run_oracle(MemoryStore(), args.repository, args.oracle, args.knowledge_id, args.promote, args.fixture, args.timeout_seconds)
        print(json.dumps({"ok": True, "result": result}, ensure_ascii=False, indent=2))
    except AretError as exc:
        print(json.dumps({"ok": False, "error": {"code": type(exc).__name__, "message": str(exc)}}, ensure_ascii=False, indent=2))
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()

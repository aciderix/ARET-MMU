"""Pipelines ARET fermés, auditables et contextualisables via ARET-MMU.

Cette couche ne reçoit jamais de commande, d'URL ni de chemin de sortie arbitraire d'un
client MCP. Elle sélectionne des scripts réels du dépôt par nom, borne leurs paramètres,
stocke des artefacts hashés et consigne l'exécution dans le Store canonique.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from core.repository import AretError, MemoryStore, canonical_json, utc_now


PROJECT_ROOT = Path(__file__).resolve().parents[3]
PIPELINE_POLICIES = {"READ_ONLY", "GENERATE", "NETWORK", "SENSITIVE"}
PIPELINE_RESULTS = {"PASS", "FAIL", "ERROR", "SKIPPED", "UNKNOWN", "PLANNED"}
PROFILE_PACKAGES = {"sample": 25, "medium": 125, "full": 450}
SAFE_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,95}")


@dataclass(frozen=True)
class PipelineSpec:
    """Contrat fermé d'un pipeline réellement présent dans le dépôt ARET."""

    name: str
    kind: str
    policy: str
    description: str
    dependencies: tuple[str, ...]
    timeout_seconds: int
    runner: str
    requires_aret_binary: bool = False


PIPELINES: dict[str, PipelineSpec] = {
    "toolchain_status": PipelineSpec(
        "toolchain_status", "TOOLCHAIN_STATUS", "READ_ONLY",
        "Diagnostique les prérequis ARET, Wine, MinGW, Rust, Unicorn, Clang, Z3 et le binaire ARET.",
        (), 10, "internal_toolchain",
    ),
    "inspect_binary": PipelineSpec(
        "inspect_binary", "BINARY_IMPORTS", "READ_ONLY",
        "Inspecte les imports d'un PE par la CLI ARET sans générer de code.",
        ("aret",), 120, "aret_imports", True,
    ),
    "measure_binary_walls": PipelineSpec(
        "measure_binary_walls", "BINARY_WALLS", "READ_ONLY",
        "Cartographie les murs statiques d'un PE : instructions, imports et appels non résolus.",
        ("aret",), 300, "aret_walls", True,
    ),
    "measure_walls": PipelineSpec(
        "measure_walls", "CORPUS_WALLS", "READ_ONLY",
        "Agrège les murs sur un corpus PE32 et les classe par binaires distincts bloqués.",
        ("bash",), 3600, "wallsweep", True,
    ),
    "measure_corpus_imports": PipelineSpec(
        "measure_corpus_imports", "CORPUS_IMPORTS", "READ_ONLY",
        "Agrège les imports HLE non couverts sur un corpus de binaires réels.",
        ("bash",), 3600, "corpus_sweep", True,
    ),
    "run_regression_gate": PipelineSpec(
        "run_regression_gate", "REGRESSION_GATE", "READ_ONLY",
        "Exécute la porte de régression ARET unifiée avant intégration.",
        ("bash",), 7200, "regression", True,
    ),
    "run_gauntlet": PipelineSpec(
        "run_gauntlet", "GAUNTLET", "READ_ONLY",
        "Mesure bit-à-bit le gauntlet de binaires Win32 représentatifs.",
        ("bash",), 7200, "gauntlet", True,
    ),
    "run_busybox_sweep": PipelineSpec(
        "run_busybox_sweep", "BUSYBOX_SWEEP", "READ_ONLY",
        "Exécute la batterie déterministe BusyBox sur un vrai binaire multicall.",
        ("bash", "wine"), 7200, "busybox_sweep", True,
    ),
    "run_sqlite_sweep": PipelineSpec(
        "run_sqlite_sweep", "SQLITE_SWEEP", "READ_ONLY",
        "Mesure la surface fonctionnelle d'un sqlite3.exe réel contre Wine.",
        ("bash", "wine"), 7200, "sqlite_sweep", True,
    ),
    "run_transpile_diff": PipelineSpec(
        "run_transpile_diff", "TRANSPILE_DIFF", "READ_ONLY",
        "Différentiel du pipeline transpile complet, distinct du difftest d'émission C.",
        ("bash", "gcc"), 3600, "transpile_diff", True,
    ),
    "run_inplace_diff": PipelineSpec(
        "run_inplace_diff", "INPLACE_DIFF", "READ_ONLY",
        "Différentiel pour fonctions accédant à des données globales par adresse absolue.",
        ("bash", "gcc"), 3600, "inplace_diff", True,
    ),
    "prove_rewrites": PipelineSpec(
        "prove_rewrites", "SMT_REWRITES", "READ_ONLY",
        "Prouve avec Z3 que les réécritures de l'optimiseur préservent la sémantique.",
        ("bash", "z3"), 1800, "smt_rewrites", True,
    ),
    "run_magicdiv_check": PipelineSpec(
        "run_magicdiv_check", "MAGICDIV", "READ_ONLY",
        "Vérifie exhaustivement la réécriture de division magique sur 32 bits.",
        ("bash", "gcc"), 3600, "magicdiv", True,
    ),
    "run_relay_diff": PipelineSpec(
        "run_relay_diff", "RELAY_DIFF", "READ_ONLY",
        "Exécute le différentiel d'exécution ARET vers Wine.",
        ("python3", "wine"), 3600, "relaydiff", True,
    ),
    "generate_flirt_signatures": PipelineSpec(
        "generate_flirt_signatures", "FLIRT_SIGNATURES", "GENERATE",
        "Génère des signatures FLIRT-lite à partir d'un binaire avec symboles.",
        ("aret",), 900, "gensig", True,
    ),
    "execute_auto_lift": PipelineSpec(
        "execute_auto_lift", "AUTO_LIFT", "GENERATE",
        "Transpile un PE avec fermeture auto-lift des DLL tierces non système.",
        ("aret",), 7200, "auto_lift", True,
    ),
    "generate_stdcall_pops": PipelineSpec(
        "generate_stdcall_pops", "STDCALL_GENERATION", "GENERATE",
        "Régénère la table __stdcall @N depuis les import-libs MinGW.",
        ("python3", "i686-w64-mingw32-nm"), 1800, "stdcall_generation",
    ),
    "generate_win32_signatures": PipelineSpec(
        "generate_win32_signatures", "WIN32_SIGNATURES", "GENERATE",
        "Génère les signatures Win32 typées depuis les en-têtes MinGW et l'AST Clang.",
        ("python3", "clang"), 3600, "win32_signature_generation",
    ),
    "generate_codepage_cp1252": PipelineSpec(
        "generate_codepage_cp1252", "CODEPAGE_CP1252", "GENERATE",
        "Génère la table CP1252 mesurée depuis Wine.",
        ("python3",), 900, "cp1252_generation",
    ),
    "generate_codepage_cp437": PipelineSpec(
        "generate_codepage_cp437", "CODEPAGE_CP437", "GENERATE",
        "Génère la table CP437 OEM vers UTF-16 et inverse.",
        ("python3",), 900, "cp437_generation",
    ),
    "generate_mlang_codepage": PipelineSpec(
        "generate_mlang_codepage", "MLANG_CODEPAGE", "GENERATE",
        "Extrait une table codepage depuis les sources Wine mlang.",
        ("python3",), 900, "mlang_generation",
    ),
    "measure_wine_heavy": PipelineSpec(
        "measure_wine_heavy", "WINE_HEAVY_MEASURE", "READ_ONLY",
        "Mesure une source Wine locale inchangée et son plancher de primitives, sans récupération réseau implicite.",
        ("python3", "i686-w64-mingw32-gcc", "i686-w64-mingw32-nm"), 1800, "wine_heavy_measure",
    ),
    "run_wine_heavy_proof": PipelineSpec(
        "run_wine_heavy_proof", "WINE_HEAVY_PROOF", "GENERATE",
        "Exécute une preuve de réutilisation lourde Wine selon un profil fermé.",
        ("bash",), 3600, "wine_heavy_proof",
    ),
    "build_gauntlet": PipelineSpec(
        "build_gauntlet", "GAUNTLET_BUILD", "GENERATE",
        "Reconstruit les binaires de gauntlet depuis archives source déjà disponibles localement.",
        ("bash",), 7200, "gauntlet_build",
    ),
    "fetch_wall_corpus": PipelineSpec(
        "fetch_wall_corpus", "WALL_CORPUS_FETCH", "NETWORK",
        "Télécharge un corpus PE32 FOSS depuis les sources autorisées MSYS2 et UnxUtils.",
        ("bash", "curl", "tar", "unzstd", "file"), 14400, "wallcorpus_fetch",
    ),
    "setup_winelib": PipelineSpec(
        "setup_winelib", "WINELIB_SETUP", "NETWORK",
        "Provisionne la toolchain Winelib reproductible depuis la procédure ARET contrôlée.",
        ("bash",), 3600, "setup_winelib",
    ),
    "capture_snapshot": PipelineSpec(
        "capture_snapshot", "PROCESS_SNAPSHOT", "SENSITIVE",
        "Capture un snapshot ARETSNP1 d'un processus explicitement approuvé.",
        ("python3",), 600, "capture_snapshot",
    ),
}


def _repository_revision(repository: Path) -> str:
    result = subprocess.run(["git", "-C", str(repository), "rev-parse", "HEAD"], text=True, capture_output=True, check=False)
    return result.stdout.strip() if result.returncode == 0 else "UNKNOWN"


def _safe_token(value: Any, label: str) -> str:
    candidate = str(value or "").strip()
    if not SAFE_TOKEN_RE.fullmatch(candidate):
        raise AretError(f"{label} invalide : utiliser 1 à 96 caractères alphanumériques, _, . ou -")
    return candidate


def _required_tools(spec: PipelineSpec, repository: Path) -> list[str]:
    binary = repository / "target" / "release" / "aret"
    missing: list[str] = []
    for tool in spec.dependencies:
        if tool == "aret":
            if not binary.is_file():
                missing.append("target/release/aret")
        elif shutil.which(tool) is None:
            missing.append(tool)
    if spec.requires_aret_binary and not binary.is_file() and "target/release/aret" not in missing:
        missing.append("target/release/aret")
    return missing


def _safe_asset_path(store: MemoryStore, repository: Path, value: str) -> Path:
    """Accepte seulement un fichier dans le dépôt ou les artefacts du Store."""
    raw = Path(str(value)).expanduser()
    candidate = raw.resolve() if raw.is_absolute() else (repository / raw).resolve()
    roots = (repository.resolve(), store.artifacts_dir.resolve())
    if not any(candidate == root or root in candidate.parents for root in roots):
        raise AretError("Le binaire doit être dans le dépôt ARET ou sous .aret-memory/artifacts/")
    if not candidate.is_file():
        raise AretError(f"Asset introuvable : {value}")
    if candidate.stat().st_size > 2 * 1024 * 1024 * 1024:
        raise AretError("Asset refusé : taille supérieure à 2 GiB")
    return candidate


def _safe_corpus_path(store: MemoryStore, repository: Path, value: str) -> Path:
    raw = Path(str(value)).expanduser()
    candidate = raw.resolve() if raw.is_absolute() else (repository / raw).resolve()
    roots = (repository.resolve(), store.artifacts_dir.resolve())
    if not any(candidate == root or root in candidate.parents for root in roots):
        raise AretError("Le corpus doit rester dans le dépôt ARET ou sous .aret-memory/artifacts/")
    if not candidate.is_dir():
        raise AretError(f"Corpus introuvable : {value}")
    return candidate


def _command_for(spec: PipelineSpec, store: MemoryStore, repository: Path, parameters: dict[str, Any], run_dir: Path) -> list[str] | None:
    """Construit uniquement des argv fermés depuis des paramètres validés."""
    runner = spec.runner
    binary = str((repository / "target" / "release" / "aret").resolve())
    if runner == "internal_toolchain":
        return None
    if runner in {"aret_imports", "aret_walls", "gensig"}:
        asset = _safe_asset_path(store, repository, str(parameters.get("binary_path", "")))
        mode = {"aret_imports": "imports", "aret_walls": "walls", "gensig": "gensig"}[runner]
        return [binary, str(asset), "--mode", mode]
    if runner == "auto_lift":
        asset = _safe_asset_path(store, repository, str(parameters.get("binary_path", "")))
        out_dir = run_dir / "auto_lift"
        out_dir.mkdir(parents=True, exist_ok=True)
        command = [binary, str(asset), "--mode", "transpile", "--auto-lift", "--out-dir", str(out_dir)]
        for item in parameters.get("dll_paths", []):
            candidate = _safe_corpus_path(store, repository, str(item))
            command.extend(["--dll-path", str(candidate)])
        return command
    if runner == "wallsweep":
        corpus = _safe_corpus_path(store, repository, str(parameters.get("corpus_path", "")))
        return ["bash", str(repository / "bench" / "wallsweep.sh"), str(corpus)]
    if runner == "corpus_sweep":
        corpus = _safe_corpus_path(store, repository, str(parameters.get("corpus_path", "")))
        return ["bash", str(repository / "bench" / "corpus_sweep.sh"), str(corpus)]
    scripts = {
        "regression": "bench/regression.sh", "gauntlet": "bench/gauntlet/score.sh",
        "busybox_sweep": "bench/busybox_sweep.sh", "sqlite_sweep": "bench/sqlite_sweep.sh",
        "transpile_diff": "bench/difftest_transpile.sh", "inplace_diff": "bench/inplace.sh",
        "smt_rewrites": "bench/smt_rewrites.sh", "magicdiv": "bench/magicdiv.sh",
        "relaydiff": "bench/relaydiff.py", "stdcall_generation": "tools/gen_stdcall_pops.py",
        "win32_signature_generation": "tools/gen_win32_sigs.py", "cp1252_generation": "tools/gen_cp1252.py",
        "cp437_generation": "tools/gen_cp437.py", "mlang_generation": "tools/gen_mlang_cp.py",
        "gauntlet_build": "bench/gauntlet/build.sh", "setup_winelib": "tools/setup-winelib.sh",
    }
    if runner in scripts:
        path = repository / scripts[runner]
        prefix = ["python3"] if path.suffix == ".py" else ["bash"]
        return prefix + [str(path)]
    if runner == "wine_heavy_measure":
        source = _safe_asset_path(store, repository, str(parameters.get("source_path", "")))
        if source.suffix.lower() != ".c":
            raise AretError("source_path doit désigner un fichier C Wine local")
        return ["python3", str(repository / "tools" / "gen_wine_heavy.py"), str(source)]
    if runner == "wine_heavy_proof":
        profile = _safe_token(parameters.get("profile", "native"), "profile")
        scripts_by_profile = {
            "wine": "tools/wine_heavy/proof.sh", "native": "tools/wine_heavy/proof_native.sh",
            "ntreg": "tools/wine_heavy/proof_ntreg.sh", "ntreg_native": "tools/wine_heavy/proof_ntreg_native.sh",
            "reg_native": "tools/wine_heavy/proof_reg_native.sh",
        }
        if profile not in scripts_by_profile:
            raise AretError("Profil wine_heavy inconnu : wine, native, ntreg, ntreg_native ou reg_native")
        return ["bash", str(repository / scripts_by_profile[profile])]
    if runner == "wallcorpus_fetch":
        profile = _safe_token(parameters.get("profile", "sample"), "profile")
        if profile not in PROFILE_PACKAGES:
            raise AretError("Profil corpus inconnu : sample, medium ou full")
        corpus_dir = store.artifacts_dir / "corpora" / f"wall-{profile}"
        corpus_dir.mkdir(parents=True, exist_ok=True)
        return ["bash", str(repository / "bench" / "wallcorpus_fetch.sh"), str(corpus_dir), str(PROFILE_PACKAGES[profile])]
    if runner == "capture_snapshot":
        pid = parameters.get("pid")
        if isinstance(pid, bool) or not isinstance(pid, int) or pid < 1:
            raise AretError("pid doit être un entier positif")
        lo = int(parameters.get("lo_va", 0x10000))
        hi = int(parameters.get("hi_va", 0x80000000))
        if lo < 0 or hi <= lo or hi > 0x1_0000_0000:
            raise AretError("Plage mémoire snapshot invalide")
        target = run_dir / f"snapshot-{pid}.aretsnp1"
        return ["python3", str(repository / "tools" / "snapshot" / "dump_snapshot.py"), str(pid), str(target), hex(lo), hex(hi)]
    raise AretError(f"Runner non implémenté : {runner}")


def _normalise_result(exit_code: int | None, missing: list[str], timed_out: bool) -> str:
    if missing:
        return "SKIPPED"
    if timed_out:
        return "ERROR"
    if exit_code == 0:
        return "PASS"
    if exit_code is not None:
        return "FAIL"
    return "ERROR"


def pipeline_catalog() -> dict[str, Any]:
    """Inventaire borné injectible dans le contexte Claude, sans exécuter de processus."""
    categories: dict[str, list[dict[str, Any]]] = {policy: [] for policy in sorted(PIPELINE_POLICIES)}
    for spec in PIPELINES.values():
        categories[spec.policy].append({
            "name": spec.name, "kind": spec.kind, "description": spec.description,
            "dependencies": list(spec.dependencies), "timeout_seconds": spec.timeout_seconds,
        })
    for items in categories.values():
        items.sort(key=lambda item: item["name"])
    return {
        "contract": "Pipelines nommés, liste fermée, argv contrôlés, artefacts hashés, aucun shell arbitraire, aucun push automatique.",
        "policies": categories,
        "network_confirmation_required": True,
        "sensitive_confirmation_required": True,
        "generate_apply_confirmation_required": True,
    }


def toolchain_status(repository: Path) -> dict[str, Any]:
    expected = {
        "aret": repository / "target" / "release" / "aret", "wine": "wine", "mingw_c": "i686-w64-mingw32-gcc",
        "mingw_cpp": "i686-w64-mingw32-g++", "cargo": "cargo", "rustc": "rustc", "clang": "clang",
        "z3": "z3", "unicorn": "libunicorn", "winegcc": "winegcc",
    }
    status: dict[str, Any] = {}
    for name, expected_value in expected.items():
        if isinstance(expected_value, Path):
            status[name] = {"available": expected_value.is_file(), "path": str(expected_value)}
            continue
        path = shutil.which(expected_value)
        version = ""
        if path:
            completed = subprocess.run([path, "--version"], text=True, capture_output=True, timeout=5, check=False)
            version = (completed.stdout or completed.stderr).splitlines()[0][:240] if (completed.stdout or completed.stderr) else ""
        status[name] = {"available": bool(path), "path": path or "", "version": version}
    return {"repository": str(repository), "revision": _repository_revision(repository), "tools": status}


def run_pipeline(
    store: MemoryStore,
    repository: Path,
    pipeline_name: str,
    parameters: dict[str, Any] | None = None,
    *,
    dry_run: bool = True,
    confirm_apply: bool = False,
    confirm_network: bool = False,
    confirm_sensitive: bool = False,
    timeout_seconds: int | None = None,
    actor: str = "aret-pipeline-adapter",
) -> dict[str, Any]:
    """Exécute un pipeline fermé ou retourne son plan ; aucune commande libre n'est acceptée."""
    name = str(pipeline_name or "").strip().lower()
    if name not in PIPELINES:
        raise AretError(f"Pipeline inconnu : {name}")
    spec = PIPELINES[name]
    parameters = parameters or {}
    if not isinstance(parameters, dict):
        raise AretError("parameters doit être un objet JSON")
    repository = repository.expanduser().resolve()
    if not repository.is_dir():
        raise AretError("Dépôt ARET introuvable")
    if timeout_seconds is not None and (isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, int) or timeout_seconds < 1 or timeout_seconds > spec.timeout_seconds):
        raise AretError(f"timeout_seconds doit être compris entre 1 et {spec.timeout_seconds}")
    if spec.policy == "GENERATE" and not dry_run and not confirm_apply:
        raise AretError("Pipeline génératif refusé : dry_run=false et confirm_apply=true sont requis")
    if spec.policy == "NETWORK" and not dry_run and not confirm_network:
        raise AretError("Pipeline réseau refusé : confirm_network=true est requis")
    if spec.policy == "SENSITIVE" and not dry_run and not confirm_sensitive:
        raise AretError("Pipeline sensible refusé : confirm_sensitive=true est requis")
    run_dir = store.artifacts_dir / "pipelines" / name / f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}_{uuid4().hex[:12]}"
    command = _command_for(spec, store, repository, parameters, run_dir)
    if dry_run:
        return {
            "pipeline": name, "policy": spec.policy, "dry_run": True, "command": command or ["<internal-toolchain-status>"],
            "parameters": parameters, "confirmation_required": {
                "confirm_apply": spec.policy == "GENERATE", "confirm_network": spec.policy == "NETWORK",
                "confirm_sensitive": spec.policy == "SENSITIVE",
            },
        }
    if spec.runner == "internal_toolchain":
        return {"pipeline": name, "policy": spec.policy, "dry_run": False, "result": "PASS", "toolchain": toolchain_status(repository)}
    store._require_write()
    missing = _required_tools(spec, repository)
    started = utc_now()
    started_monotonic = time.monotonic()
    stdout = ""
    stderr = ""
    exit_code: int | None = None
    timed_out = False
    limit = timeout_seconds or spec.timeout_seconds
    if not missing:
        run_dir.mkdir(parents=True, exist_ok=True)
        environment = {
            "PATH": os.environ.get("PATH", ""), "LC_ALL": "C", "TZ": "UTC",
            "ARET": str((repository / "target" / "release" / "aret").resolve()),
            "ARET_MMU_PIPELINE_DIR": str(run_dir),
        }
        try:
            completed = subprocess.run(command or [], cwd=repository, env=environment, text=True, capture_output=True, timeout=limit, check=False)
            stdout, stderr, exit_code = completed.stdout, completed.stderr, completed.returncode
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            stdout = exc.stdout if isinstance(exc.stdout, str) else (exc.stdout or b"").decode("utf-8", errors="replace")
            stderr = exc.stderr if isinstance(exc.stderr, str) else (exc.stderr or b"").decode("utf-8", errors="replace")
    finished = utc_now()
    result = _normalise_result(exit_code, missing, timed_out)
    artifact = {
        "format": "aret-pipeline-artifact/v1", "pipeline": name, "kind": spec.kind, "policy": spec.policy,
        "command": command, "parameters": parameters, "result": result, "exit_code": exit_code,
        "started_at": started, "finished_at": finished,
        "environment": {"repository": str(repository), "revision": _repository_revision(repository), "missing_dependencies": missing, "timed_out": timed_out, "duration_seconds": round(time.monotonic() - started_monotonic, 3)},
        "stdout": stdout, "stderr": stderr,
    }
    artifact_rel = f"pipelines/{name}/{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}_{uuid4().hex[:12]}.json"
    artifact_path = store.artifacts_dir / artifact_rel
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    artifact_hash = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
    record = store.record_pipeline_run(
        pipeline_name=name, kind=spec.kind, policy=spec.policy, result=result,
        command=" ".join(command or ["<internal-toolchain-status>"]), parameters=parameters,
        artifact_path=artifact_rel, artifact_hash=artifact_hash, exit_code=exit_code,
        started_at=started, finished_at=finished, actor=actor,
    )
    registered_asset = None
    if result == "PASS" and name == "fetch_wall_corpus":
        profile = str(parameters.get("profile", "sample"))
        corpus_root = store.artifacts_dir / "corpora" / f"wall-{profile}"
        registered_asset = store.register_asset_file(
            source_path=artifact_path, kind="CORPUS", source_kind="NETWORK",
            provenance={
                "pipeline": name, "pipeline_address": record["address"], "corpus_root": str(corpus_root),
                "profile": profile, "sources": ["https://repo.msys2.org/mingw/mingw32/", "https://downloads.sourceforge.net/project/unxutils/"],
            }, actor=actor,
        )
    elif result == "PASS" and name == "capture_snapshot":
        snapshots = sorted(run_dir.glob("*.aretsnp1"))
        if snapshots:
            registered_asset = store.register_asset_file(
                source_path=snapshots[0], kind="SNAPSHOT", source_kind="SNAPSHOT",
                provenance={"pipeline": name, "pipeline_address": record["address"], "pid": parameters.get("pid")}, actor=actor,
            )
    return {
        "pipeline": name, "policy": spec.policy, "dry_run": False, "execution": {
            "result": result, "exit_code": exit_code, "missing_dependencies": missing, "timed_out": timed_out,
        }, "artifact": {"path": artifact_rel, "sha256": artifact_hash}, "run": record, "registered_asset": registered_asset,
    }


def register_asset(
    store: MemoryStore, repository: Path, source_path: str, kind: str, *, confirm_import: bool, actor: str = "mcp-asset-import"
) -> dict[str, Any]:
    """Copie un asset local autorisé dans le Store, le hashe et conserve sa provenance."""
    if not confirm_import:
        raise AretError("Import d'asset refusé : confirm_import=true est requis")
    allowed = {"PE32", "DLL", "SNAPSHOT", "IAT_MAP", "CORPUS", "GENERATED"}
    normalized_kind = str(kind).strip().upper()
    if normalized_kind not in allowed:
        raise AretError("kind d'asset inconnu : PE32, DLL, SNAPSHOT, IAT_MAP, CORPUS ou GENERATED")
    source = _safe_asset_path(store, repository, source_path)
    if source.stat().st_size > 2 * 1024 * 1024 * 1024:
        raise AretError("Asset refusé : taille supérieure à 2 GiB")
    store._require_write()
    return store.register_asset_file(
        source_path=source, kind=normalized_kind, source_kind="LOCAL",
        provenance={"repository": str(repository), "revision": _repository_revision(repository), "original_path": str(source)}, actor=actor,
    )

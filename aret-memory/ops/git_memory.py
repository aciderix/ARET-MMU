"""Opérations Git explicitement demandées et limitées au Memory Store ARET-MMU."""

from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class GitMemoryError(RuntimeError):
    pass


def invoke(repository: Path, *args: str) -> str:
    completed = subprocess.run(["git", "-C", str(repository), *args], check=False, text=True, capture_output=True)
    if completed.returncode != 0:
        raise GitMemoryError((completed.stderr or completed.stdout).strip() or f"git {' '.join(args)} a échoué")
    return completed.stdout.strip()


def repository_root(path: Path) -> Path:
    root = invoke(path, "rev-parse", "--show-toplevel")
    return Path(root).resolve()


def memory_path(repository: Path, requested: str | None) -> Path:
    target = (repository / (requested or "aret-memory/.aret-memory")).resolve()
    if target.name != ".aret-memory" or repository not in target.parents:
        raise GitMemoryError("Le chemin autorisé doit désigner un dossier .aret-memory/ situé dans le dépôt")
    if not target.is_dir():
        raise GitMemoryError("Le Memory Store .aret-memory/ est introuvable")
    return target


def memory_relative(repository: Path, requested: str | None) -> str:
    return memory_path(repository, requested).relative_to(repository).as_posix()


def checkpoint_wal(memory_dir: Path) -> dict[str, int | bool | str]:
    """Consolide le journal WAL avant de versionner la base canonique.

    Un répertoire mémoire sans base est autorisé pour les tests de confinement Git ; dans ce cas
    aucun checkpoint fictif n’est annoncé. Une base occupée bloque le commit plutôt que de
    versionner un fichier principal incomplet.
    """
    database = memory_dir / "aret_memory.sqlite"
    if not database.is_file():
        return {"checkpointed": False, "reason": "database_absent"}
    connection = sqlite3.connect(database)
    try:
        connection.execute("PRAGMA busy_timeout = 5000")
        row = connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
        busy, log_frames, checkpointed = (int(value) for value in row)
    except sqlite3.Error as exc:
        raise GitMemoryError(f"Checkpoint WAL impossible : {exc}") from exc
    finally:
        connection.close()
    if busy:
        raise GitMemoryError("Checkpoint WAL refusé : une connexion active empêche le commit mémoire")
    return {"checkpointed": True, "busy": busy, "log_frames": log_frames, "checkpointed_frames": checkpointed}


def changes(repository: Path) -> list[dict[str, str]]:
    raw = invoke(repository, "status", "--porcelain=v1", "--untracked-files=all")
    output: list[dict[str, str]] = []
    for line in raw.splitlines():
        if len(line) < 4:
            continue
        output.append({"index": line[0], "worktree": line[1], "path": line[3:]})
    return output


def validate_scope(items: list[dict[str, str]], relative_memory: str) -> None:
    outside = [item["path"] for item in items if not (item["path"] == relative_memory or item["path"].startswith(relative_memory + "/"))]
    if outside:
        raise GitMemoryError("Des changements hors du Memory Store sont présents : " + ", ".join(outside[:8]))


def status(repository: Path, requested: str | None) -> dict[str, Any]:
    root = repository_root(repository)
    target = memory_path(root, requested)
    relative = memory_relative(root, requested)
    all_changes = changes(root)
    scoped = [item for item in all_changes if item["path"] == relative or item["path"].startswith(relative + "/")]
    outside = [item for item in all_changes if item not in scoped]
    return {"repository": str(root), "memory_dir": str(target), "memory_changes": scoped, "outside_changes": outside,
            "clean_memory": not scoped, "safe_to_commit_memory_only": not outside}


def commit(repository: Path, requested: str | None, message: str, yes: bool) -> dict[str, Any]:
    if not yes:
        raise GitMemoryError("Commit refusé sans --yes explicite")
    if not message.strip():
        raise GitMemoryError("Un message de commit explicite est requis")
    root = repository_root(repository)
    target = memory_path(root, requested)
    relative = memory_relative(root, requested)
    wal = checkpoint_wal(target)
    all_changes = changes(root)
    validate_scope(all_changes, relative)
    if not all_changes:
        return {"repository": str(root), "committed": False, "notice": "Aucun changement .aret-memory/ à committer."}
    invoke(root, "add", "--", relative)
    invoke(root, "commit", "-m", message.strip(), "--", relative)
    return {"repository": str(root), "committed": True, "message": message.strip(), "head": invoke(root, "rev-parse", "HEAD"), "wal_checkpoint": wal}


def push(repository: Path, requested: str | None, remote: str, branch: str, yes: bool) -> dict[str, Any]:
    if not yes:
        raise GitMemoryError("Push refusé sans --yes explicite")
    root = repository_root(repository)
    relative = memory_relative(root, requested)
    pending = changes(root)
    validate_scope(pending, relative)
    if pending:
        raise GitMemoryError("Le push est refusé tant que .aret-memory/ contient des changements non commités")
    invoke(root, "push", remote, branch)
    return {"repository": str(root), "pushed": True, "remote": remote, "branch": branch, "head": invoke(root, "rev-parse", "HEAD")}


def load_sync_policy(memory_dir: Path) -> dict[str, Any]:
    """Charge la politique locale sans jamais transformer une erreur de config en commit implicite."""
    defaults: dict[str, Any] = {"auto_commit": False, "auto_push": False, "remote": "origin", "branch": ""}
    policy_file = memory_dir / "sync_policy.json"
    if not policy_file.exists():
        return defaults
    try:
        payload = json.loads(policy_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GitMemoryError(f"Politique de synchronisation invalide : {exc}") from exc
    if not isinstance(payload, dict):
        raise GitMemoryError("Politique de synchronisation invalide")
    result = {**defaults, **{key: payload[key] for key in defaults if key in payload}}
    if not isinstance(result["auto_commit"], bool) or not isinstance(result["auto_push"], bool):
        raise GitMemoryError("auto_commit et auto_push doivent être booléens")
    if result["auto_push"] and not result["auto_commit"]:
        raise GitMemoryError("auto_push exige auto_commit")
    if not isinstance(result["remote"], str) or not isinstance(result["branch"], str):
        raise GitMemoryError("remote et branch doivent être des chaînes")
    return result


def automatic_sync(repository: Path, requested: str | None, operation: str) -> dict[str, Any]:
    """Commit/push post-mutation strictement borné, activé seulement par la politique locale."""
    root = repository_root(repository)
    target = memory_path(root, requested)
    relative = memory_relative(root, requested)
    policy = load_sync_policy(target)
    if not policy["auto_commit"]:
        return {"enabled": False, "reason": "auto_commit=false"}
    wal = checkpoint_wal(target)
    all_changes = changes(root)
    try:
        validate_scope(all_changes, relative)
    except GitMemoryError as exc:
        return {"enabled": True, "committed": False, "refused": True, "reason": str(exc)}
    scoped = [item for item in all_changes if item["path"] == relative or item["path"].startswith(relative + "/")]
    if not scoped:
        return {"enabled": True, "committed": False, "reason": "Aucun changement mémoire à synchroniser."}
    message = f"ARET-MMU memory: {operation} — {datetime.now(UTC).strftime('%Y-%m-%dT%H:%M:%SZ')}"
    invoke(root, "add", "--", relative)
    invoke(root, "commit", "-m", message, "--", relative)
    result: dict[str, Any] = {"enabled": True, "committed": True, "message": message, "head": invoke(root, "rev-parse", "HEAD"), "wal_checkpoint": wal}
    if policy["auto_push"]:
        if not policy["branch"].strip():
            return {**result, "pushed": False, "warning": "auto_push activé sans branche : push refusé"}
        invoke(root, "push", policy["remote"], policy["branch"])
        result["pushed"] = True
        result["remote"] = policy["remote"]
        result["branch"] = policy["branch"]
    else:
        result["pushed"] = False
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Git explicite et borné pour ARET-MMU")
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    parser.add_argument("--memory-dir", default="aret-memory/.aret-memory")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("status")
    commit_parser = subparsers.add_parser("commit")
    commit_parser.add_argument("--message", required=True)
    commit_parser.add_argument("--yes", action="store_true")
    push_parser = subparsers.add_parser("push")
    push_parser.add_argument("--remote", default="origin")
    push_parser.add_argument("--branch", required=True)
    push_parser.add_argument("--yes", action="store_true")
    args = parser.parse_args()
    try:
        if args.command == "status":
            result = status(args.repository.resolve(), args.memory_dir)
        elif args.command == "commit":
            result = commit(args.repository.resolve(), args.memory_dir, args.message, args.yes)
        else:
            result = push(args.repository.resolve(), args.memory_dir, args.remote, args.branch, args.yes)
        print(json.dumps({"ok": True, "result": result}, ensure_ascii=False, indent=2))
    except GitMemoryError as exc:
        print(json.dumps({"ok": False, "error": {"code": type(exc).__name__, "message": str(exc)}}, ensure_ascii=False, indent=2))
        raise SystemExit(1)


if __name__ == "__main__":
    main()

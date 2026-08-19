"""Création de reçus de preuve pour les adaptateurs d’oracle de confiance.

Ce module est destiné à être appelé par un adaptateur local maîtrisé, jamais par le modèle.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
from pathlib import Path
from typing import Any


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def make_payload(
    *,
    kind: str,
    command: str,
    result: str,
    exit_code: int | None,
    artifact_path: str,
    artifact_hash: str,
    environment: dict[str, Any],
    started_at: str | None,
    finished_at: str | None,
) -> str:
    """Construit exactement l’enveloppe attendue par `MemoryStore.record_proof`."""
    return canonical_json({
        "artifact_hash": artifact_hash,
        "artifact_path": artifact_path,
        "command": command,
        "environment": environment,
        "exit_code": exit_code,
        "finished_at": finished_at,
        "kind": kind.strip().upper(),
        "result": result.strip().upper(),
        "started_at": started_at,
    })


def create_receipt(payload: dict[str, Any], secret: str) -> dict[str, str]:
    """Retourne le hash de charge et le reçu HMAC-SHA256 de l’oracle."""
    if not secret:
        raise ValueError("ARET_PROOF_HMAC_SECRET est requis pour signer une preuve")
    canonical = make_payload(**payload)
    return {
        "payload_hash": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        "receipt_hmac": hmac.new(secret.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256).hexdigest(),
    }


def main() -> None:
    """Signe un manifeste JSON de preuve, écrit par un adaptateur de test local."""
    parser = argparse.ArgumentParser(description="Signer un manifeste de preuve ARET-MMU")
    parser.add_argument("manifest", type=Path, help="JSON contenant les champs de preuve canoniques")
    parser.add_argument("--output", type=Path, help="Fichier de reçu JSON ; sinon affichage standard")
    args = parser.parse_args()
    payload = json.loads(args.manifest.read_text(encoding="utf-8"))
    receipt = create_receipt(payload, os.environ.get("ARET_PROOF_HMAC_SECRET", ""))
    result = json.dumps(receipt, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(result, encoding="utf-8")
    else:
        print(result, end="")


if __name__ == "__main__":
    main()

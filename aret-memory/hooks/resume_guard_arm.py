#!/usr/bin/env python3
"""Arme explicitement le récapitulatif de reprise ARET-MMU."""
from __future__ import annotations

import json
from pathlib import Path

from common import input_payload, store_from_payload
from resume_guard import arm, ritual_prompt


def main() -> None:
    payload = input_payload()
    store = store_from_payload(payload)
    reason = str(payload.get("reason") or payload.get("hook_event_name") or "manual")[:64]
    context = store.get_resume_context(journal_limit=8, rule_limit=12, excerpt_bytes=260)
    dossier_hash = context["resume_dossier"]["contract_hash"]
    state = arm(Path(store.memory_dir), payload, reason=reason, resume_contract_hash=dossier_hash)
    print(json.dumps({
        "ok": True,
        "resume_guard": state,
        "additional_context": ritual_prompt(dossier_hash),
    }, ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    main()

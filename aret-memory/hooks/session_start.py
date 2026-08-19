"""Hook SessionStart : restitue le contrat minimal de reprise, sans mutation."""

from __future__ import annotations

from typing import Any

from common import run


def handler(store: Any, payload: dict[str, Any]) -> dict[str, Any]:
    restored = store.restore()
    return {
        **restored,
        "instructions": [
            "Utiliser FIND uniquement pour découvrir des candidats.",
            "Utiliser READ ou READ_BATCH pour récupérer les objets canoniques explicitement adressés.",
            "Ne jamais traiter un score de recherche comme une preuve.",
        ],
    }


if __name__ == "__main__":
    run("SessionStart", handler)

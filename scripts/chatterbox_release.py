"""Release eligibility for optional local Chatterbox speech.

Research preparation and test fixtures cannot grant production approval. Change
this boundary only with reviewed runtime/security and native release evidence.
"""

from __future__ import annotations

from typing import Any


def release_readiness() -> dict[str, Any]:
    """Keep regular speech fail-closed while adoption gates remain incomplete."""
    blockers = [
        "A maintained runtime has not passed the security, licence and update-owner gate (#57).",
        "Native warm Stop/reset/crash recovery has not passed the release sequence (#58).",
        "The normal-app native end-to-end release gates have not passed (#62).",
    ]
    return {
        "available": False,
        "decision": "no-go",
        "error": "Chatterbox is unavailable for regular use. " + " ".join(blockers),
        "blockers": blockers,
        "experimental_preparation_available": True,
    }

"""Approved optional speech profile; changed artifacts fail closed pending revalidation."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
# Public artifact digests, not credentials. Reapprove only after the documented release gates.
APPROVED_ARTIFACTS = {
    "chatterbox-maintained-lock.json": (
        "29410cea1ffe712d71c0c907d04396ec11970394d5354533d51e7a1806377ebd"
    ),
    "docs/runtime/chatterbox/requirements-maintained.lock": (
        "959222f9a75f9ec98d86238fc9454ab485ce9be37c5c119f17699db1f5d3261a"
    ),
    "patches/chatterbox-maintained.patch": (
        "55dcc9c809dc6a8b61243d915963f96a7830fdf7579ea4bf021b1a69bb562fde"
    ),
}


def release_readiness() -> dict[str, Any]:
    """Enable only the exact audited and native-verified English CUDA profile."""
    for name, expected in APPROVED_ARTIFACTS.items():
        try:
            actual = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
        except OSError:
            actual = ""
        if actual != expected:
            return {
                "available": False,
                "decision": "no-go",
                "error": "Local voice runtime pins changed or are missing. Restore the approved "
                "checkout or repeat the security and native release gates before enabling.",
            }
    return {
        "available": True,
        "decision": "go",
        "configuration": "maintained",
        "supported_device": "NVIDIA GeForce RTX 3090",
        "error": "",
        "message": "Optional local cloned voices: verified RTX 3090 CUDA configuration.",
    }

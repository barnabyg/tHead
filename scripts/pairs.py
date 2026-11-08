"""Named built-in avatars; legacy pair interfaces remain compatibility aliases."""

from __future__ import annotations

import hashlib
import importlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from prepare import ROOT

DEFAULT_PAIR = "jfk-zira"


def supported_voices() -> dict[str, Path]:
    """Voice references are independent of avatars and may be reused."""
    return {"zira": ROOT / "speech-lock.json", "hazel": ROOT / "hazel-lock.json"}


@dataclass(frozen=True)
class Avatar:
    id: str
    name: str
    portrait: dict[str, Any]
    voice: str

    @property
    def voice_lock(self) -> Path:
        return supported_voices()[self.voice]

    def validate_portrait(self, inputs: Path) -> Path:
        path = inputs / str(self.portrait["filename"])
        if hashlib.sha256(path.read_bytes()).hexdigest() != self.portrait["sha256"]:
            raise ValueError(f"Portrait changed: {path}; preserve/remove it and rerun the launcher")
        image = importlib.import_module("PIL.Image")
        with image.open(path) as picture:
            picture.verify()
        return path


def configured_avatars() -> dict[str, Avatar]:
    data = json.loads((ROOT / "avatar-pairs.json").read_text(encoding="utf-8"))
    return {
        item["id"]: Avatar(item["id"], item["name"], item["portrait"], item["voice"])
        for item in data["pairs"]
    }


def configured_avatar(identity: str) -> Avatar:
    pairs = configured_avatars()
    if identity not in pairs:
        raise ValueError(f"Unknown pair {identity!r}; choose {', '.join(pairs)}")
    return pairs[identity]


Pair = Avatar
configured_pairs = configured_avatars
configured_pair = configured_avatar

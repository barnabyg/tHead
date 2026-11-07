"""Declared portrait/voice pairs and their asset validation, independent of turns."""

from __future__ import annotations

import hashlib
import importlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from prepare import ROOT

DEFAULT_PAIR = "jfk-zira"


@dataclass(frozen=True)
class Pair:
    id: str
    name: str
    portrait: dict[str, Any]
    voice_lock: Path

    def validate_portrait(self, inputs: Path) -> Path:
        path = inputs / str(self.portrait["filename"])
        if hashlib.sha256(path.read_bytes()).hexdigest() != self.portrait["sha256"]:
            raise ValueError(f"Portrait changed: {path}; preserve/remove it and rerun the launcher")
        image = importlib.import_module("PIL.Image")
        with image.open(path) as picture:
            picture.verify()
        return path


def configured_pairs() -> dict[str, Pair]:
    data = json.loads((ROOT / "avatar-pairs.json").read_text(encoding="utf-8"))
    return {
        item["id"]: Pair(item["id"], item["name"], item["portrait"], ROOT / item["voice_lock"])
        for item in data["pairs"]
    }


def configured_pair(identity: str) -> Pair:
    pairs = configured_pairs()
    if identity not in pairs:
        raise ValueError(f"Unknown pair {identity!r}; choose {', '.join(pairs)}")
    return pairs[identity]

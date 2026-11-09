"""Explicit optional preparation, isolated from speech and ordinary Zira/Hazel use."""

from __future__ import annotations

import importlib
import json
import subprocess  # nosec B404
import threading
from pathlib import Path
from typing import Any

from chatterbox_release import release_readiness
from prepare import ROOT, run


class SpeechPreparation:
    def __init__(self, state: Path, fixture: bool, candidate: bool = False) -> None:
        self.directory, self.fixture, self.candidate = state, fixture, candidate
        self.lock = threading.RLock()
        self.cancelled = threading.Event()
        self.worker: threading.Thread | None = None
        self.state = "idle"
        self.error = ""

    def eligibility(self) -> dict[str, Any]:
        if self.fixture:
            return {
                "available": True,
                "error": "",
                "fixture": True,
                "message": "Synthetic protocol fixture. This does not demonstrate cloned speech.",
            }
        result = release_readiness()
        if self.candidate:
            result = {
                "available": True,
                "error": "",
                "candidate": True,
                "message": "Native release candidate; regular availability remains gated.",
            }
        if result["available"]:
            try:
                torch = importlib.import_module("torch")
                if (
                    not torch.cuda.is_available()
                    or torch.cuda.get_device_name(0) != "NVIDIA GeForce RTX 3090"
                ):
                    return {
                        **result,
                        "available": False,
                        "error": "Local cloned voices require the verified RTX 3090 "
                        "CUDA configuration.",
                    }
            except (ImportError, OSError, RuntimeError) as error:
                return {
                    **result,
                    "available": False,
                    "error": "Local GPU runtime unavailable. Prepare the normal app and retry. "
                    + str(error),
                }
        return result

    def status(self) -> dict[str, Any]:
        with self.lock:
            eligible = self.eligibility()
            assets = json.loads((ROOT / "chatterbox-maintained-lock.json").read_text())["model"][
                "files"
            ]
            installed = self.fixture or (
                (self.directory / "venv/Scripts/python.exe").is_file()
                and all((self.directory / "model" / asset["name"]).is_file() for asset in assets)
            )
            available = bool(eligible["available"] and installed and self.state != "preparing")
            message = eligible.get("message", "")
            error = eligible["error"] or self.error
            if eligible["available"] and not installed and not error:
                error = "Local voice engine is not prepared. Choose Prepare local voices."
            if self.state == "preparing":
                message = "Preparing local voices. Downloads and checks may take several minutes."
            return {
                **eligible,
                "available": available,
                "eligible": eligible["available"],
                "state": self.state,
                "error": error,
                "message": message,
            }

    def start(self) -> dict[str, Any]:
        with self.lock:
            eligible = self.eligibility()
            if not eligible["available"]:
                raise ValueError(eligible["error"])
            if self.worker and self.worker.is_alive():
                raise ValueError("Local voices are already preparing")
            if self.fixture:
                self.state = "ready"
                return self.status()
            self.cancelled = threading.Event()
            self.state, self.error = "preparing", ""
            self.worker = threading.Thread(target=self.prepare, daemon=True)
            self.worker.start()
            return self.status()

    def prepare(self) -> None:
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            with (self.directory / "app-preparation.log").open("wb") as log:
                run(
                    [
                        "pwsh",
                        "-NoProfile",
                        "-File",
                        str(ROOT / "scripts/prepare-chatterbox-maintained.ps1"),
                        "-State",
                        str(self.directory),
                    ],
                    10800,
                    cancelled=self.cancelled,
                    output=log,
                )
            with self.lock:
                self.state = "cancelled" if self.cancelled.is_set() else "ready"
        except (
            OSError,
            RuntimeError,
            ValueError,
            InterruptedError,
            subprocess.SubprocessError,
        ) as error:
            with self.lock:
                self.state = "cancelled" if self.cancelled.is_set() else "failed"
                self.error = (
                    "Preparation cancelled; retry to resume verified downloads."
                    if self.cancelled.is_set()
                    else "Local voice preparation failed. Retry; see app-preparation.log "
                    "for diagnostics. " + str(error)
                )

    def cancel(self) -> None:
        self.cancelled.set()

    def close(self) -> None:
        self.cancel()
        if self.worker:
            self.worker.join(timeout=120)
            if self.worker.is_alive():
                raise TimeoutError("Local voice preparation did not release its process tree")

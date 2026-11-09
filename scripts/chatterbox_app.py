"""Opt-in no-cost reference-voice experiment over the existing conversation/media path."""

from __future__ import annotations

import argparse
import json
import shutil
import threading
import webbrowser
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from avatars import AvatarStore
from chatterbox_voice import ChatterboxVoice, prepare_references, reference_record
from conversation import Conversation
from pairs import Avatar, configured_avatars
from prepare import ROOT, RUNTIME
from provider import Provider
from speech import SpeechVoice
from streaming import LoopbackServer, handler

REFERENCES = {
    "chatterbox-nano-1089": "librispeech-1089-10s",
    "chatterbox-nano-121": "librispeech-121-10s",
}
FIXTURE_TEXTS = {
    "short-1": "Yes, that sounds good.",
    "short-2": "The meeting starts at nine forty-five.",
    "short-3": "I can help with that.",
    "multi-1": "A black hole traps light. We detect one by its effects on nearby matter.",
    "multi-2": "First, check that the microphone is connected and the room is quiet. "
    "Next, record one clear sentence at a comfortable speaking volume. "
    "Finally, listen to the whole answer and make sure the last word is complete.",
}


class ExperimentalStore(AvatarStore):
    def avatars(self) -> dict[str, Avatar]:
        result = super().avatars()
        portrait = configured_avatars()["jfk-zira"].portrait
        for identity, reference in REFERENCES.items():
            name = reference_record(reference)["speaker"]
            result[identity] = Avatar(
                identity, f"JFK / Nano: {name} (experimental)", portrait, identity
            )
        return result

    def require_user_avatar(self, identity: str) -> Avatar:
        if identity in REFERENCES:
            raise ValueError("Experimental built-in avatars cannot be edited or deleted")
        return super().require_user_avatar(identity)


class FixtureProvider(Provider):
    def __init__(self) -> None:
        super().__init__(fixture=True)

    def stream(
        self, messages: list[dict[str, str]], cancelled: threading.Event, fault: str = ""
    ) -> Iterator[dict[str, Any]]:
        question = messages[-1]["content"].strip()
        text = FIXTURE_TEXTS.get(question, FIXTURE_TEXTS["multi-1"])
        if not cancelled.is_set():
            yield {"text": text}
            yield {
                "done": True,
                "truncated": False,
                "usage": {"input_tokens": 100, "output_tokens": 25},
            }


class ExperimentalConversation(Conversation):
    experimental_enabled = True

    def __init__(
        self,
        inputs: Path,
        output: Path,
        state: Path,
        fixture: bool,
        avatar: str,
        configuration: str = "cpu",
    ) -> None:
        self.evaluation_state = state
        self.configuration = configuration
        self.selection = output / "experimental-selection.json"
        prepare_references(state)
        if not avatar:
            avatar = (
                str(json.loads(self.selection.read_text())["avatar"])
                if self.selection.exists()
                else "jfk-zira"
            )
        store = ExperimentalStore(output / "user-data")
        super().__init__(
            inputs,
            output,
            test_backend=fixture,
            diagnostics=True,
            fixture=True,
            budget_path=output / "budget.sqlite3",
            initialize_budget=True,
            pair=avatar,
            avatar_store=store,
        )
        self.provider = FixtureProvider()

    def make_voice(self, avatar: Avatar) -> SpeechVoice:
        if avatar.id in REFERENCES:
            return ChatterboxVoice(
                self.evaluation_state, REFERENCES[avatar.id], self.test_backend, self.configuration
            )
        return super().make_voice(avatar)

    def prepare_voice(self, voice: SpeechVoice) -> None:
        if isinstance(voice, ChatterboxVoice):
            voice.prepare(self.shutdown)
        else:
            super().prepare_voice(voice)

    def speech_pcm(self, text: str, cancelled: threading.Event) -> bytes:
        if isinstance(self.voice, ChatterboxVoice):
            return self.voice.speak(text, cancelled)
        return super().speech_pcm(text, cancelled)

    def prepare_assets(self, pipeline: Any, inference: Any) -> None:
        super().prepare_assets(pipeline, inference)
        self.selection.write_text(
            json.dumps({"avatar": self.selected_pair.id}) + "\n", encoding="utf-8"
        )

    def command(self, path: str, data: dict[str, Any]) -> dict[str, Any]:
        if path == "/experimental":
            if set(data) - {"session", "fault"} or data.get("session") != self.identity:
                raise ValueError("Expected the current session and a declared experimental fault")
            if not isinstance(self.voice, ChatterboxVoice):
                raise ValueError("Select an experimental reference voice first")
            fault = data.get("fault", "")
            if fault not in ("", "delay", "crash", "missing-reference", "missing-model"):
                raise ValueError("Unknown experimental fault")
            self.voice.fault = fault
            return {"ok": True}
        return super().command(path, data)

    def status(self) -> dict[str, Any]:
        result = super().status()
        result["experimental"] = {
            "enabled": True,
            "configuration": self.configuration,
            "fixed_fixture_text": True,
            "reference_id": self.voice.metadata.get("reference_id"),
            "worker_alive": bool(self.voice.metadata.get("worker_alive", False)),
            "voice": dict(self.voice.metadata),
        }
        return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8767)
    parser.add_argument("--output", type=Path, default=RUNTIME / "chatterbox-integration")
    parser.add_argument("--inputs", type=Path, default=RUNTIME / "demo-inputs")
    parser.add_argument("--state", type=Path)
    parser.add_argument("--configuration", choices=("cpu", "cuda", "maintained"), default="cpu")
    parser.add_argument("--avatar", default="")
    parser.add_argument("--test-backend", action="store_true")
    parser.add_argument("--open-browser", action="store_true")
    args = parser.parse_args()
    inputs = args.inputs
    if args.test_backend:
        inputs = args.output / "inputs"
        inputs.mkdir(parents=True, exist_ok=True)
        for name in ("portrait.jpg", "hopper.jpg"):
            shutil.copyfile(ROOT / "tests/fixtures/portrait.jpg", inputs / name)
    state = args.state or (
        args.output / "evaluation"
        if args.test_backend
        else RUNTIME
        / {
            "cpu": "chatterbox-eval",
            "cuda": "chatterbox-eval-gpu",
            "maintained": "chatterbox-maintained",
        }[args.configuration]
    )
    app = ExperimentalConversation(
        inputs, args.output, state, args.test_backend, args.avatar, args.configuration
    )
    server = LoopbackServer(("127.0.0.1", args.port), handler(app))
    lifetime = threading.Timer(7200, server.shutdown)
    lifetime.daemon = True
    lifetime.start()
    print(f"LISTEN http://127.0.0.1:{server.server_port}", flush=True)
    if args.open_browser:
        browser = threading.Timer(
            2, lambda: webbrowser.open(f"http://127.0.0.1:{server.server_port}")
        )
        browser.daemon = True
        browser.start()
    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        pass
    finally:
        lifetime.cancel()
        server.server_close()
        app.shutdown.set()
        if app.current:
            app.stop(app.current.id)
        with app.condition:
            app.condition.notify_all()
        app.worker.join(timeout=120)
        app.voice.close()
        if app.worker.is_alive():
            raise TimeoutError("Experimental application worker did not release")


if __name__ == "__main__":
    main()

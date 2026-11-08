"""Single-user, loopback conversational application over the proven speech pipeline."""

from __future__ import annotations

import argparse
import base64
import os
import re
import threading
import time
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from avatars import AvatarStore, decode_portrait, user_data_directory, voice_catalogue
from budget import PRICES, Budget, BudgetError
from pairs import DEFAULT_PAIR, Avatar
from prepare import RUNTIME
from provider import (
    INPUT_BOUND,
    INSTRUCTIONS,
    MODEL,
    MODEL_DEFAULTS,
    MODEL_ERRORS,
    MODEL_LEVELS,
    OUTPUT_TOKENS,
    Provider,
    validate_level,
    validate_model,
)
from speech import SpeechVoice, Voice
from streaming import Demonstration, LoopbackServer, Session, handler

PAIR_FAULTS = {
    "pair-portrait-missing": "Portrait missing; rerun the preparation/launch command",
    "pair-portrait-unreadable": "Portrait unreadable; restore read permissions and retry",
    "pair-portrait-invalid": "Portrait invalid; restore the declared portrait and retry",
    "pair-voice-missing": "Desktop voice unavailable; install the declared legacy English voice",
    "pair-voice-invalid": "Voice assets invalid; restore the declared Windows voice version",
    "pair-prepare": "Avatar failed after voice preparation; retry or select another avatar",
    "pair-delay-fail": "Delayed avatar preparation failed; retry or select another avatar",
}


class Turn(Session):
    def __init__(
        self, directory: Path, fragment_frames: int, conversation: str, question: str
    ) -> None:
        super().__init__(directory, fragment_frames)
        self.conversation = conversation
        self.question = question
        self.answer = ""
        self.messages = [{"role": "user", "content": question}]
        self.truncated = False
        self.usage: dict[str, Any] = {}
        self.input_bound = 0
        self.omitted = 0
        self.reservation = ""
        self.request_id = ""
        self.progressive = True
        self.pair = ""
        self.text = ["conversation"]
        self.provider = Provider()

    def save(self) -> None:
        # Conversation text and transcript events remain in memory only.
        pass

    def snapshot(self) -> dict[str, Any]:
        return {
            **super().snapshot(),
            "session": self.conversation,
            "answer": self.answer,
            "truncated": self.truncated,
            "usage": dict(self.usage),
            "inputBound": self.input_bound,
            "request": self.request_id,
            "pair": self.pair,
            "model": self.provider.model,
            "thinkingLevel": self.provider.thinking_level,
        }


class Conversation(Demonstration):
    page = "conversation.html"

    def command(self, path: str, data: dict[str, Any]) -> dict[str, Any]:
        if path == "/settings":
            return self.configure(data)
        if path == "/avatars":
            return self.create_avatar(data)
        if path in ("/avatars/update", "/avatars/delete"):
            return self.change_avatar(data, path.endswith("delete"))
        if path == "/reset":
            return self.reset(str(data.get("session", "")))
        if path == "/cancel":
            return self.cancel(str(data.get("session", "")), str(data.get("request", "")))
        if path == "/select":
            return self.select(
                str(data.get("session", "")),
                str(data.get("avatar", data.get("pair", ""))),
                str(data.get("fault", "")),
            )
        return self.ask(
            str(data.get("session", "")),
            data.get("question"),
            str(data.get("fault", "")),
            str(data.get("request", "")),
        ).snapshot()

    def __init__(
        self,
        inputs: Path,
        directory: Path,
        test_backend: bool = False,
        diagnostics: bool = False,
        model: str = MODEL,
        fixture: bool = False,
        budget_path: Path | None = None,
        initialize_budget: bool = False,
        pair: str = DEFAULT_PAIR,
        user_data: Path | None = None,
        avatar_store: AvatarStore | None = None,
    ) -> None:
        self.avatars = avatar_store or AvatarStore(
            user_data or (directory / "user-data" if test_backend else user_data_directory())
        )
        self.voices = voice_catalogue(test_backend)
        self.selected_pair = self.avatars.get(pair)
        self.active_pair = ""
        self.pair_sequence = 0
        self.pair_preparation_seconds = 0.0
        self.pair_fault = ""
        self.identity = uuid.uuid4().hex
        self.transcript: list[Turn] = []
        self.cancelled_requests: set[str] = set()
        self.provider = Provider(model, test_backend or fixture)
        self.settings_message = ""
        self.budget: Budget | None = None
        self.budget_error = ""
        try:
            self.budget = Budget(
                budget_path or directory / "budget.sqlite3",
                initialize=initialize_budget or test_backend,
            )
        except BudgetError as error:
            self.budget_error = str(error)
        super().__init__(inputs, directory, test_backend, 8, True, diagnostics or fixture)

    def configure(self, data: dict[str, Any]) -> dict[str, Any]:
        with self.condition:
            if data.get("session") != self.identity:
                raise ValueError("Stale session; reload before changing settings")
            if set(data) - {"session", "model", "thinkingLevel"}:
                raise ValueError("Unknown setting; reload Settings and retry")
            model = validate_model(data.get("model", self.provider.model))
            level = data.get("thinkingLevel", self.provider.thinking_level)
            message = ""
            if "thinkingLevel" not in data and level not in MODEL_LEVELS[model]:
                level = MODEL_DEFAULTS[model]
                message = f"Thinking level changed to {level}; the selected model requires it."
            validate_level(model, level)
            self.provider = Provider(model, self.provider.fixture, level)
            self.settings_message = message
            return self.status()

    def settings(self) -> dict[str, Any]:
        return {
            "model": self.provider.model,
            "thinkingLevel": self.provider.thinking_level,
            "message": self.settings_message,
            "models": [
                {
                    "id": model,
                    "available": not error,
                    "error": error,
                    "levels": MODEL_LEVELS.get(model, ()),
                    "defaultLevel": MODEL_DEFAULTS.get(model),
                }
                for model, error in MODEL_ERRORS.items()
            ],
        }

    def create_avatar(self, data: dict[str, Any]) -> dict[str, Any]:
        # Saving is independent of turn state: no selection, context or provider mutation.
        if data.get("session") != self.identity:
            raise ValueError("Stale session; reload before saving")
        voice = data.get("voice")
        self.validate_voice(voice)
        avatar = self.avatars.create(data.get("name"), voice, data.get("image"))
        return {"id": avatar.id, "name": avatar.name}

    def validate_voice(self, voice: Any) -> None:
        available = voice_catalogue(self.test_backend, str(voice))
        if not any(v["id"] == voice and v["available"] for v in available):
            raise ValueError("Voice unavailable; restore the supported Windows voice and retry")

    def portrait(self, identity: str) -> bytes:
        avatar = self.avatars.get(identity)
        if avatar.portrait.get("stored"):
            return self.avatars.portrait(identity)
        return (self.inputs / str(avatar.portrait["filename"])).read_bytes()

    def change_avatar(self, data: dict[str, Any], deleting: bool) -> dict[str, Any]:
        identity = str(data.get("id", ""))
        with self.condition:
            if data.get("session") != self.identity:
                raise ValueError("Stale session; reload before changing avatars")
            if not self.pair_selectable():
                raise ValueError("Change avatars between turns; Stop and wait for resource release")
            previous = self.avatars.require_user_avatar(identity)
            if deleting:
                self.avatars.delete(identity, data.get("name"))
                avatar = self.avatars.get(DEFAULT_PAIR)
            else:
                voice = data.get("voice", previous.voice)
                self.validate_voice(voice)
                avatar = self.avatars.update(
                    identity, data.get("name", previous.name), voice, data.get("image")
                )
            if self.selected_pair.id == identity:
                # Invalidate prepared media even when the stable avatar ID is unchanged.
                self.active_pair = ""
                self.select(self.identity, avatar.id)
            return {"id": avatar.id, "name": previous.name if deleting else avatar.name}

    def prepare_assets(self, pipeline: Any, inference: Any) -> None:
        pair = self.selected_pair
        if not pair.portrait.get("stored"):
            # The derived input is needed only while a saved avatar is selected.
            # Remove its private bytes on fallback without touching source/bundled images.
            (self.directory / "imported-portrait.png").unlink(missing_ok=True)
        if self.pair_fault in ("pair-delay", "pair-delay-fail"):
            time.sleep(2)  # Simulated preparation completing after Stop/reset.
        candidate = self.make_voice(pair)
        try:
            self.pair_probe(
                "pair-portrait-missing", "pair-portrait-unreadable", "pair-portrait-invalid"
            )
            portrait = (
                (
                    self.inputs / str(pair.portrait["filename"])
                    if self.test_backend
                    else pair.validate_portrait(self.inputs)
                )
                if not pair.portrait.get("stored")
                else self.imported_portrait(pair.id)
            )
            self.pair_probe("pair-voice-missing")
            self.prepare_voice(candidate)
            self.pair_probe("pair-voice-invalid")
            if not self.test_backend:
                inference.get_base_data(pipeline, str(portrait), 42, False)
            self.pair_probe("pair-prepare", "pair-delay-fail")
            self.voice.close()
            with self.condition:
                self.voice = candidate
                self.portrait_path = portrait
                self.active_pair = pair.id
                self.loading["tts"] = candidate.metadata
        finally:
            if self.voice is not candidate:
                candidate.close()

    def make_voice(self, avatar: Avatar) -> SpeechVoice:
        return Voice(avatar.voice_lock)

    def prepare_voice(self, voice: SpeechVoice) -> None:
        if not self.test_backend:
            voice.prepare(self.shutdown)

    def imported_portrait(self, identity: str) -> Path:
        # One derived model input per server output directory, never the user's source path.
        # The authoritative image remains in the atomic database record.
        path = self.directory / "imported-portrait.png"
        portrait = decode_portrait(
            base64.b64encode(self.avatars.portrait(identity)).decode("ascii")
        )
        path.write_bytes(portrait)
        return path

    def pair_probe(self, *faults: str) -> None:
        if self.pair_fault in faults:
            raise RuntimeError(PAIR_FAULTS[self.pair_fault])

    def load_assets(self, pipeline: Any, inference: Any) -> None:
        started = time.perf_counter()
        try:
            super().load_assets(pipeline, inference)
        except Exception as error:
            with self.condition:
                self.ready = False
                self.state = "idle"
                self.error = (
                    f"{self.selected_pair.name} preparation failed: "
                    f"{type(error).__name__}: {error}. "
                    "See docs/runtime/windows-pairs.md; select an available avatar to recover."
                )
                self.condition.notify_all()
        finally:
            self.pair_preparation_seconds = time.perf_counter() - started

    def select(self, identity: str, pair_id: str, fault: str = "") -> dict[str, Any]:
        pair = self.avatars.get(pair_id)
        if fault and (not self.diagnostics or fault not in (*PAIR_FAULTS, "pair-delay")):
            raise ValueError("Unknown pair diagnostic; launch with --diagnostics")
        with self.condition:
            if identity != self.identity:
                raise ValueError("Stale session")
            if not self.pair_selectable():
                raise ValueError("Select between turns; Stop and wait for resource release")
            if self.ready and pair.id == self.active_pair:
                return self.status()
            self.selected_pair = pair
            self.error = ""
            self.pair_fault = fault
            self.pair_sequence += 1
            self.ready = False
            self.state = "selecting"
            self.current = None
            self.condition.notify_all()
            return self.status()

    def pair_selectable(self) -> bool:
        current = self.current
        playback = (
            current
            and current.state == "complete"
            and not any(e["event"] == "ended" for e in current.events)
        )
        return self.state == "idle" and not playback

    def readiness(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "ready": self.ready,
            "error": self.error,
            "loading": self.loading,
        }

    def status(self) -> dict[str, Any]:
        with self.condition:
            avatars = [
                {
                    "id": p.id,
                    "name": p.name,
                    "voice": p.voice,
                    "editable": bool(p.portrait.get("stored")),
                }
                for p in self.avatars.avatars().values()
            ]
            budget: dict[str, Any] = {"usable": False, "error": self.budget_error}
            if self.budget:
                try:
                    budget = self.budget.snapshot()
                except BudgetError as error:
                    budget["error"] = str(error)
            result = {
                **super().status(),
                "conversationEnabled": True,
                "pairs": avatars,
                "avatars": avatars,
                "voices": self.voices,
                "avatarStorageError": self.avatars.error or self.avatars.record_error,
                "activeAvatar": self.active_pair,
                "selectedAvatar": self.selected_pair.id,
                "activePair": self.active_pair,
                "selectedPair": self.selected_pair.id,
                "pairSequence": self.pair_sequence,
                "pairSelectable": self.pair_selectable(),
                "pairPreparationSeconds": self.pair_preparation_seconds,
                "session": self.identity,
                "model": self.provider.model,
                "settings": self.settings(),
                "fixtureProvider": self.provider.fixture,
                "budget": budget,
                "contextOmitted": self.current.omitted if isinstance(self.current, Turn) else 0,
                "configurationError": ""
                if self.provider.fixture or os.environ.get("OPENAI_API_KEY")
                else "Set OPENAI_API_KEY in the backend and restart",
                "transcript": [
                    {
                        "id": t.id,
                        "question": t.question,
                        "answer": t.answer,
                        "state": t.state,
                        "truncated": t.truncated,
                        "usage": t.usage,
                        "pair": t.pair,
                        "model": t.provider.model,
                        "thinkingLevel": t.provider.thinking_level,
                    }
                    for t in self.transcript
                ],
            }
            if isinstance(self.current, Turn) and self.current.conversation != self.identity:
                result["run"] = None
            if not budget["usable"]:
                result["configurationError"] = budget["error"]
            elif self.provider.model not in PRICES:
                result["configurationError"] = (
                    "Unknown model pricing; choose an available model in Settings"
                )
            return result

    def reset(self, identity: str) -> dict[str, Any]:
        with self.condition:
            if identity != self.identity:
                raise ValueError("Session was lost or reset; reload the conversation")
            if self.current and not self.current.cancelled.is_set():
                self.stop(self.current.id)
            self.identity = uuid.uuid4().hex
            self.transcript.clear()
            self.cancelled_requests.clear()
            if self.state == "idle":
                self.current = None
            return self.status()

    def cancel(self, identity: str, request_id: str) -> dict[str, Any]:
        with self.condition:
            if identity != self.identity:
                raise ValueError("Stale session")
            if not re.fullmatch(r"[a-f0-9-]{32,36}", request_id):
                raise ValueError("Expected response request identity")
            if len(self.cancelled_requests) >= 512:
                raise ValueError("Start a New conversation before further requests")
            self.cancelled_requests.add(request_id)
            current = self.current
            if isinstance(current, Turn) and current.request_id == request_id:
                self.stop(current.id)
            return {"ok": True}

    def context(self, question: str) -> tuple[list[dict[str, str]], int, int]:
        # UTF-8 bytes upper-bound text BPE tokens, with explicit framing margin.
        def bound(messages: list[dict[str, str]]) -> int:
            return (
                len(INSTRUCTIONS.encode())
                + 256
                + sum(len(m["content"].encode()) + 64 for m in messages)
            )

        messages = [{"role": "user", "content": question}]
        if bound(messages) > INPUT_BOUND:
            raise ValueError("Question exceeds the configured input allowance")
        retained = 0
        for turn in reversed(self.transcript):
            exchange = [{"role": "user", "content": turn.question}]
            if turn.state == "complete":
                exchange.append({"role": "assistant", "content": turn.answer})
            if bound(exchange + messages) > INPUT_BOUND:
                break
            messages = exchange + messages
            retained += 1
        return messages, bound(messages), len(self.transcript) - retained

    def ask(self, identity: str, question: Any, fault: str = "", request_id: str = "") -> Turn:
        if not isinstance(question, str) or not question.strip() or len(question) > 1200:
            raise ValueError("Enter a question of 1–1200 characters")
        if fault and (
            not self.diagnostics
            or fault
            not in (
                "llm",
                "llm-delay",
                "llm-connect",
                "llm-settings",
                "missing-completion",
                "long",
                "unbroken",
                "markup",
                "truncate",
                "tts",
                "tts-delay",
                "media",
                "buffer-delay",
                "dispatch-delay",
            )
        ):
            raise ValueError("Unknown diagnostic; launch with --diagnostics")
        with self.condition:
            if identity != self.identity:
                raise ValueError("Session was lost or reset; reload the conversation")
            if not re.fullmatch(r"[a-f0-9-]{32,36}", request_id):
                raise ValueError("Expected response request identity")
            if request_id in self.cancelled_requests:
                raise ValueError("Response was cancelled before dispatch")
            if not self.ready or self.state != "idle":
                raise ValueError("Wait for readiness and resource release")
            if not self.provider.fixture and not os.environ.get("OPENAI_API_KEY"):
                raise ValueError("Set OPENAI_API_KEY in the backend and restart")
            if len(self.transcript) >= 100:
                raise ValueError("Session reached 100 turns; start a New conversation")
            validate_level(self.provider.model, self.provider.thinking_level)
            messages, input_bound, omitted = self.context(question.strip())
            if not self.budget:
                raise ValueError(self.budget_error)
            # The only application provider-request boundary. Every explicit retry
            # enters here and receives its own durable reservation before dispatch.
            reservation = self.budget.reserve(self.provider.model, input_bound, OUTPUT_TOKENS)
            session = Turn(self.directory, self.fragment_frames, self.identity, question.strip())
            session.provider = self.provider
            session.reservation = reservation
            session.request_id = request_id
            session.pair = self.active_pair
            session.messages, session.input_bound, session.omitted = messages, input_bound, omitted
            session.fault = fault
            self.current = session
            self.transcript.append(session)
            self.state = "generating"
            self.condition.notify_all()
            return session

    def finish_speech(self, session: Session, producer: threading.Thread | None) -> None:
        super().finish_speech(session, producer)
        if isinstance(session, Turn) and self.budget:
            try:
                # Provider output_tokens already includes reasoning; keep its detail separate.
                details = session.usage.get("output_tokens_details") or {}
                reasoning = details.get("reasoning_tokens") if isinstance(details, dict) else None
                session.usage = self.budget.settle(
                    session.reservation,
                    session.usage.get("input_tokens"),
                    session.usage.get("output_tokens"),
                )
                output = session.usage.get("output_tokens")
                if type(reasoning) is int and type(output) is int and 0 <= reasoning <= output:
                    session.usage["reasoning_tokens"] = reasoning
            except BudgetError:
                # The committed reservation remains charged; later dispatch fails closed.
                self.budget_error = (
                    "Budget reconciliation failed; restore accounting before retrying"
                )

    def phrases(self, session: Session) -> Iterator[str]:
        if not isinstance(session, Turn):
            yield from super().phrases(session)
            return
        pending = ""
        done = False
        session.event("llm-connect")
        if session.provider.fixture:
            session.event(
                "provider-request",
                messages=session.messages,
                configuration=session.provider.configuration(),
            )
        for event in session.provider.stream(session.messages, session.cancelled, session.fault):
            if session.cancelled.is_set():
                return
            if "text" in event:
                delta = event["text"]
                if not isinstance(delta, str) or len(session.answer) + len(delta) > 4096:
                    raise ValueError("Provider answer exceeded the text allowance")
                with session.condition:
                    if not session.answer:
                        session.event("llm-first-text")
                    session.answer += delta
                pending += delta
                while pending:
                    sentence = re.search(r"[.!?]\s", pending)
                    cut = sentence.end() if sentence and sentence.end() <= 180 else 0
                    if not cut and len(pending) > 180:
                        cut = pending.rfind(" ", 0, 181) + 1 or 180
                    if not cut:
                        break
                    phrase, pending = pending[:cut], pending[cut:]
                    if phrase.strip():
                        yield phrase
            elif event.get("done"):
                done = True
                session.truncated = bool(event.get("truncated"))
                session.usage = event.get("usage", {})
                session.event("llm-complete", truncated=session.truncated)
                break
        if session.cancelled.is_set():
            return
        if not done or not session.answer.strip():
            raise ValueError(
                "Provider returned no completed answer within the output allowance; "
                "try a lower thinking level in Settings or submit again"
            )
        if pending.strip():
            yield pending


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--inputs", type=Path, default=RUNTIME / "demo-inputs")
    parser.add_argument("--output", type=Path, default=RUNTIME / "conversation")
    parser.add_argument("--test-backend", action="store_true")
    parser.add_argument("--fixture-provider", action="store_true")
    parser.add_argument("--diagnostics", action="store_true")
    parser.add_argument("--model", default=os.environ.get("THEAD_MODEL", MODEL))
    parser.add_argument("--budget", type=Path)
    parser.add_argument("--initialize-budget", action="store_true")
    parser.add_argument("--user-data", type=Path)
    parser.add_argument(
        "--avatar",
        "--pair",
        dest="pair",
        default=os.environ.get("THEAD_AVATAR", os.environ.get("THEAD_PAIR", DEFAULT_PAIR)),
    )
    args = parser.parse_args()
    app = Conversation(
        args.inputs,
        args.output,
        args.test_backend,
        args.diagnostics,
        args.model,
        args.fixture_provider,
        args.budget
        or (
            args.output / "budget.sqlite3"
            if args.test_backend
            else RUNTIME
            / (
                "conversation-fixture-budget.sqlite3"
                if args.fixture_provider
                else "conversation-budget.sqlite3"
            )
        ),
        args.initialize_budget,
        args.pair,
        args.user_data,
    )
    server = LoopbackServer(("127.0.0.1", args.port), handler(app))
    lifetime = threading.Timer(7200, server.shutdown)
    lifetime.daemon = True
    lifetime.start()
    print(f"LISTEN http://127.0.0.1:{server.server_port}", flush=True)
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


if __name__ == "__main__":
    main()

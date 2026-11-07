"""Single-user, loopback conversational application over the proven speech pipeline."""

from __future__ import annotations

import argparse
import os
import re
import threading
import time
import uuid
from collections.abc import Iterator
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any

from budget import PRICES, Budget, BudgetError
from pairs import DEFAULT_PAIR, configured_pair, configured_pairs
from prepare import RUNTIME
from provider import INPUT_BOUND, INSTRUCTIONS, MODEL, OUTPUT_TOKENS, Provider
from speech import Voice
from streaming import Demonstration, Session, handler

PAIR_FAULTS = {
    "pair-portrait-missing": "Portrait missing; rerun the preparation/launch command",
    "pair-portrait-unreadable": "Portrait unreadable; restore read permissions and retry",
    "pair-portrait-invalid": "Portrait invalid; restore the declared portrait and retry",
    "pair-voice-missing": "Desktop voice unavailable; install the declared legacy English voice",
    "pair-voice-invalid": "Voice assets invalid; restore the declared Windows voice version",
    "pair-prepare": "Avatar failed after voice preparation; retry or select another pair",
    "pair-delay-fail": "Delayed avatar preparation failed; retry or select another pair",
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
        }


class Conversation(Demonstration):
    page = "conversation.html"

    def command(self, path: str, data: dict[str, Any]) -> dict[str, Any]:
        if path == "/reset":
            return self.reset(str(data.get("session", "")))
        if path == "/cancel":
            return self.cancel(str(data.get("session", "")), str(data.get("request", "")))
        if path == "/select":
            return self.select(
                str(data.get("session", "")),
                str(data.get("pair", "")),
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
    ) -> None:
        self.selected_pair = configured_pair(pair)
        self.active_pair = ""
        self.pair_sequence = 0
        self.pair_preparation_seconds = 0.0
        self.pair_fault = ""
        self.identity = uuid.uuid4().hex
        self.transcript: list[Turn] = []
        self.cancelled_requests: set[str] = set()
        self.provider = Provider(model, test_backend or fixture)
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

    def prepare_assets(self, pipeline: Any, inference: Any) -> None:
        pair = self.selected_pair
        if self.pair_fault in ("pair-delay", "pair-delay-fail"):
            time.sleep(2)  # Simulated preparation completing after Stop/reset.
        candidate = Voice(pair.voice_lock)
        try:
            self.pair_probe(
                "pair-portrait-missing", "pair-portrait-unreadable", "pair-portrait-invalid"
            )
            portrait = (
                self.inputs / str(pair.portrait["filename"])
                if self.test_backend
                else pair.validate_portrait(self.inputs)
            )
            self.pair_probe("pair-voice-missing")
            if not self.test_backend:
                candidate.prepare(self.shutdown)
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
                    "See docs/runtime/windows-pairs.md; select an available pair to recover."
                )
                self.condition.notify_all()
        finally:
            self.pair_preparation_seconds = time.perf_counter() - started

    def select(self, identity: str, pair_id: str, fault: str = "") -> dict[str, Any]:
        pair = configured_pair(pair_id)
        if fault and (not self.diagnostics or fault not in (*PAIR_FAULTS, "pair-delay")):
            raise ValueError("Unknown pair diagnostic; launch with --diagnostics")
        with self.condition:
            if identity != self.identity:
                raise ValueError("Stale session")
            current = self.current
            playback = (
                current
                and current.state == "complete"
                and not any(e["event"] == "ended" for e in current.events)
            )
            if self.state != "idle" or playback:
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

    def readiness(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "ready": self.ready,
            "error": self.error,
            "loading": self.loading,
        }

    def status(self) -> dict[str, Any]:
        with self.condition:
            budget: dict[str, Any] = {"usable": False, "error": self.budget_error}
            if self.budget:
                try:
                    budget = self.budget.snapshot()
                except BudgetError as error:
                    budget["error"] = str(error)
            result = {
                **super().status(),
                "conversationEnabled": True,
                "pairs": [{"id": p.id, "name": p.name} for p in configured_pairs().values()],
                "activePair": self.active_pair,
                "selectedPair": self.selected_pair.id,
                "pairSequence": self.pair_sequence,
                "pairPreparationSeconds": self.pair_preparation_seconds,
                "session": self.identity,
                "model": self.provider.model,
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
                    }
                    for t in self.transcript
                ],
            }
            if isinstance(self.current, Turn) and self.current.conversation != self.identity:
                result["run"] = None
            if not budget["usable"]:
                result["configurationError"] = budget["error"]
            elif self.provider.model not in PRICES:
                result["configurationError"] = "Unknown model pricing; select gpt-6-luna"
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
            messages, input_bound, omitted = self.context(question.strip())
            if not self.budget:
                raise ValueError(self.budget_error)
            # The only application provider-request boundary. Every explicit retry
            # enters here and receives its own durable reservation before dispatch.
            reservation = self.budget.reserve(self.provider.model, input_bound, OUTPUT_TOKENS)
            session = Turn(self.directory, self.fragment_frames, self.identity, question.strip())
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
                session.usage = self.budget.settle(
                    session.reservation,
                    session.usage.get("input_tokens"),
                    session.usage.get("output_tokens"),
                )
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
        if self.provider.fixture:
            session.event("provider-request", messages=session.messages)
        for event in self.provider.stream(session.messages, session.cancelled, session.fault):
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
            raise ValueError("Provider returned no completed answer; submit again")
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
    parser.add_argument("--pair", default=os.environ.get("THEAD_PAIR", DEFAULT_PAIR))
    args = parser.parse_args()
    try:
        configured_pair(args.pair)
    except ValueError as error:
        parser.error(str(error))
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
    )
    server = ThreadingHTTPServer(("127.0.0.1", args.port), handler(app))
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

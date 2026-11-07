"""Single-user, loopback conversational application over the proven speech pipeline."""

from __future__ import annotations

import argparse
import os
import re
import threading
import uuid
from collections.abc import Iterator
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any

from prepare import RUNTIME
from provider import MODEL, Provider
from streaming import Demonstration, Session, handler


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
        self.progressive = True
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
        }


class Conversation(Demonstration):
    page = "conversation.html"

    def command(self, path: str, data: dict[str, Any]) -> dict[str, Any]:
        return self.ask(
            str(data.get("session", "")), data.get("question"), str(data.get("fault", ""))
        ).snapshot()

    def __init__(
        self,
        inputs: Path,
        directory: Path,
        test_backend: bool = False,
        diagnostics: bool = False,
        model: str = MODEL,
        fixture: bool = False,
    ) -> None:
        self.identity = uuid.uuid4().hex
        self.transcript: list[Turn] = []
        self.provider = Provider(model, test_backend or fixture)
        super().__init__(inputs, directory, test_backend, 8, True, diagnostics or fixture)

    def readiness(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "ready": self.ready,
            "error": self.error,
            "loading": self.loading,
        }

    def status(self) -> dict[str, Any]:
        with self.condition:
            return {
                **super().status(),
                "conversationEnabled": True,
                "session": self.identity,
                "model": self.provider.model,
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
                    }
                    for t in self.transcript
                ],
            }

    def ask(self, identity: str, question: Any, fault: str = "") -> Turn:
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
            if not self.ready or self.state != "idle":
                raise ValueError("Wait for readiness and resource release")
            if not self.provider.fixture and not os.environ.get("OPENAI_API_KEY"):
                raise ValueError("Set OPENAI_API_KEY in the backend and restart")
            session = Turn(self.directory, self.fragment_frames, self.identity, question.strip())
            session.fault = fault
            self.current = session
            self.transcript.append(session)
            self.state = "generating"
            self.condition.notify_all()
            return session

    def phrases(self, session: Session) -> Iterator[str]:
        if not isinstance(session, Turn):
            yield from super().phrases(session)
            return
        pending = ""
        done = False
        session.event("llm-connect")
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
    args = parser.parse_args()
    app = Conversation(
        args.inputs,
        args.output,
        args.test_backend,
        args.diagnostics,
        args.model,
        args.fixture_provider,
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

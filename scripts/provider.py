"""Bounded, stateless OpenAI Responses stream. Credentials never enter diagnostics."""

from __future__ import annotations

import http.client
import json
import os
import socket
import threading
import time
from collections.abc import Iterator
from typing import Any

INSTRUCTIONS = (
    "Answer in English using approximately two to four concise spoken sentences. "
    "Use plain text, no markdown. Finish the answer within 240 output tokens."
)
MODEL = "gpt-6-luna"
OUTPUT_TOKENS = 384
INPUT_BOUND = 8192


class Provider:
    def __init__(self, model: str = MODEL, fixture: bool = False) -> None:
        self.model = model
        self.fixture = fixture

    def stream(
        self, messages: list[dict[str, str]], cancelled: threading.Event, fault: str = ""
    ) -> Iterator[dict[str, Any]]:
        if self.fixture:
            yield from self.synthetic(messages, cancelled, fault)
            return
        key = os.environ.get("OPENAI_API_KEY", "")
        if not key:
            raise ValueError("Set OPENAI_API_KEY in the backend environment and restart")
        connection = http.client.HTTPSConnection("api.openai.com", timeout=15)
        started = time.monotonic()
        finished = threading.Event()

        def disconnect() -> None:
            # Wake a blocked read; closing a buffered HTTPResponse alone can wait for it.
            stream = connection.sock
            if stream is not None:
                try:
                    stream.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
            connection.close()

        def watch() -> None:
            while not finished.wait(0.05):
                if cancelled.is_set():
                    disconnect()
                    return

        watcher = threading.Thread(target=watch, daemon=True)
        watcher.start()
        # Hard deadline also interrupts a server that sends endless non-text events.
        deadline = threading.Timer(180, disconnect)
        deadline.daemon = True
        deadline.start()
        try:
            connection.request(
                "POST",
                "/v1/responses",
                body=json.dumps(
                    {
                        "model": self.model,
                        "instructions": INSTRUCTIONS,
                        "input": messages,
                        "stream": True,
                        "store": False,
                        "service_tier": "default",
                        "reasoning": {"effort": "none"},
                        "max_output_tokens": OUTPUT_TOKENS,
                    }
                ).encode(),
                headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
            )
            response = connection.getresponse()
            if response.status != 200:
                # Never reflect provider bodies, headers or credentials into the browser/logs.
                raise ValueError(
                    f"OpenAI HTTP {response.status}; check backend key, model access and quota"
                )
            total = 0
            while not cancelled.is_set():
                if time.monotonic() - started > 180:
                    raise TimeoutError("OpenAI stream exceeded three minutes")
                line = response.readline(65537)
                total += len(line)
                if len(line) > 65536 or total > 2_000_000:
                    raise ValueError("OpenAI stream exceeded event allowance")
                if not line:
                    raise ValueError("OpenAI disconnected before completion; submit again")
                if not line.startswith(b"data: "):
                    continue
                event = json.loads(line[6:])
                kind = event.get("type")
                if kind == "response.output_text.delta":
                    yield {"text": event["delta"]}
                elif kind in ("response.completed", "response.incomplete"):
                    value = event["response"]
                    usage = value.get("usage") or {}
                    yield {"done": True, "truncated": kind == "response.incomplete", "usage": usage}
                    return
                elif kind in ("error", "response.failed"):
                    raise ValueError("OpenAI generation failed; submit a new question to retry")
        except (OSError, http.client.HTTPException) as error:
            raise ValueError("OpenAI connection failed or timed out; check connectivity") from error
        finally:
            finished.set()
            deadline.cancel()
            connection.close()
            watcher.join(timeout=5)

    @staticmethod
    def synthetic(
        messages: list[dict[str, str]], cancelled: threading.Event, fault: str
    ) -> Iterator[dict[str, Any]]:
        if fault == "llm-connect":
            cancelled.wait(3)
        if cancelled.is_set():
            return
        if fault == "llm":
            raise ValueError("Injected provider failure")
        text = "A black hole traps light. We detect one by its effects on nearby matter."
        if len(messages) > 1:
            text += " Earlier question: " + messages[0]["content"][:80]
        if fault == "long":
            text = "word " * 90 + "Final partial"
        elif fault == "unbroken":
            text = "a" * 400 + " final"
        elif fault == "markup":
            text = "<script>alert('text')</script> Safe plain text."
        # Arbitrary, single-character token boundaries exercise phrase assembly.
        for index, character in enumerate(text):
            if cancelled.is_set():
                return
            if fault == "llm-delay" and index == 26:
                cancelled.wait(3)
            yield {"text": character}
        if fault == "missing-completion":
            raise ValueError("Injected disconnect before completion")
        yield {
            "done": True,
            "truncated": fault == "truncate",
            "usage": {"input_tokens": 100, "output_tokens": 25},
        }

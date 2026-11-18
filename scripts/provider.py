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

from model_catalog import DEFAULT_EFFORT, FIXTURE_MODELS, MODEL, ModelInfo

OUTPUT_TOKENS = 384
ANSWER_TOKEN_TARGET = 240
INPUT_BOUND = 8192


def validate_model(model: Any, models: dict[str, ModelInfo]) -> ModelInfo:
    if not isinstance(model, str) or model not in models:
        raise ValueError("Unknown model; choose an available model in Settings")
    info = models[model]
    if info.error or not info.rates:
        raise ValueError(info.error or "Model pricing unavailable")
    return info


def validate_level(info: ModelInfo, level: Any) -> None:
    if not isinstance(level, str) or level not in info.levels:
        raise ValueError("Unsupported thinking level for this model; choose a level in Settings")


class Provider:
    def __init__(
        self,
        model: str = MODEL,
        fixture: bool = False,
        thinking_level: str | None = None,
        *,
        models: dict[str, ModelInfo] | None = None,
        max_output_tokens: int = OUTPUT_TOKENS,
        answer_token_target: int = ANSWER_TOKEN_TARGET,
        input_token_limit: int = INPUT_BOUND,
    ) -> None:
        for label, value, minimum, maximum in (
            ("Maximum output tokens", max_output_tokens, 16, 32768),
            ("Answer token target", answer_token_target, 1, 32768),
            ("Input token allowance", input_token_limit, 512, 131072),
        ):
            if type(value) is not int or not minimum <= value <= maximum:
                raise ValueError(f"{label} must be a whole number from {minimum} to {maximum}")
        if answer_token_target > max_output_tokens:
            raise ValueError("Answer token target must not exceed maximum output tokens")
        self.model = model
        self.models = FIXTURE_MODELS if models is None else models
        self.fixture = fixture
        self.max_output_tokens = max_output_tokens
        self.answer_token_target = answer_token_target
        self.input_token_limit = input_token_limit
        self.thinking_level = (
            self.models.get(model, ModelInfo()).default
            if thinking_level is None
            else thinking_level
        )

    @property
    def instructions(self) -> str:
        return (
            "Answer in English using approximately two to four concise spoken sentences. "
            "Use plain text, no markdown. "
            f"Finish the answer within {self.answer_token_target} output tokens."
        )

    def token_settings(self) -> dict[str, int]:
        return {
            "maxOutputTokens": self.max_output_tokens,
            "answerTokenTarget": self.answer_token_target,
            "inputTokenLimit": self.input_token_limit,
        }

    def configuration(self) -> dict[str, Any]:
        return {
            "model": self.model,
            **(
                {"reasoning": {"effort": self.thinking_level}}
                if self.thinking_level != DEFAULT_EFFORT
                else {}
            ),
            "max_output_tokens": self.max_output_tokens,
        }

    def stream(
        self, messages: list[dict[str, str]], cancelled: threading.Event, fault: str = ""
    ) -> Iterator[dict[str, Any]]:
        validate_level(validate_model(self.model, self.models), self.thinking_level)
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
                        **self.configuration(),
                        "instructions": self.instructions,
                        "input": messages,
                        "stream": True,
                        "store": False,
                        "service_tier": "default",
                    }
                ).encode(),
                headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
            )
            response = connection.getresponse()
            if response.status != 200:
                # Never reflect provider bodies, headers or credentials into the browser/logs.
                raise ValueError(
                    f"OpenAI HTTP {response.status}; check model/thinking level in Settings, "
                    "backend key, model access and quota"
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
        if fault == "llm-settings":
            raise ValueError("Provider rejected model/thinking level; change Settings and retry")
        if fault == "llm":
            raise ValueError("Injected provider failure")
        text = "A black hole traps light. We detect one by its effects on nearby matter."
        if len(messages) > 1:
            text += " Earlier question: " + messages[0]["content"][:80]
        if messages[-1]["content"].startswith("Fixture speech: "):
            text = messages[-1]["content"][len("Fixture speech: ") :]
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
            "usage": {
                "input_tokens": 100,
                "output_tokens": 25,
                "output_tokens_details": {"reasoning_tokens": 10},
            },
        }

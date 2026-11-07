"""Conversation acceptance at the loopback HTTP boundary; no paid calls or GPU."""

import json
import subprocess  # nosec B404
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from budget import Budget  # noqa: E402


class ConversationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.addCleanup(self.stop_process)
        self.start_app()

    def start_app(self, pair: str | None = None) -> None:
        # Fixed task-owned executable and loopback server, isolated output and ephemeral port.
        self.process = subprocess.Popen(  # nosec B603
            [
                sys.executable,
                str(ROOT / "scripts/conversation.py"),
                "--port",
                "0",
                "--output",
                self.temporary.name,
                "--test-backend",
                *(["--pair", pair] if pair else []),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        assert self.process.stdout is not None  # nosec B101
        line = self.process.stdout.readline()
        self.assertTrue(line.startswith("LISTEN "), line)
        self.url = line.strip().split(" ")[1]
        self.wait(lambda s: s["state"] == "idle")

    def test_configured_pair_launch_and_invalid_configuration(self) -> None:
        status = self.request("/status")
        self.assertEqual(status["activePair"], "jfk-zira")
        self.ask()
        done = self.wait(lambda s: s["state"] == "idle")
        self.assertEqual(done["run"]["pair"], "jfk-zira")
        self.stop_process()
        self.start_app("hopper-hazel")
        status = self.request("/status")
        self.assertEqual(status["activePair"], "hopper-hazel")
        self.assertIn("Hazel", status["pairs"][1]["name"])
        self.ask()
        self.wait(lambda s: s["state"] == "idle")
        self.ask("How do we detect one?")
        done = self.wait(lambda s: s["state"] == "idle")
        self.assertEqual(done["run"]["pair"], "hopper-hazel")
        self.assertIn("Earlier question", done["run"]["answer"])
        # Fixed executable and invalid configuration; no assets/provider dispatch.
        invalid = subprocess.run(  # nosec B603
            [sys.executable, str(ROOT / "scripts/conversation.py"), "--pair", "unknown"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertNotEqual(invalid.returncode, 0)
        self.assertIn("Unknown pair", invalid.stderr)

    def stop_process(self) -> None:
        self.process.terminate()
        self.process.communicate(timeout=30)

    def request(self, path: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
        body = json.dumps(data).encode() if data is not None else None
        # URL comes only from our loopback process.
        with urllib.request.urlopen(self.url + path, data=body, timeout=30) as response:  # nosec B310
            value: dict[str, Any] = json.load(response)
            return value

    def wait(self, predicate: Any) -> dict[str, Any]:
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            status = self.request("/status")
            if predicate(status):
                return status
            time.sleep(0.02)
        self.fail("Conversation did not reach expected state")

    def ask(self, question: str = "What is a black hole?", fault: str = "") -> dict[str, Any]:
        return self.request(
            "/ask",
            {
                "question": question,
                "fault": fault,
                "session": self.request("/status")["session"],
                "request": uuid.uuid4().hex,
            },
        )

    def test_streamed_answer_and_progressive_speech(self) -> None:
        for question in ("", " \n", "x" * 1201):
            with self.assertRaises(urllib.error.HTTPError):
                self.ask(question)
        run = self.ask(fault="llm-delay")
        with self.assertRaises(urllib.error.HTTPError):
            self.ask("Overlapping question")
        streaming = self.wait(lambda s: s["transcript"] and s["transcript"][-1]["answer"])
        self.assertEqual(streaming["transcript"][-1]["question"], "What is a black hole?")
        done = self.wait(lambda s: s["state"] == "idle")
        self.assertEqual(done["run"]["id"], run["id"])
        self.assertEqual(done["run"]["state"], "complete")
        events = done["run"]["events"]
        media = next(e for e in events if e["event"] == "media-ready")
        end = next(e for e in events if e["event"] == "llm-complete")
        self.assertLess(media["seconds"], end["seconds"])
        spoken = "".join(e["text"] for e in events if e["event"] == "tts-segment")
        self.assertEqual("".join(spoken.split()), "".join(done["transcript"][-1]["answer"].split()))
        self.assertFalse(list(Path(self.temporary.name).rglob("result.json")))

    def test_token_boundaries_long_phrases_and_final_partial(self) -> None:
        for fault in ("long", "unbroken", "truncate", "markup"):
            self.ask(fault=fault)
            done = self.wait(lambda s: s["state"] == "idle")
            self.assertEqual(done["run"]["state"], "complete")
            phrases = [e["text"] for e in done["run"]["events"] if e["event"] == "tts-segment"]
            self.assertTrue(all(len(p) <= 180 for p in phrases))
            answer = done["transcript"][-1]["answer"]
            self.assertEqual("".join("".join(phrases).split()), "".join(answer.split()))
            self.assertEqual(done["transcript"][-1]["truncated"], fault == "truncate")

    def test_followup_context_order_reset_and_stale_session(self) -> None:
        self.ask()
        self.wait(lambda s: s["state"] == "idle")
        self.ask("How do we detect one?")
        done = self.wait(lambda s: s["state"] == "idle")
        self.assertIn("Earlier question: What is a black hole?", done["transcript"][-1]["answer"])
        self.assertEqual(
            [t["question"] for t in done["transcript"]],
            ["What is a black hole?", "How do we detect one?"],
        )
        identity = done["session"]
        fresh = self.request("/reset", {"session": identity})
        self.assertNotEqual(fresh["session"], identity)
        self.assertEqual(fresh["transcript"], [])
        with self.assertRaises(urllib.error.HTTPError):
            self.request("/ask", {"session": identity, "question": "Stale session"})
        self.ask("How do we detect one?")
        done = self.wait(lambda s: s["state"] == "idle")
        self.assertNotIn("Earlier question", done["transcript"][-1]["answer"])

    def test_context_is_bounded_and_truncation_visible(self) -> None:
        for _ in range(8):
            self.ask("What is a black hole? " + "x" * 1100)
            done = self.wait(lambda s: s["state"] == "idle")
        self.assertGreater(done["contextOmitted"], 0)
        self.assertLessEqual(done["run"]["inputBound"], 8192)

    def test_stop_at_async_stages_rejects_stale_results_and_recovers(self) -> None:
        for fault, event in (
            ("llm-connect", "llm-connect"),
            ("llm-delay", "llm-first-text"),
            ("tts-delay", "tts-start"),
            ("buffer-delay", "media-ready"),
            ("dispatch-delay", "dispatch-delay"),
        ):
            run = self.ask(fault=fault)
            self.wait(
                lambda s, expected=event: any(e["event"] == expected for e in s["run"]["events"])
            )
            self.request("/stop", {"run": run["id"]})
            self.request("/stop", {"run": run["id"]})
            stopped = self.wait(lambda s: s["state"] == "idle")
            self.assertEqual(stopped["transcript"][-1]["state"], "stopped")
            self.ask("Replacement question")
            done = self.wait(lambda s: s["state"] == "idle")
            request = next(e for e in done["run"]["events"] if e["event"] == "provider-request")
            self.assertEqual(request["messages"][-2]["role"], "user")
            with self.assertRaises(urllib.error.HTTPError):
                self.request("/telemetry", {"run": run["id"], "currentTime": 90})

    def test_busy_reset_and_provider_speech_media_failure_recovery(self) -> None:
        run = self.ask(fault="tts-delay")
        self.wait(lambda s: any(e["event"] == "tts-start" for e in s["run"]["events"]))
        fresh = self.request("/reset", {"session": run["session"]})
        self.assertEqual(fresh["transcript"], [])
        self.assertNotEqual(fresh["session"], run["session"])
        self.assertIsNone(fresh["run"])
        self.wait(lambda s: s["state"] == "idle")
        for fault in ("llm", "missing-completion", "tts", "media"):
            self.ask(fault=fault)
            done = self.wait(lambda s: s["state"] == "idle")
            self.assertEqual(done["run"]["state"], "failed")
            self.ask("Recovery question")
            done = self.wait(lambda s: s["state"] == "idle")
            self.assertEqual(done["run"]["state"], "complete")

    def test_budget_reconciles_and_survives_stop_reset_and_retry(self) -> None:
        self.ask(fault="llm-connect")
        working = self.request("/status")
        self.assertGreater(working["budget"]["reserved_usd"], 0)
        self.request("/stop", {"run": working["run"]["id"]})
        stopped = self.wait(lambda s: s["state"] == "idle")
        spent = stopped["budget"]["estimated_usd"]
        self.assertGreater(spent, 0)
        self.request("/reset", {"session": stopped["session"]})
        self.assertEqual(self.request("/status")["budget"]["estimated_usd"], spent)
        self.ask()
        done = self.wait(lambda s: s["state"] == "idle")
        self.assertGreater(done["budget"]["estimated_usd"], spent)
        self.assertEqual(done["transcript"][-1]["usage"]["input_tokens"], 100)
        self.assertEqual(done["transcript"][-1]["usage"]["estimated_usd"], 0.000025)

    def test_budget_rejection_and_unusable_accounting_make_no_provider_request(self) -> None:
        ledger = Budget(Path(self.temporary.name) / "budget.sqlite3")
        ledger.reserve("gpt-6-luna", 0, 80_000_000)
        with self.assertRaises(urllib.error.HTTPError):
            self.ask()
        status = self.request("/status")
        self.assertIsNone(status["run"])
        self.assertEqual(status["transcript"], [])
        self.assertEqual(status["budget"]["remaining_usd"], 0)
        (Path(self.temporary.name) / "budget.sqlite3").write_text("unusable")
        with self.assertRaises(urllib.error.HTTPError):
            self.ask()
        status = self.request("/status")
        self.assertFalse(status["budget"]["usable"])
        self.assertTrue(status["configurationError"])

    def test_nonloopback_host_cannot_read_session_or_dispatch(self) -> None:
        for path in ("/status", "/"):
            request = urllib.request.Request(self.url + path, headers={"Host": "attacker.test"})
            with self.assertRaises(urllib.error.HTTPError) as failure:
                urllib.request.urlopen(request, timeout=10)  # nosec B310
            self.assertEqual(failure.exception.code, 403)

    def test_cancellation_without_a_start_reply(self) -> None:
        identity = self.request("/status")["session"]
        request_id = uuid.uuid4().hex
        self.request("/cancel", {"session": identity, "request": request_id})
        with self.assertRaises(urllib.error.HTTPError):
            self.request(
                "/ask",
                {
                    "session": identity,
                    "request": request_id,
                    "question": "Cancelled before dispatch",
                },
            )
        run = self.ask(fault="llm-connect")
        self.request("/cancel", {"session": identity, "request": run["request"]})
        stopped = self.wait(lambda s: s["state"] == "idle")
        self.assertEqual(stopped["run"]["state"], "stopped")


if __name__ == "__main__":
    unittest.main()

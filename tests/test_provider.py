"""Provider wire contract through a deterministic HTTPS transport; no paid requests."""

import json
import sys
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from provider import Provider  # noqa: E402


class ProviderTests(unittest.TestCase):
    def test_supported_settings_reach_responses_request_without_changing_bounds(self) -> None:
        for model, levels in (
            ("gpt-6.1-sol", ("low", "medium", "high", "xhigh", "max")),
            ("gpt-6-luna", ("none", "low", "medium", "high", "xhigh", "max")),
        ):
            for level in levels:
                with self.subTest(model=model, level=level):
                    response = Mock(status=200)
                    response.readline.return_value = (
                        b'data: {"type":"response.completed","response":{"usage":'
                        b'{"input_tokens":100,"output_tokens":25,'
                        b'"output_tokens_details":{"reasoning_tokens":10}}}}\n'
                    )
                    connection = Mock(sock=None)
                    connection.getresponse.return_value = response
                    messages = [{"role": "user", "content": "Hello"}]
                    with (
                        patch.dict(
                            "os.environ",
                            # Secret Keyword: public fake token; review if transport is not mocked.
                            {"OPENAI_API_KEY": "fixture-only"},  # pragma: allowlist secret
                        ),
                        patch("provider.http.client.HTTPSConnection", return_value=connection),
                    ):
                        events = list(
                            Provider(model, False, level).stream(messages, threading.Event())
                        )
                    args, kwargs = connection.request.call_args
                    self.assertEqual(args, ("POST", "/v1/responses"))
                    request = json.loads(kwargs["body"])
                    self.assertEqual(request["model"], model)
                    self.assertEqual(request["reasoning"], {"effort": level})
                    self.assertEqual(request["input"], messages)
                    self.assertEqual(request["max_output_tokens"], 384)
                    self.assertEqual(request["service_tier"], "default")
                    self.assertFalse(request["store"])
                    self.assertEqual(events[-1]["usage"]["output_tokens"], 25)
                    self.assertEqual(
                        events[-1]["usage"]["output_tokens_details"]["reasoning_tokens"], 10
                    )
                    connection.close.assert_called_once()

    def test_invalid_combination_rejects_before_network_dispatch(self) -> None:
        with patch("provider.http.client.HTTPSConnection") as transport:
            for model, level in (("gpt-6.1-sol", "none"), ("gpt-6.1-lunar", "low")):
                with self.assertRaises(ValueError):
                    list(Provider(model, False, level).stream([], threading.Event()))
            transport.assert_not_called()


if __name__ == "__main__":
    unittest.main()

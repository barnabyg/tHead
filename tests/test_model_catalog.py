"""Read-only discovery, settings and price-reservation contract with offline OpenAI responses."""

import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from conversation import Conversation  # noqa: E402
from model_catalog import ModelIndex, StandardRates, discover, model_info, standard_prices  # noqa: E402

PRICING = """Prices per 1M tokens.
Standard
### Standard pricing data
| Model | Short context input | Short context output | Short context 30m write \
| Long context input | Long context output | Long context 30m write |
| --- | --- | --- | --- | --- | --- | --- |
| new-model | $1 | $2 | $1.25 | $2 | $3 | $2.5005 |

| Model | Input | Output | Cached input |
| --- | --- | --- | --- |
| new-simple | $1 | $2 | - |
| malformed | $1 | TBD | - |

Batch
### Batch pricing data
| Model | Input | Output |
| new-model | $0.50 | $0.75 |
| only-batch | $1 | $2 |
"""

PAGE = """Model ID: `new-model`

`reasoning.effort` supports `low`, `medium` (default), and
`high`.

## Model details
- Input modalities: text, image
- Output modalities: text
## Pricing
Prompts with more than 272K input tokens are priced at higher rates.
## Endpoints
| Responses | `v1/responses` | Supported |
## Supported features
- streaming
"""


class ModelCatalogTests(unittest.TestCase):
    def test_standard_text_only_complete_rates_and_upward_rounding(self) -> None:
        self.assertEqual(
            standard_prices(PRICING),
            {
                "new-model": StandardRates((1250, 2000), (2501, 3000)),
                "new-simple": StandardRates((1000, 2000), (1000, 2000)),
            },
        )
        for changed in (
            PRICING.replace("per 1M", "per 100K"),
            PRICING.replace("Standard pricing data", "Fast pricing data"),
        ):
            with self.assertRaises(ValueError):
                standard_prices(changed)
        self.assertNotIn("new-model", standard_prices(PRICING.replace("30m write", "Hourly fee")))

    def test_model_identity_endpoint_and_streaming_are_independently_required(self) -> None:
        for changed in (
            PAGE.replace("ID: `new-model`", "ID: `different-model`"),
            PAGE.replace(" | Supported |", " | Not supported |"),
            PAGE.replace("## Supported features", "## Unsupported features"),
            PAGE.replace("Output modalities: text", "Output modalities: audio"),
        ):
            self.assertIsNone(model_info("new-model", changed, StandardRates((1, 2), (1, 2))).rates)

    def test_exact_index_match_and_default_when_levels_are_unclear(self) -> None:
        index = ModelIndex()
        index.feed(
            "<b>Model ID</b><i>new-model</i><b>Reasoning</b><i>low</i><i>max</i>"
            "<b>Input price</b><i>$2</i>"
        )
        self.assertEqual(index.efforts(), {"new-model": ("low", "max")})
        ambiguous = PAGE.replace("supports", "does not support")
        self.assertEqual(
            model_info("new-model", ambiguous, StandardRates((1, 2), (1, 2))).levels, ("default",)
        )
        self.assertEqual(
            model_info(
                "new-model", ambiguous, StandardRates((1, 2), (1, 2)), index.efforts()["new-model"]
            ).levels,
            ("default", "low", "max"),
        )

    def test_account_intersection_and_host_credentials(self) -> None:
        listing = json.dumps({"data": [{"id": "new-model"}, {"id": "private:id"}]})
        with patch("model_catalog.get_document", side_effect=[listing, PRICING, "", PAGE]) as fetch:
            models = discover("example", threading.Event())
        self.assertEqual(set(models), {"new-model", "private:id"})
        self.assertEqual(models["new-model"].levels, ("low", "medium", "high"))
        self.assertEqual(models["new-model"].default, "medium")
        self.assertEqual(models["new-model"].request_rates(272000), (1250, 2000))
        self.assertEqual(models["new-model"].request_rates(272001), (2501, 3000))
        self.assertIsNone(models["private:id"].rates)
        self.assertEqual(fetch.call_args_list[0].args, ("api.openai.com", "/v1/models", "example"))
        for request in fetch.call_args_list[1:]:
            self.assertEqual(len(request.args), 2)
            self.assertEqual(request.args[0], "developers.openai.com")

    def test_refresh_publishes_rates_and_revokes_removed_models_without_changing_turns(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            app = Conversation(path, path, test_backend=True)
            try:
                listing = '{"data":[{"id":"new-model"}]}'
                with patch("model_catalog.get_document", side_effect=[listing, PRICING, "", PAGE]):
                    app.refresh_catalog()
                app.configure({"session": app.identity, "model": "new-model"})
                selected = app.provider
                self.assertEqual(selected.thinking_level, "medium")
                self.assertEqual(selected.models["new-model"].rates, (2501, 3000))
                with patch("model_catalog.get_document", side_effect=ValueError("sensitive")):
                    self.assertEqual(app.refresh_catalog(), 60)
                self.assertIn("refresh failed", app.status()["configurationError"])
                self.assertNotIn("sensitive", app.catalog_message)
                with self.assertRaises(ValueError):
                    app.configure({"session": app.identity, "model": "new-model"})
                self.assertIn("new-model", selected.models)
                self.assertEqual(app.provider.models, {})
            finally:
                app.close(Mock())


if __name__ == "__main__":
    unittest.main()

"""Discover account-visible models and match them to OpenAI's public Standard text rates."""

from __future__ import annotations

import http.client
import json
import re
import threading
from dataclasses import dataclass
from decimal import ROUND_CEILING, Decimal
from html.parser import HTMLParser

MODEL = "gpt-6-luna"
DEFAULT_EFFORT = "default"
Rates = tuple[int, int]  # Input and output nanodollars per token.


@dataclass(frozen=True)
class StandardRates:
    short: Rates
    maximum: Rates


@dataclass(frozen=True)
class ModelInfo:
    rates: Rates | None = None
    levels: tuple[str, ...] = ()
    default: str = DEFAULT_EFFORT
    error: str = ""
    short_rates: Rates | None = None
    short_limit: int = 0

    def request_rates(self, input_bound: int) -> Rates:
        if self.short_rates and input_bound <= self.short_limit:
            return self.short_rates
        if not self.rates:
            raise ValueError("Standard text pricing unconfirmed")
        return self.rates


# Deterministic offline provider and ledger fixtures. Live discovery supplies its own rates.
FIXTURE_MODELS = {
    "gpt-6.1-sol": ModelInfo((2500, 10000), ("low", "medium", "high", "xhigh", "max"), "medium"),
    MODEL: ModelInfo((125, 500), ("none", "low", "medium", "high", "xhigh", "max"), "none"),
    "fixture-auto": ModelInfo((1000, 2000), (DEFAULT_EFFORT,)),
    "fixture-unpriced": ModelInfo(error="Standard text pricing unconfirmed"),
}


class CatalogError(ValueError):
    """A catalog failure with a message suitable for Settings."""


def get_document(host: str, path: str, key: str = "") -> str:
    connection = http.client.HTTPSConnection(host, timeout=12)
    try:
        headers = {"Authorization": "Bearer " + key} if key else {}
        connection.request("GET", path, headers=headers)
        response = connection.getresponse()
        if response.status != 200:
            raise CatalogError(f"{host} returned HTTP {response.status}")
        body = response.read(2_000_001)
        if len(body) > 2_000_000:
            raise CatalogError("OpenAI catalog document exceeded its size limit")
        return body.decode("utf-8")
    finally:
        connection.close()


def standard_prices(document: str) -> dict[str, StandardRates]:
    # Only the per-million-token Standard block. Adjacent tables can have different headers.
    section = re.search(
        r"Prices per 1M tokens\.\s+Standard\s+### Standard pricing data[ \t\r]*\n",
        document,
    )
    if not section:
        raise CatalogError("OpenAI Standard text pricing table unavailable")
    prices: dict[str, StandardRates] = {}
    columns: list[str] = []
    seen: set[str] = set()
    for line in document[section.end() :].splitlines():
        if not line.strip():
            continue
        if not line.startswith("|"):
            break
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if cells[0] == "Model":
            columns = [c.lower() for c in cells[1:]]
            continue
        if not re.fullmatch(r"[\w.-]+(?: \(<\d+K context length\))?", cells[0]):
            continue
        model = cells[0].split()[0]
        if model in seen:
            prices.pop(model, None)
            continue
        seen.add(model)
        rates = parse_rates(columns, cells[1:])
        if rates is not None:
            prices[model] = rates
    if not prices:
        raise CatalogError("OpenAI Standard text pricing table has no readable rates")
    return prices


def parse_rates(columns: list[str], values: list[str]) -> StandardRates | None:
    if len(columns) != len(values) or len(set(columns)) != len(columns):
        return None
    bands: dict[str, dict[str, int]] = {}
    for column, value in zip(columns, values, strict=True):
        header = re.fullmatch(
            r"(?:(short|long) context )?(input|output|cached input|30m write|12h write)", column
        )
        if not header:
            return None
        band = bands.setdefault(header[1] or "single", {})
        metric = header[2]
        if value == "-" and metric not in {"input", "output"}:
            continue
        if not re.fullmatch(r"\$\d{1,9}(?:\.\d{1,12})?", value):
            return None
        rate = int((Decimal(value[1:]) * 1000).to_integral_value(rounding=ROUND_CEILING))
        if rate <= 0:
            return None
        band[metric] = rate

    if set(bands) not in ({"single"}, {"short", "long"}):
        return None
    rates: dict[str, Rates] = {}
    for name, band in bands.items():
        if "input" not in band or "output" not in band:
            return None
        rates[name] = max(v for k, v in band.items() if k != "output"), band["output"]
    if "single" in rates:
        return StandardRates(rates["single"], rates["single"])
    short, long = rates["short"], rates["long"]
    return StandardRates(short, (max(short[0], long[0]), max(short[1], long[1])))


class ModelIndex(HTMLParser):
    """Read adjacent labelled fields in the featured model cards, independent of styling."""

    def __init__(self) -> None:
        super().__init__()
        self.labels: list[str] = []

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.labels.append(data.strip())

    def efforts(self) -> dict[str, tuple[str, ...]]:
        cards = "\n".join(self.labels)
        return {
            model: tuple(levels.splitlines())
            for model, levels in re.findall(
                r"^Model ID\n([\w.-]+)\nReasoning\n((?:[a-z][a-z0-9_-]*\n)+)Input price$",
                cards,
                re.M,
            )
        }


def model_info(
    model: str, page: str, prices: StandardRates, indexed_levels: tuple[str, ...] = ()
) -> ModelInfo:
    sections = re.split(r"^## (.+?)\s*$", page, flags=re.M)
    fields = dict(zip(sections[1::2], sections[2::2], strict=True))
    details = fields.get("Model details", "")
    if (
        f"Model ID: `{model}`" not in sections[0].splitlines()
        or not all(
            re.search(rf"^- {direction} modalities: (?:\w+, )*text(?:, \w+)*$", details, re.M)
            for direction in ("Input", "Output")
        )
        or not re.search(
            r"^\|\s*Responses\s*\|\s*`v1/responses`\s*\|\s*Supported\s*\|$",
            fields.get("Endpoints", ""),
            re.M,
        )
        or "- streaming" not in fields.get("Supported features", "").splitlines()
    ):
        return ModelInfo(error="Streaming text support for the Responses API is unconfirmed")
    # The public price table names the bands; the model page supplies the cutoff.
    limit = re.search(r"more than ([\d,]+)(K?) input tokens", fields.get("Pricing", ""), re.I)
    short_limit = int(limit[1].replace(",", "")) * (1000 if limit[2] else 1) if limit else 0
    levels = (DEFAULT_EFFORT, *indexed_levels)
    default_level = DEFAULT_EFFORT
    match = re.search(r"^`reasoning\.effort` supports ([^.]+)\.", sections[0], re.M)
    if match and re.fullmatch(r"(?:`[a-z][a-z0-9_-]*`|\s|,|and|\(default\))+", match[1]):
        levels = tuple(re.findall(r"`([a-z][a-z0-9_-]*)`", match[1]))
        default = re.search(r"`([\w-]+)` \(default\)", match[1])
        if model == MODEL and "none" in levels:
            default_level = "none"  # Preserve the app's low-latency default.
        elif default:
            default_level = default[1]
        else:
            levels = (DEFAULT_EFFORT, *levels)
    return ModelInfo(
        prices.maximum, levels, default_level, short_rates=prices.short, short_limit=short_limit
    )


def discover(key: str, stopped: threading.Event) -> dict[str, ModelInfo]:
    listing = json.loads(get_document("api.openai.com", "/v1/models", key))
    if not isinstance(listing, dict) or not isinstance(listing.get("data"), list):
        raise CatalogError("OpenAI returned an unreadable model list")
    ids = {
        row["id"]
        for row in listing["data"]
        if isinstance(row, dict) and isinstance(row.get("id"), str)
    }
    prices = standard_prices(get_document("developers.openai.com", "/api/docs/pricing.md"))
    index = ModelIndex()
    try:
        index.feed(get_document("developers.openai.com", "/api/docs/models"))
        index.close()
    except (OSError, http.client.HTTPException, ValueError):
        pass  # Individual model pages can still supply levels.
    levels = index.efforts()
    models: dict[str, ModelInfo] = {}
    for model in sorted(ids):
        if stopped.is_set():
            break
        if model not in prices:
            models[model] = ModelInfo(error="Standard text pricing unconfirmed")
            continue
        try:
            page = get_document("developers.openai.com", f"/api/docs/models/{model}.md")
            models[model] = model_info(model, page, prices[model], levels.get(model, ()))
        except (OSError, http.client.HTTPException, ValueError):
            models[model] = ModelInfo(error="Model documentation unavailable")
    return models

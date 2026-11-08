"""Conservative, transactional application accounting; stores no prompts or credentials."""

from __future__ import annotations

import os
import sqlite3
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

NANODOLLARS = 1_000_000_000
LIMIT = 40 * NANODOLLARS
# Standard text/cache-write pricing verified 2026-11-08; no cache, batch or regional discounts.
# Source/assumptions and review condition: docs/runtime/conversation-budget.md.
PRICES = {"gpt-6-luna": (125, 500), "gpt-6.1-sol": (2500, 10000)}


class BudgetError(ValueError):
    """Reject paid dispatch when accounting cannot establish available allowance."""


class Budget:
    """SQLite commits reservations before callers dispatch; every retry needs a new one."""

    def __init__(
        self,
        path: Path,
        *,
        initialize: bool = False,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.path = path.resolve()
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        if initialize and not self.path.exists():
            self.path.parent.mkdir(parents=True, exist_ok=True)
            try:
                # Never overwrite existing accounting, including an incomplete initialisation.
                descriptor = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                os.close(descriptor)
            except FileExistsError:
                pass
            else:
                with self.connection(validate=False) as database:
                    database.executescript(
                        "CREATE TABLE metadata (version INTEGER NOT NULL, month TEXT NOT NULL);"
                        "CREATE TABLE requests ("
                        "id TEXT PRIMARY KEY, month TEXT NOT NULL, model TEXT NOT NULL,"
                        "input_bound INTEGER NOT NULL CHECK(input_bound >= 0),"
                        "output_bound INTEGER NOT NULL CHECK(output_bound >= 0),"
                        "input_rate INTEGER NOT NULL CHECK(input_rate > 0),"
                        "output_rate INTEGER NOT NULL CHECK(output_rate > 0),"
                        "charge INTEGER NOT NULL CHECK(charge >= 0),"
                        "pending INTEGER NOT NULL CHECK(pending IN (0,1)),"
                        "estimated INTEGER NOT NULL CHECK(estimated IN (0,1)),"
                        "input_tokens INTEGER, output_tokens INTEGER);"
                    )
                    database.execute("INSERT INTO metadata VALUES (1, ?)", (self.month(),))
        with self.connection():
            pass

    def month(self) -> str:
        instant = self.clock()
        if instant.tzinfo is None:
            raise BudgetError("Accounting clock must include a timezone")
        return instant.astimezone(timezone.utc).strftime("%Y-%m")

    @contextmanager
    def connection(self, *, validate: bool = True) -> Iterator[sqlite3.Connection]:
        if not self.path.is_file():
            raise BudgetError(
                "Budget accounting missing; explicitly initialise first use or restore it"
            )
        database: sqlite3.Connection | None = None
        try:
            uri = "file:" + quote(self.path.as_posix(), safe="/:") + "?mode=rw"
            database = sqlite3.connect(uri, uri=True, timeout=5)
            database.row_factory = sqlite3.Row
            database.execute("PRAGMA synchronous=FULL")
            database.execute("BEGIN IMMEDIATE")
            if validate:
                metadata = database.execute("SELECT version, month FROM metadata").fetchall()
                if len(metadata) != 1 or metadata[0]["version"] != 1:
                    raise BudgetError("Budget accounting has an unsupported schema; restore it")
                if metadata[0]["month"] > self.month():
                    raise BudgetError("Accounting clock moved backwards; correct the UTC clock")
                if database.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                    raise BudgetError("Budget accounting is damaged; restore it")
                # Catch schema/value corruption rather than treating malformed totals as zero.
                for row in database.execute("SELECT * FROM requests"):
                    self.validate_row(row)
            yield database
            database.commit()
        except (sqlite3.Error, OSError, TypeError, KeyError, IndexError) as error:
            if database:
                database.rollback()
            raise BudgetError(
                "Budget accounting unusable; restore it before paid requests"
            ) from error
        finally:
            if database:
                database.close()

    @staticmethod
    def validate_row(row: sqlite3.Row) -> None:
        for key in ("input_bound", "output_bound", "input_rate", "output_rate", "charge"):
            if type(row[key]) is not int or row[key] < 0:
                raise BudgetError("Budget accounting contains invalid amounts; restore it")
        if row["pending"] not in (0, 1) or row["estimated"] not in (0, 1):
            raise BudgetError("Budget accounting contains invalid request states; restore it")
        if not isinstance(row["month"], str) or len(row["month"]) != 7:
            raise BudgetError("Budget accounting contains an invalid month; restore it")

    @staticmethod
    def total(database: sqlite3.Connection, month: str) -> tuple[int, int, int, int]:
        result = database.execute(
            "SELECT COALESCE(SUM(CASE WHEN pending=0 THEN charge ELSE 0 END),0),"
            "COALESCE(SUM(CASE WHEN pending=1 THEN charge ELSE 0 END),0),"
            "COALESCE(SUM(input_tokens),0),COALESCE(SUM(output_tokens),0) "
            "FROM requests WHERE month=? OR pending=1",
            (month,),
        ).fetchone()
        return int(result[0]), int(result[1]), int(result[2]), int(result[3])

    def reserve(self, model: str, input_bound: int, output_bound: int) -> str:
        if model not in PRICES:
            raise BudgetError("Unknown model pricing; select a documented priced model")
        if any(type(value) is not int or value < 0 for value in (input_bound, output_bound)):
            raise BudgetError("Token allowances must be nonnegative integers")
        input_rate, output_rate = PRICES[model]
        allowance = input_bound * input_rate + output_bound * output_rate
        if allowance > LIMIT or allowance <= 0:
            raise BudgetError("Request allowance exceeds the monthly application budget")
        month = self.month()
        with self.connection() as database:
            spent, reserved, _, _ = self.total(database, month)
            if spent + reserved + allowance > LIMIT:
                raise BudgetError("Monthly application budget has insufficient remaining allowance")
            request_id = uuid.uuid4().hex
            database.execute(
                "INSERT INTO requests VALUES (?,?,?,?,?,?,?,?,1,1,NULL,NULL)",
                (
                    request_id,
                    month,
                    model,
                    input_bound,
                    output_bound,
                    input_rate,
                    output_rate,
                    allowance,
                ),
            )
            database.execute("UPDATE metadata SET month=?", (month,))
        return request_id

    def settle(
        self, request_id: str, input_tokens: int | None = None, output_tokens: int | None = None
    ) -> dict[str, Any]:
        with self.connection() as database:
            row = database.execute("SELECT * FROM requests WHERE id=?", (request_id,)).fetchone()
            if row is None:
                raise BudgetError("Unknown budget reservation")
            if row["pending"]:
                valid = all(
                    type(value) is int and value >= 0 for value in (input_tokens, output_tokens)
                )
                if valid:
                    assert input_tokens is not None and output_tokens is not None  # nosec B101
                    charge = input_tokens * row["input_rate"] + output_tokens * row["output_rate"]
                    database.execute(
                        "UPDATE requests SET charge=?,pending=0,estimated=0,"
                        "input_tokens=?,output_tokens=? WHERE id=?",
                        (charge, input_tokens, output_tokens, request_id),
                    )
                else:
                    database.execute("UPDATE requests SET pending=0 WHERE id=?", (request_id,))
                row = database.execute(
                    "SELECT * FROM requests WHERE id=?", (request_id,)
                ).fetchone()
            return {
                "input_tokens": row["input_tokens"],
                "output_tokens": row["output_tokens"],
                "estimated_usd": row["charge"] / NANODOLLARS,
                "estimated": bool(row["estimated"]),
            }

    def snapshot(self) -> dict[str, Any]:
        month = self.month()
        with self.connection() as database:
            spent, reserved, inputs, outputs = self.total(database, month)
        return {
            "month": month,
            "timezone": "UTC",
            "currency": "USD",
            "limit_usd": 40,
            "estimated_usd": spent / NANODOLLARS,
            "reserved_usd": reserved / NANODOLLARS,
            "remaining_usd": max(0, LIMIT - spent - reserved) / NANODOLLARS,
            "input_tokens": inputs,
            "output_tokens": outputs,
            "usable": True,
            "error": "",
        }

# Conversation application budget

The guard limits **this application's estimated standard API requests to USD 40 per UTC
calendar month**. It is not authoritative billing and cannot cap other applications,
account usage, taxes or provider billing adjustments. Speech and avatar generation stay
local. The application sends no tools, audio or image requests to the provider.

## Prices and bounds

Pricing was checked on **2026-11-07** against the official
[GPT-6 Luna model page](https://developers.openai.com/api/docs/models/gpt-6-luna).
The configured model is `gpt-6-luna`. Standard input is USD 0.10 per million tokens;
output is USD 0.50; cached reads are USD 0.01 and cache writes USD 0.125. To avoid
underestimating writes, the guard prices **all input at USD 0.125 per million tokens**,
including conversation context. It never assumes a cached-input discount. Use the fixed
standard OpenAI endpoint; regional/premium/batch service pricing is outside this adapter.
Recheck the source and update `scripts/budget.py` before changing model, endpoint,
service tier or price assumptions. An unknown model is rejected before dispatch.

Every paid attempt must first reserve its bounded full input and maximum output.
The caller must include instructions, message framing and retained conversation context
in its input upper bound, and pass the same output cap to the provider. Each retry needs
a new reservation. No automatic retries are supplied by the ledger. Money is calculated
as integer nanodollars, avoiding floating-point rounding at the acceptance boundary.
For example, 1000 input and 400 output tokens reserve USD 0.000325. A completed
100-input/20-output-token request is estimated at USD 0.0000225.

## Durable accounting

The SQLite ledger contains only random accounting IDs, UTC month, model, price rates,
token bounds, available reported usage, charges and reservation states. It contains no
conversation text or credentials. Keep the same ledger path across application restarts
and configuration changes. Conversation reset and Stop must never delete or reset it.

First use requires an explicit initialisation action. Normal restarts open existing
accounting without initialisation. Missing, corrupt, inaccessible, unsupported or locked
accounting rejects paid dispatch. Initialisation never overwrites an existing ledger,
including an incomplete initialisation. A lost ledger must be restored or externally
reconciled before enabling calls; creating another ledger does not recover lost spend.

SQLite `BEGIN IMMEDIATE` serialises reservations across threads and processes, with a
five-second lock wait. FULL synchronous commits complete before dispatch is allowed.
An outstanding reservation survives crashes and restarts. Completed requests replace
their reservation with reported token cost. Cancelled/failed streams, absent final usage
and malformed/negative usage consume their **entire reserved allowance**. Settlement is
idempotent: delayed repeated callbacks cannot charge or refund the same attempt twice.
Reported usage greater than the bound is charged in full; it is not silently clamped.
That is an upstream-bound violation to investigate, and may leave no available budget.

Requests are attributed to the UTC month when reserved. Unsettled reservations carry
into every subsequent month's available allowance until settled. Once settled, their
charge belongs to the dispatch month; this deliberately over-reserves in-flight work at
rollover. Current-month completed totals reset at 00:00 UTC on the first day of the next
month. Pending reservations from crashed processes remain held conservatively. The
ledger rejects a clock earlier than its most recent reservation month. Historic prices
are stored per reservation, so a price configuration update cannot reprice past work.

## Controlled near-limit fixture

Use only a disposable fixture ledger, never real accounting. This command creates a
fresh isolated accounting fixture and reserves the entire ceiling without a paid call:

```powershell
# Working directory: C:/docs/git/tHead; prerequisite: prepared Python environment.
& ./.venv/Scripts/python.exe -c "import pathlib,sys,tempfile; sys.path.insert(0,'scripts'); from budget import Budget; p=pathlib.Path(tempfile.mkdtemp(prefix='thead-budget-'))/'fixture.sqlite'; b=Budget(p,initialize=True); b.settle(b.reserve('gpt-6-luna',0,80000000)); print(p); print(b.snapshot())"
```

The printed fixture has USD 40 estimated spend and USD 0 remaining. Launch the
conversation application with this path and its deterministic provider/media fixtures;
submit “What is a black hole?”. Expect an understandable budget rejection and no new
provider dispatch or speech. Use a separate freshly initialised fixture for a normal
answer: inspect per-turn input/output usage and estimated cost, then Stop or reset and
confirm the monthly totals remain. The complete preparation/launch command and browser
scenario are documented with the conversation application. The automated budget tests
also cover exact-limit acceptance, rejection, retry allowance, missing usage, reopening,
UTC rollover, unknown model rejection, corrupt/missing accounting and concurrent
connections from multiple Budget instances in threads. Cross-process contention and
changes to the published price table have not been independently exercised.

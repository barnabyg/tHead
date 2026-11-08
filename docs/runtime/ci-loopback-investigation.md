# Windows loopback connection refusals

Observed while publishing PR #51 on 8 November 2026. The push and PR jobs for
`c800ad2` failed in different browser scenarios with `ECONNREFUSED` on `/status`.
The full local canonical command had passed twice. Success means connection
bursts from polling, media, telemetry and controls do not refuse connections
while a live server's accept loop is briefly delayed.

## Hypothesis → measurement → conclusion

1. Fixture process exit: added bounded stderr capture and process diagnostics.
   CI on `a77d5a2` reproduced the failure with `exitCode: null`,
   `signalCode: null` and empty stderr. The observed fixture had not exited.
2. Ordinary concurrent requests: five rounds of 32 concurrent status requests
   to a running local fixture produced zero failures; it remained ready.
   Six repeated browser Stop/Settings checks also passed. Fast local dispatch
   alone does not reproduce the slow-host condition.
3. Pending connections exceed the stdlib backlog: the socket-boundary regression
   queues 16 connections before dispatch, modelling a descheduled accept loop.
   The default backlog of five produced Windows error 10061 (connection refused)
   in 2.042 s while the listener remained open. Setting the explicit pending
   backlog to 128 made the same regression pass. This bounds queued connections;
   it does not change test retries, worker counts or execution timeouts.

The CI diagnostic establishes a live fixture process rather than process exit; the
controlled regression isolates backlog capacity as a cause of the same symptom.
It does not measure the precise number of queued connections in the original CI
failures. CI must pass on the fix before handoff.

From `C:/docs/git/tHead`, with the development dependencies installed:

```powershell
uv run --locked python -W error -m unittest discover -s tests -p test_streaming.py -k connection_burst
```

The full streaming module (three tests) and six parallel repeated Stop/Settings
browser checks passed after the change. Formatting, lint, strict types and static
analysis passed. The canonical CI command remains
`uv run --locked python scripts/verify.py`; existing CI-only fail-fast behaviour
and local failure reporting are unchanged. No new security/warning exceptions.

Manual application testing does not apply to the pending-connection regression;
the existing native avatar playback evidence is separate. The regression binds
an ephemeral loopback port, owns/closes all client sockets and uses no paid API,
GPU or persistent user data.

## Separate Windows fixture teardown failure

After the backlog change, the PR job on `8dcb440` reached a different failure:
`fs.rmSync` raised `EPERM` removing a fixture directory after process termination.
The error arose in teardown, not a behaviour assertion. The old harness killed
the venv launcher and awaited its exit before immediately deleting output;
that does not establish that descendant interpreter handles have closed.

Normal shutdown now asks the diagnostic fixture to stop, lets it cancel/join its
worker, and waits for the process's `close` event. Explicit interrupted-save
scenarios and the hard lifetime cap terminate the owned process tree on Windows.
Deletion checks the resolved path is a task-owned `thead-browser-` directory
directly under the temporary root. It uses Node's bounded filesystem-lock retries
(10 retries, 250 ms linear backoff, at most 13.75 s of backoff) for transient
Windows handle/antivirus locks. See [Node fs.rmSync options](https://nodejs.org/api/fs.html#fsrmsyncpath-options).
This changes cleanup retries only; test/request retries remain unchanged.

Twelve repeated reset, interruption and restart/storage browser checks passed
locally with four workers after this change. CI still provides the authoritative
clean-run result; no test failure is suppressed by the cleanup policy.

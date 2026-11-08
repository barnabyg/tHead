# Chatterbox quality audition (#53)

The [setup gate #52](https://github.com/barnabyg/tHead/issues/52) closed with a
passing reproducibility verdict on 8 November 2026. This stage reuses its exact
Nano/model/Perth/dependency pins and isolated CPU environment. See the
[shared evaluation report](chatterbox-evaluation.md) for maintenance, security,
licensing and offline limitations. There is no production voice or storage change.

## Preparation and listening command

From **`C:/docs/git/tHead` in PowerShell 7**, with Windows 11, Git, uv 0.11.7,
the installed/pinned Zira and Hazel Desktop voices, 20 GiB free disk and 8 GiB
free RAM, one command prepares the environment, creates a new pack and opens it:

```powershell
uv run --locked python scripts/chatterbox_quality.py --pack .runtime/chatterbox-quality-review --generate --prepare --open
```

Choose a new `--pack` directory for each generation; existing evidence is never
overwritten. Preparation needs network access to the pinned public sources;
candidate synthesis itself rejects Python socket access. The delivered reference
excerpts and their [CC BY 4.0 provenance](chatterbox/ATTRIBUTION.md) are committed,
so no private files or pre-existing downloaded corpus are needed. Failed preparation
and attempts retain logs. Two candidate processes run concurrently on CPU, each
with eight intra-op threads and one inter-op thread; they use separate outputs
and no GPU. Model files are read-only shared inputs. Each candidate is bounded
to 31 minutes externally (its worker has a 30-minute limit); the unattended batch
used a three-hour process-tree limit. These are hang limits, not speed targets.
Three consecutive synthesis errors stop scheduling and require reassessment.

To reopen the pack generated for this evaluation, without generating anything:

```powershell
uv run --locked python scripts/chatterbox_quality.py --pack .runtime/chatterbox-quality-pack --open
```

Expected: a local HTML index that starts with **four clips and two reference
excerpts, about 70 seconds of audio**. No Excel or CSV work is needed for this
initial screen. Reply in chat with four lines, A–D: similarity/naturalness (1–5)
and any missing/extra words or ending defects. Clear defects can justify stopping
early; a good screen only justifies further review, not passing the full gate.

The complete experiment matrix, baselines, diagnostics and optional score CSV
remain under a collapsed advanced section. The index contains no scripts, server,
automatic scoring or network media. The initial screen uses the first declared
seed (17), 10-second clean references and the baseline/long-answer passages for
both speakers; it does not select favourable samples after listening.

## Fixed experiment matrix

Two clean reference speakers: **Peter Bobbe (1089)** and **Nikolle Doolin (121)**.
Both are read-audiobook recordings from LibriSpeech test-clean; equipment and
room conditions are unknown. The selected corpus is broadly described as US
English, but its own README warns that automatic accent classification is
unreliable. No human accent classification or verified UK reference is available
in this pack. Hazel's UK baseline does not establish UK cloning retention.

| Condition | Work planned |
| --- | --- |
| Each speaker, exactly 5 seconds | One CLI rejection probe per speaker; Nano requires strictly more than 5 seconds, so no three-repeat synthesis claim |
| Each speaker, 5.1 seconds | Baseline passage × seeds 17, 23, 42 = 6 approximately-five-second comparisons |
| Each speaker, 10 and 20 seconds | Five texts × seeds 17, 23, 42 = 60 clean candidate generations |
| Nominal 15 dB noisy 10-second reference | One baseline-passage generation, seed 17 |
| Two-speaker reference (5 seconds each, concatenated) | One baseline-passage generation, seed 17 |
| Zira and Hazel | Each speaks all five texts = 10 baseline WAVs |

The 5.1-second condition tests the supported side of Nano's strict minimum,
without padding a shorter clip with silence. Its passage/seeds match the longer
reference conditions. The 10/20-second conditions carry the full five-text core
set. The 5.1-second comparison was added explicitly after recognising that an
exact-5-second rejection alone would not cover an approximately-5-second audition;
the original attempts are all retained.

The five texts are the existing baseline passage, names/numbers, a question,
a short reply, and a longer answer with three consecutive sentences. Their
exact text is displayed in the index and manifest. None occurs in either
reference transcript. All planned jobs, attempts, seeds, failures and output
hashes are retained in `manifest.json`; each successful candidate also has its
original `result.json`. The optional preparation audition is separate from this
matrix and retained in `preparation-audition/`.

Settings: temperature 0.8, top-p 0.95, top-k 1000, repetition penalty 1.2,
CFG/exaggeration 0, reference loudness normalisation on, unmodified Perth
watermarking. Each sample starts a new candidate worker with the declared seed;
no cherry-picked re-runs or variants are substituted. Clean input is mono 16 kHz
PCM16; candidate output is mono 24 kHz PCM16, SAPI baseline output mono 16 kHz
PCM16. No resampling to FlashHead's 16 kHz pipeline is evaluated at this stage.

## Human scores and gate

Use 1–5 similarity and naturalness scores: **1 poor/unusable, 3 recognisable or
usable with clear defects, 5 convincing/clear**. For every generated candidate,
compare to its labelled source excerpt and record accent retention, intelligibility,
joins between consecutive sentences, unwanted/repeated words, truncation and
complete endings. Mark any meaning-changing missing/extra word explicitly.
Baseline similarity is **not applicable**: Zira/Hazel compare speech quality only.
Record reviewer identity and observations in the CSV; retain failed samples.

Provisional recommended input is one clean speaker for about **10 seconds**,
because the pinned decoder uses the first 10 seconds, speech-token conditioning
uses up to 15 seconds and speaker embedding sees the full input. This is an
input-preparation recommendation, not an observed quality winner over 20 seconds.
Do not extend a 5-second clip with silence to bypass the minimum. Manually reject
or re-record noisy/music/multi-speaker references; the harness does not detect
those conditions automatically. The contaminated examples test what happens if
that preparation rule is ignored, rather than validating a detector.

The original full-matrix quality gate remains distinct from the **positive initial
human screen** recorded below. No negative outcome is inferred from the numeric
scores against the user's explicit judgement.
To pass provisionally, each clean speaker at a supported recommended reference
length must score at least 3 for similarity and naturalness, with no meaning-changing
missing/extra words across the core text set and repeats. Report every sample,
not just averages or the best seed. Input rejection or successful WAV generation
does not establish similarity, naturalness or accent retention. No embedding score
or automatic transcription substitutes for this listening judgement.

## Results and limits

The completed matrix has **80 records: 68 successful candidate generations,
10 successful native baseline generations, and 2 expected unsupported-length
rejections**. No planned synthesis was skipped or failed. This includes 66 clean
candidate samples and 2 contaminated-reference samples. The optional preparation
audition is separate. The full [raw manifest](chatterbox/quality-manifest.json)
records each result, seed, output hash and configuration. The local pack contains
33.1 MB of audio/evidence, ten reference WAVs and 78 score-sheet rows.

Four fixed screen samples have explicit user scores; 74 generated clips remain
unreviewed. The earlier #52 confirmation concerned only intelligibility of one
identical setup sample. After the user
reported that Excel was unavailable and the 78-row CSV was burdensome, the default
review was narrowed to the four-clip screen above, with chat replies. The original
matrix/evidence is retained; this changes review workload, not the formal quality
gate or the generated audio.

### Recorded initial human screen

The user reported all four utterances complete and explicitly judged the cloning
accuracy **acceptable/comparable to their previous voice-cloning experience**.
They rejected a negative interpretation based on the provisional cutoff: voice
cloning is not expected to be 100% identical. The numeric scores remain unchanged.

| Clip | Speaker / passage | Similarity | Naturalness | User report |
| --- | --- | --- | --- | --- |
| A | Peter Bobbe / baseline | 2 | 4 | Complete |
| B | Peter Bobbe / longer answer | 3 | 4 | Complete |
| C | Nikolle Doolin / baseline | 3 | 4 | Complete |
| D | Nikolle Doolin / longer answer | 3 | 4 | Complete |

[Recorded user verdict](chatterbox/human-verdict.json) preserves the scores and
clarification. This is a **positive initial screen**, not a negative result and
not a claim that all remaining samples or accents were reviewed. The original
issue's cutoff of 3 was provisional; it is not used to override the experienced
user's explicit acceptability judgement. The user explicitly approved this screen as the passing gate for the bounded #54
prototype, replacing the broader provisional listening requirement. #53 is closed.
The remaining 74 generated clips stay unreviewed; the scores are unchanged.

Both contaminated references produced WAVs without automatic rejection. This
establishes that reference hygiene must be a manual preparation step; it does
not establish that their outputs are usable. Exactly 5 seconds failed at CLI
validation; all six 5.1-second paired comparisons generated successfully.

All six 5.1-second cases emitted S3Gen's exact reference mel/token alignment
diagnostic. The pinned source clamps reference speech tokens to the mel length
when input is not a multiple of 40 ms. Original logs are retained and the index
labels the affected cases. The launcher now moves only this exact root-logger
warning, source file and function into conditioning_diagnostics in result.json;
it does not discard the observation or change synthesis. Review this narrow
exception when the source pin changes or short-reference listening reveals a
defect. Other logging remains visible. Prefer 40 ms crop boundaries when preparing
references, and do not interpret this adjustment as an automatic quality verdict.
One separate post-matrix verification reran the affected 1089/5.1-second/seed-17
case: the WAV digest was identical, the diagnostic was present in
[result JSON](chatterbox/alignment-verification.json), and no warning was printed.
It is retained as verification, not substituted for a quality sample. Complete
attempt accounting is 80 matrix records plus one preparation audition plus this
one diagnostic verification (82 operations total).

Hypothesis → change → measurement → conclusion: the pinned Nano may retain two
different voices consistently → fixed texts/seeds and paired reference lengths,
with all attempts retained → 68 candidate WAVs generated, no synthesis errors,
then four human scores plus an explicit acceptable/comparable verdict → positive
initial quality screen, with broader conditions unreviewed. No quality-driven retries, variant
switches or tuning were performed. The 5.1-second extension closes a protocol
coverage gap rather than replacing an unfavourable sample.

Technical inspection verifies all 88 HTML audio resources exist and use complete
mono PCM16 WAVs: 10 reference excerpts plus 78 generated samples. This is not
a substitute for listening to joins, words or endings. Focused CLI tests cover
missing packs, preserving existing evidence and missing pinned assets; strict
types, formatting/lint and static security checks also pass during implementation.
New narrow analysis exceptions cover deterministic test noise (Bandit B311),
bounded fixed local commands/task-owned PID cleanup (B404/B603/B607), and explicitly
opening the escaped, script-free local HTML index (B606). Their review conditions
are documented beside the affected code. No vulnerability advisory is suppressed.

Generation timings include separate worker setup and two-process CPU contention.
They are not warm conversational turns or evidence for the 3–5-second browser
first-speech target. Long answers here use whole-utterance generation; they do not
prove bounded phrase streaming, media continuity, avatar synchronisation or Stop.
Those are #54 integration checks. The four-clip quality gate passes for this
bounded prototype; production adoption also requires integration and security approval.

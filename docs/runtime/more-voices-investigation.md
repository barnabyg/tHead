# More voices: feasibility investigation (#50)

Investigated 8 November 2026. Desk research and read-only native Windows
enumeration only: no voice installation, candidate benchmark or paid experiment.
Implementation remains separately scoped work.

## Inventory and recommendation

`scripts/pairs.py` whitelists two stable references, `zira` and `hazel`.
`scripts/avatars.py` supplies their catalogue labels. `scripts/speech.py` uses
Windows PowerShell/framework System.Speech, verifying the exact Desktop name,
token, English culture and pinned Windows file hashes from `speech-lock.json`
and `hazel-lock.json`. The worker produces mono 16 kHz PCM16 in bounded phrases;
Stop kills synthesis and the next turn reloads the worker.

Native `SpeechSynthesizer.GetInstalledVoices()` enumeration returned exactly
Microsoft Zira Desktop (en-US, `TTS_MS_EN-US_ZIRA_11.0`) and Microsoft Hazel
Desktop (en-GB, `TTS_MS_EN-GB_HAZEL_11.0`), both enabled. The same probe failed
inside the sandbox; successful host enumeration is the relevant result.
The limit is both app configuration and host installation, not a two-voice
engine limit. Microsoft documents [installed-voice enumeration and validation](https://learn.microsoft.com/en-us/dotnet/api/system.speech.synthesis.speechsynthesizer.getinstalledvoices?view=netframework-4.8.1).

First investigate Microsoft David Desktop through the existing adapter. If
Desktop variety/quality is insufficient, audition CPU Piper and Kokoro on
native Windows alongside FlashHead before choosing an adapter. CPU evaluation
avoids adding GPU contention initially. Hosted speech is a separate privacy,
network and budget decision.

## Compatible installed voices first

Microsoft lists US David/Mark/Zira, GB George/Hazel/Susan and English choices
for Australia, Canada, India and Ireland. Its supported route is Narrator
settings → Add legacy voices → Manage voices → Add voices. This list is not
proof that every voice is visible to framework System.Speech; Narrator natural
voices must not be assumed compatible. Enumerate from the same process
architecture, validate enabled name/token/culture and synthesise before
offering a voice. Avoid registry-copying recipes and copying Windows assets
between machines. See [Microsoft voices and installation](https://support.microsoft.com/en-us/accessibility/windows/narrator/appendix-a-supported-languages-and-voices).

These proprietary Windows assets should remain an OS installation prerequisite;
do not redistribute their binaries. Reproducible setup needs the supported
installation route, Windows build, voice token, culture, versions and reviewed
file hashes. Servicing can change hashes and requires deliberate revalidation.
Fresh additional-voice installation and its precise applicable Windows licence
terms remain to be checked; enumeration alone establishes neither.

## Local candidates

| Candidate | Variety/quality evidence | Windows, acquisition and licensing | Resources and integration |
| --- | --- | --- | --- |
| SAPI Desktop | Two installed regional English voices; broader Windows catalogue requires compatibility checks | OS installation; distribute metadata only | CPU; existing PCM/cancellation path; new voice timings and memory unmeasured |
| Piper | Multiple US/GB models; no local audition | Python wheel plus ONNX model/config; upstream release CI tests Windows/Python 3.12; engine GPL-3.0-or-later, each model has its own licence | CPU first, optional CUDA; chunk PCM API; resample actual model rate to 16 kHz; persistent worker and cancellation needed |
| Kokoro | Upstream 82-million-parameter model and US/GB choices; quality claims unverified here | Python package; documented Windows espeak-ng MSI; library Apache-2.0 and upstream describes Apache weights, but audit pinned tensors/dependencies individually | CPU/GPU consumption alongside FlashHead unmeasured; generator example gives 24 kHz; needs continuous resampling and process cancellation |
| eSpeak NG | Compact formant synthesis; upstream describes less natural speech than recording-based engines | Windows/SAPI5 support documented; GPL; exact integration package requires review | Low-resource candidate, no local timings/audition; less promising for naturalness improvement |

Primary sources: [Piper engine/licence](https://github.com/OHF-Voice/piper1-gpl),
[Piper models and licences](https://github.com/OHF-Voice/piper1-gpl/blob/main/docs/VOICES.md),
[Piper streaming API](https://github.com/OHF-Voice/piper1-gpl/blob/main/docs/API_PYTHON.md),
[Piper Windows release CI](https://github.com/OHF-Voice/piper1-gpl/blob/main/.github/workflows/publish.yml),
[Kokoro installation/licence/API](https://github.com/hexgrad/kokoro),
[eSpeak NG](https://github.com/espeak-ng/espeak-ng).

Pin engine/wheel hashes, model/config/speaker revisions, licences, phonemiser
and resampler dependencies. A subprocess does not automatically exempt a
distribution from GPL obligations. Third-party commercial SAPI compatibility
and licence terms were not established in this investigation.

## Measurements versus claims

Historical [Phase 3 evidence](phase-3-assessment.md) reports Zira loading in
0.548 s and synthesising 4.56 s of speech in 0.081 s. Integrated repeats took
0.034–0.068 s for 10.245 s audio. [Phase 6 evidence](phase-6-assessment.md)
records user confirmation of clear speech/approximate synchronisation and
fixture digital onset medians of 1.904 s (Zira) and 1.832 s (Hazel).
Those onset figures include different portraits and the whole pipeline;
historical process/GPU measurements cannot be assigned solely to TTS.

No new candidate quality, startup/synthesis latency, CPU/GPU/memory or Stop
measurements were made. Documentation establishes possibilities, not an audible
or performance winner.

## Hosted alternatives

Azure Speech provides streamed PCM formats. Real-time prebuilt TTS documentation
says input text/output audio are not stored, but text still leaves the computer:
[formats](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/rest-text-to-speech),
[privacy](https://learn.microsoft.com/en-us/azure/ai-foundry/responsible-ai/speech-service/text-to-speech/data-privacy-security),
[pricing](https://azure.microsoft.com/en-us/pricing/details/speech/).
Amazon Polly offers standard/neural/long-form/generative speech; published
standard/neural rates at investigation time were USD 4/16 per million characters
outside free tiers, subject to region/current terms:
[service](https://docs.aws.amazon.com/polly/latest/dg/what-is.html),
[pricing](https://aws.amazon.com/polly/pricing/).
Both need credentials, network-failure/cancellation handling, latency evaluation
and TTS reservation/accounting in addition to the current LLM budget. No spending
experiment was performed.

## Avatar integration

Preserve readable `zira`/`hazel` references. Give additional engines stable,
namespaced references tied to pinned assets and speaker identifiers. Never use
display names or catalogue order as identity. Creation/editing must share one
catalogue showing engine, region, availability and actionable errors; preserve
the avatar identity and chosen voice across saves/restarts.

Activate portrait/voice together between turns, retaining context, budget, Stop
and stale-media isolation. If a voice disappears, retain its reference, name the
missing voice and installation/revalidation steps, and require explicit editing
or selection to recover. Never choose the first available voice silently.

## Investigation record and scoped follow-ups

1. Hypothesis: the app hides installed voices. Inspecting the whitelist and
   enumerating the native host found the same two voices. Configuration alone
   will not supply a third installed voice.
2. Hypothesis: Windows installation can expand choices without changing engines.
   Vendor documentation supports more English voices, but framework visibility
   and reviewed asset pins remain unproven. Scope one David Desktop installation,
   enumeration and synthesis experiment first.
3. Hypothesis: another local engine gives useful variety. Primary APIs/licences
   narrow the shortlist to CPU Piper/Kokoro; no quality winner is established.
   If Desktop choices are insufficient, scope a bounded no-cost audition with
   reviewed, pinned model licences rather than downloading whole collections.

For the audition, use the same English passage for baseline and candidates:
“Hello. This is a local text to speech demonstration. The avatar should speak
this passage clearly, then finish without repeating any words.” Capture cold
readiness and five warm repeats: first PCM, browser audio/video onset, synthesis
real-time factor, peak/RSS memory, CPU and GPU use alongside FlashHead. Listen
on native Windows with synchronised avatar playback for accent, pronunciation,
prosody, joins, missing/repeated words and complete endings. Exercise Stop during
synthesis, switching, replacement, restart and missing-voice recovery. Agree
quality/latency targets before selecting a winner.

Manual application testing does not apply to this desk-research deliverable;
no runnable proof of concept was added. The candidate experiment must supply
one documented PowerShell 7 preparation-and-launch command and prerequisites
before implementation can claim native compatibility.

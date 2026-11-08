"""Build/open the bounded local Chatterbox quality listening pack (#53)."""

from __future__ import annotations

import argparse
import array
import csv
import html
import json
import math
import os
import random
import subprocess  # nosec B404
import sys
import threading
import time
import wave
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from pathlib import Path
from typing import Any

from chatterbox_eval import sha256
from speech import Voice

# B404/B603/B607: fixed shell-free local commands and numeric task-owned PIDs only.
# Revisit these exceptions if executables or commands become externally supplied.

ROOT = Path(__file__).resolve().parents[1]
TEXTS = {
    "baseline": "Hello. This is a local text to speech demonstration. The avatar should speak "
    "this passage clearly, then finish without repeating any words.",
    "names-numbers": "Dr Sarah Thompson and James O'Neill ordered 27 blue folders on "
    "14 November. The meeting starts at nine forty-five.",
    "question": "Could you explain why the sky looks blue, "
    "and tell me whether we should leave now?",
    "short": "Yes, that sounds good.",
    "long-answer": "First, check that the microphone is connected and the room is quiet. "
    "Next, record one clear sentence at a comfortable speaking volume. "
    "Finally, listen to the whole answer, including the joins between phrases, "
    "and make sure the last word is complete.",
}
SPEAKERS = {"1089": "Peter Bobbe", "121": "Nikolle Doolin"}
SEEDS = (17, 23, 42)


def command_log(command: list[str], log: Path, timeout: int) -> int:
    with log.open("wb") as stream:
        with subprocess.Popen(command, cwd=ROOT, stdout=stream, stderr=stream) as process:  # nosec B603
            try:
                return process.wait(timeout=timeout)
            except (subprocess.TimeoutExpired, KeyboardInterrupt):
                if sys.platform == "win32":
                    subprocess.run(  # nosec B603 B607
                        ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                        check=False,
                        timeout=30,
                    )
                else:
                    process.kill()
                raise


def write_wav(path: Path, samples: array.array[int]) -> None:
    with wave.open(str(path), "wb") as wav:
        wav.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
        wav.writeframes(samples.tobytes())


def references(pack: Path) -> list[dict[str, Any]]:
    directory = pack / "references"
    directory.mkdir()
    sources: dict[str, array.array[int]] = {}
    result: list[dict[str, Any]] = []
    for speaker, name in SPEAKERS.items():
        source = ROOT / f"docs/runtime/chatterbox/reference-{speaker}-20s.wav"
        with wave.open(str(source), "rb") as wav:
            sources[speaker] = array.array("h", wav.readframes(wav.getnframes()))
        for seconds in (5, 5.1, 10, 20):
            identifier = f"{speaker}-{seconds}s"
            path = directory / f"{identifier}.wav"
            write_wav(path, sources[speaker][: round(seconds * 16000)])
            result.append(
                {
                    "id": identifier,
                    "speaker": name,
                    "condition": "clean",
                    "seconds": seconds,
                    "path": path.relative_to(pack).as_posix(),
                    "sha256": sha256(path),
                    "supported": seconds > 5,
                }
            )
    clean = sources["1089"][:160000]
    # B311: deterministic test noise, never security identifiers; review if reused for security.
    rng = random.Random(20261108)  # nosec B311
    noise = [rng.gauss(0, 1) for _ in clean]
    speech_rms = math.sqrt(sum(x * x for x in clean) / len(clean))
    noise_rms = math.sqrt(sum(x * x for x in noise) / len(noise))
    gain = speech_rms / (10 ** (15 / 20) * noise_rms)
    noisy = array.array(
        "h",
        [max(-32768, min(32767, round(x + n * gain))) for x, n in zip(clean, noise, strict=True)],
    )
    for identifier, samples, description in (
        ("1089-noisy", noisy, "synthetic Gaussian noise, nominal 15 dB SNR, seed 20261108"),
        (
            "two-speakers",
            sources["1089"][:80000] + sources["121"][:80000],
            "first 5 seconds Peter Bobbe, next 5 seconds Nikolle Doolin",
        ),
    ):
        path = directory / f"{identifier}.wav"
        write_wav(path, samples)
        result.append(
            {
                "id": identifier,
                "speaker": description,
                "condition": "contaminated",
                "seconds": 10,
                "path": path.relative_to(pack).as_posix(),
                "sha256": sha256(path),
                "supported": True,
            }
        )
    return result


def candidate_attempt(pack: Path, state: Path, job: dict[str, Any]) -> dict[str, Any]:
    directory = pack / "samples" / job["id"]
    command = [
        sys.executable,
        str(ROOT / "scripts/chatterbox_eval.py"),
        "--state",
        str(state),
        "--reference",
        str(pack / job["reference"]),
        "--text",
        TEXTS[job["text_id"]],
        "--seed",
        str(job["seed"]),
        "--output",
        str(directory),
    ]
    started = time.perf_counter()
    log = pack / "logs" / f"{job['id']}.log"
    try:
        code = command_log(command, log, 1860)
        result_file = directory / "result.json"
        result = json.loads(result_file.read_text(encoding="utf-8")) if result_file.exists() else {}
        return {
            **job,
            "exit_code": code,
            "status": result.get("status", "failed"),
            "error": result.get("error")
            or log.read_text(encoding="utf-8", errors="replace")[-4000:]
            if code
            else "",
            "wall_seconds": time.perf_counter() - started,
            "audio": (directory / "speech.wav").relative_to(pack).as_posix() if code == 0 else None,
            "log": log.relative_to(pack).as_posix(),
            "result": result,
        }
    except subprocess.TimeoutExpired:
        return {
            **job,
            "status": "failed",
            "error": "process-tree timeout",
            "audio": None,
            "log": log.relative_to(pack).as_posix(),
        }


def render(pack: Path, manifest: dict[str, Any]) -> None:
    rows = [
        "<!doctype html><html lang='en'><meta charset='utf-8'>"
        "<title>Chatterbox quality audition</title><h1>Chatterbox quality audition</h1>"
        "<p>Quality gate UNRESOLVED. Synthetic audio. Compare each reference with new text. "
        "Score similarity and naturalness 1 (poor), 3 (usable with defects), 5 (convincing). "
        "Also record accent, intelligibility, joins, missing/extra words and endings in "
        "<a href='scores.csv'>scores.csv</a>. Baseline similarity is not applicable. "
        "No automatic speaker/noise rejection exists. "
        "<a href='ATTRIBUTION.md'>Reference attribution and transformations</a>.</p>"
        "<h2>References</h2>"
    ]
    for reference in manifest["references"]:
        rows.append(
            f"<p id='ref-{html.escape(reference['id'])}'>{html.escape(reference['id'])}: "
            f"{html.escape(reference['speaker'])} "
            f"({reference['seconds']} s; {html.escape(reference['condition'])})</p>"
            f"<audio controls preload='none' src='{html.escape(reference['path'])}'></audio>"
        )
    for group in ("baseline", "candidate"):
        rows.append(f"<h2>{group.title()} samples</h2>")
        for sample in manifest["samples"]:
            if sample["engine"] != group:
                continue
            rows.append(
                f"<h3>{html.escape(sample['id'])}</h3>"
                f"<p>{html.escape(TEXTS[sample['text_id']])}</p>"
                f"<p>{html.escape(sample['status'])}</p>"
            )
            if sample.get("reference_id"):
                identifier = html.escape(sample["reference_id"])
                rows.append(
                    f"<p><a href='#ref-{identifier}'>Compare reference {identifier}</a></p>"
                )
            diagnostics = sample.get("conditioning_diagnostic") or sample.get("result", {}).get(
                "conditioning_diagnostics"
            )
            if diagnostics:
                rows.append(f"<p>Conditioning diagnostic: {html.escape(str(diagnostics))}</p>")
            if sample.get("audio"):
                rows.append(
                    f"<audio controls preload='none' src='{html.escape(sample['audio'])}'></audio>"
                )
            else:
                rows.append(f"<p>{html.escape(sample.get('error', 'Not generated'))}</p>")
            if sample.get("log"):
                rows.append(f"<p><a href='{html.escape(sample['log'])}'>Attempt log</a></p>")
    rows.append("</html>")
    (pack / "index.html").write_text("\n".join(rows) + "\n", encoding="utf-8")


def generate(pack: Path, state: Path, prepare: bool) -> None:
    pack.mkdir(parents=True, exist_ok=False)
    (pack / "samples").mkdir()
    (pack / "logs").mkdir()
    attribution = (ROOT / "docs/runtime/chatterbox/ATTRIBUTION.md").read_text(encoding="utf-8")
    (pack / "ATTRIBUTION.md").write_text(
        attribution.replace(
            "[evaluation report](../chatterbox-evaluation.md)",
            "[setup resolution](https://github.com/barnabyg/tHead/issues/52)",
        ),
        encoding="utf-8",
    )
    if prepare:
        code = command_log(
            [
                sys.executable,
                str(ROOT / "scripts/chatterbox_eval.py"),
                "--prepare",
                "--state",
                str(state),
                "--reference",
                str(ROOT / "docs/runtime/chatterbox/reference-1089-10s.wav"),
                "--text",
                TEXTS["baseline"],
                "--output",
                str(pack / "preparation-audition"),
            ],
            pack / "logs/preparation.log",
            14400,
        )
        if code:
            raise ValueError("Pinned preparation failed; retained logs/preparation.log")
    refs = references(pack)
    manifest: dict[str, Any] = {
        "gate": "unresolved_human_scores_required",
        "issue": 53,
        "references": refs,
        "texts": TEXTS,
        "seeds": SEEDS,
        "settings": {
            "temperature": 0.8,
            "top_p": 0.95,
            "top_k": 1000,
            "repetition_penalty": 1.2,
            "cfg_weight": 0.0,
            "exaggeration": 0.0,
            "norm_loudness": True,
            "device": "cpu",
            "threads_per_process": 8,
            "watermark": "unmodified upstream PerthImplicitWatermarker",
        },
        "parallel_candidate_processes": 2,
        "timing_limit": "quality generation under CPU contention; not a latency benchmark",
        "samples": [],
    }
    # Persist the plan before native work, retaining evidence on interruption.
    jobs = []
    for ref in refs:
        if not ref["supported"]:
            job = {
                "id": ref["id"] + "-unsupported",
                "engine": "candidate",
                "reference": ref["path"],
                "reference_id": ref["id"],
                "condition": "unsupported_5s",
                "text_id": "short",
                "seed": 17,
            }
            measured = candidate_attempt(pack, state, job)
            measured["status"] = (
                "unsupported_minimum_length"
                if measured.get("exit_code") == 1
                else "unexpected_result"
            )
            measured["error"] = "Nano requires strictly more than 5 seconds; CLI probe retained"
            manifest["samples"].append(measured)
            continue
        texts = (
            TEXTS
            if ref["condition"] == "clean" and ref["seconds"] in (10, 20)
            else {"baseline": TEXTS["baseline"]}
        )
        seeds = SEEDS if ref["condition"] == "clean" else (17,)
        for text_id in texts:
            for seed in seeds:
                jobs.append(
                    {
                        "id": f"{ref['id']}-{text_id}-{seed}",
                        "engine": "candidate",
                        "reference": ref["path"],
                        "reference_id": ref["id"],
                        "condition": ref["condition"],
                        "text_id": text_id,
                        "seed": seed,
                    }
                )
    manifest["planned_candidate_jobs"] = jobs
    manifest_path = pack / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    cancelled = threading.Event()
    for voice_id, lock_name in (("zira", "speech-lock.json"), ("hazel", "hazel-lock.json")):
        voice = Voice(ROOT / lock_name)
        try:
            for text_id, text in TEXTS.items():
                path = pack / "samples" / f"{voice_id}-{text_id}.wav"
                row: dict[str, Any] = {
                    "id": f"{voice_id}-{text_id}",
                    "engine": "baseline",
                    "voice": voice_id,
                    "text_id": text_id,
                }
                try:
                    pcm = voice.speak(text, cancelled)
                    with wave.open(str(path), "wb") as wav:
                        wav.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
                        wav.writeframes(pcm)
                    row.update(
                        status="generated_unreviewed",
                        audio=path.relative_to(pack).as_posix(),
                        sha256=sha256(path),
                        metadata=voice.metadata,
                    )
                except Exception as error:
                    row.update(status="failed", audio=None, error=str(error))
                manifest["samples"].append(row)
        finally:
            voice.close()
    # Two isolated CPU processes fit measured RAM headroom; no shared GPU is used.
    # Stop scheduling after three consecutive synthesis errors; preserve the full plan.
    iterator = iter(jobs)
    failures = 0
    with ThreadPoolExecutor(max_workers=2) as pool:
        active: set[Future[dict[str, Any]]] = set()
        for _ in range(2):
            next_job = next(iterator, None)
            if next_job:
                active.add(pool.submit(candidate_attempt, pack, state, next_job))
        while active:
            done, active = wait(active, return_when=FIRST_COMPLETED)
            for future in done:
                row = future.result()
                manifest["samples"].append(row)
                failures = failures + 1 if row["status"] != "generated_unreviewed" else 0
                print(row["id"], row["status"], flush=True)
                if failures >= 3:
                    manifest["stopped"] = (
                        "Three consecutive synthesis errors: reassess before retrying"
                    )
                if "stopped" not in manifest:
                    next_job = next(iterator, None)
                    if next_job:
                        active.add(pool.submit(candidate_attempt, pack, state, next_job))
                manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    fields = [
        "sample_id",
        "similarity_1_5",
        "naturalness_1_5",
        "meaning_changed_yes_no",
        "accent",
        "intelligibility",
        "joins",
        "unwanted_words",
        "truncation_endings",
        "reviewer",
        "notes",
    ]
    with (pack / "scores.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for sample in manifest["samples"]:
            if sample["status"] == "generated_unreviewed":
                writer.writerow({"sample_id": sample["id"]})
    failed = [
        row
        for row in manifest["samples"]
        if row["status"] not in {"generated_unreviewed", "unsupported_minimum_length"}
    ]
    attempted = {row["id"] for row in manifest["samples"]}
    manifest["not_attempted"] = [job["id"] for job in jobs if job["id"] not in attempted]
    if failed or manifest["not_attempted"]:
        manifest["gate"] = "unresolved_generation_errors"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    render(pack, manifest)
    print(f"Listening pack: {pack / 'index.html'}", flush=True)
    if failed or manifest["not_attempted"]:
        raise ValueError(
            "Listening pack has generation errors; inspect its manifest and attempt logs"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack", type=Path, required=True)
    parser.add_argument("--open", action="store_true")
    parser.add_argument("--generate", action="store_true")
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--state", type=Path, default=ROOT / ".runtime/chatterbox-eval")
    args = parser.parse_args()
    try:
        if args.generate and args.pack.exists():
            raise ValueError("Choose a new pack directory; existing evidence is never overwritten")
        if args.generate:
            state = args.state.resolve()
            if not args.prepare:
                lock = json.loads((ROOT / "chatterbox-lock.json").read_text(encoding="utf-8"))
                for asset in lock["model"]["files"]:
                    path = state / "model" / asset["name"]
                    if not path.is_file():
                        raise ValueError(f"Missing pinned model asset: {path}. Use --prepare.")
                    if sha256(path) != asset["sha256"]:
                        raise ValueError(f"Pinned model asset hash differs: {path}")
            generate(args.pack.resolve(), state, args.prepare)
        index = args.pack.resolve() / "index.html"
        if not index.is_file():
            raise ValueError("Listening pack is missing; run with --generate first")
        if args.open:
            # B606: explicit OS opening of our generated local HTML pack; revisit if content
            # starts including scripts or unsanitised reference/text fields.
            os.startfile(index)  # nosec B606
        return 0
    except (ValueError, OSError) as error:
        print(error, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

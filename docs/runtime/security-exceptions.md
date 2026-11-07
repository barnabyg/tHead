# Runtime-only security exceptions

Reviewed 7 November 2026. These exceptions apply only to the exact Windows GPU
runtime pins checked by `scripts/verify.py`. The development environment is
audited without exceptions. All other advisories remain verification failures.
Re-review on **any Torch/setuptools version change**, and before adding generation,
compilation, packaging, uploads or user-supplied models to this runtime.

| Exact package | Advisory | Technical justification and removal condition |
| --- | --- | --- |
| torch 2.11.0+cu128 | PYSEC-2025-194 / CVE-2025-3000 | Concerns local `torch.jit.script` memory corruption. This test loads pinned public safetensors and does not accept or JIT-compile user code; upstream model/VAE compilation is disabled. PyPI lists a fix in 2.13.0, but the official CUDA 12.8 Windows index inspected for this investigation provides releases through 2.11.0. Remove when a tested compatible official patched wheel is available; re-review before enabling any compilation. |
| setuptools 81.0.0 | PYSEC-2026-3447 / CVE-2026-59890 | Source-distribution MANIFEST Unicode exclusion issue, particularly macOS filesystems. This native Windows test builds/publishes no source distributions. Installation uses uv, hash checking and binary wheels only. Torch 2.11.0 requires setuptools <82; the fixed release is >=83. Remove when Torch's dependency constraint permits a fixed version, or before building source distributions. |
| setuptools 81.0.0 | GHSA-xmj3-9gf7-h52w | Legacy setuptools wheel-to-egg installation can create files outside its destination using crafted namespace metadata. This workflow uses uv's installer and never `Wheel.install_as_egg` or untrusted wheels. Torch's <82 constraint prevents using the fixed 84.1.0 release. Remove when that constraint permits the fix; re-review if the installation mechanism changes. |

The advisory feed currently returns PYSEC-2026-3447 twice for the same package;
there are **three distinct exempted advisories**, not four distinct problems.
The checker strips the official `+cu128` local version suffix for the **advisory
query only**, so the base Torch/Torchvision releases are checked rather than
silently skipped as unknown PyPI versions. Installation still requires the
original CUDA wheel versions and SHA-256 hashes. Python dependency auditing does
not audit bundled CUDA DLLs, the NVIDIA driver, or model weights.

Bandit B404/B603/B607 exceptions are separately documented beside the exact
shell-free subprocess imports/calls. Review them if executable selection or
arguments become externally controlled. They do not suppress any other rule.

The smoke command filters only the exact PyTorch logger notice
`NOTE: Redirects are currently not supported in Windows or MacOs.` from
`torch.distributed.elastic.multiprocessing.redirects`. This refers to unused
multi-process log redirection; it is unrelated to this eager single-GPU profile.
Remove the filter when PyTorch stops issuing it; review before distributed work.
Secret scanning exempts only the 40-hex public commit values under the named
`revision`/`upstream_revision` fields; no secret detector is disabled.

Diffusers 0.42.1 emits its direct-dtype-cast warning for an **empty** list of
modules requiring float32. The smoke command filters the exact empty-list
messages for `CausalVideoAutoencoder` and `WanModelAudioProject` from
`diffusers.models.modeling_utils`. No actual modules require special precision
in that message. Nonempty lists and other models/messages are not filtered.
Remove when Diffusers fixes the empty-list diagnostic; review if either model's
precision requirements change.

The pinned wav2vec2 checkpoint is an ASR checkpoint; FlashHead consumes its encoder
features. The source patch declares only `lm_head.weight`/`lm_head.bias` as expected
unused keys and `masked_spec_embed` as an expected missing key. The CTC head is not
part of the encoder. The randomly initialized mask embedding is used only during
training or with explicit mask indices; this load-only command requires every
network to be in evaluation mode and supplies no such indices. Other missing or
unexpected keys remain reported. Re-review these exact-key exceptions before
training, explicit masking, changing checkpoints or adding audio inference.

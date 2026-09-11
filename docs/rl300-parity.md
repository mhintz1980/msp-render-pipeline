# RL300 local reference proof — T03

This gate checks the prepared scene against the source structure, renders it in
Linux without access to the source directories, and produces a reference candidate
for Mark. It does not grant G0, owner visual acceptance, or cloud authorization.

## Runtime and isolation

Pinned Linux Blender: **5.1.1 / b70da489d7f4**. Archive SHA-256:
`6f9fff89fef154ef7974d1a1c4b916ab4bc1f5618bcb48d5befee1bd0a7c7f2a`.
The [official checksum mirror](https://mirror.blender.org/release/Blender5.1/blender-5.1.1.sha256)
served this checksum when the download host's checksum endpoint returned HTTP 403.
The [official archive](https://download.blender.org/release/Blender5.1/blender-5.1.1-linux-x64.tar.xz)
was downloaded and verified locally. No alternate Blender version is accepted.

The runtime and adjacent archive live in the task-local WSL cache:
`/home/markimus/.cache/studiomark/blender-5.1.1-20260910/`.
Keep both: the verifier checks the archive hash before running and the build inside
Blender. This is a curated-file reproducibility boundary, not an arbitrary-upload
security service. No source folder is renamed, hidden, moved, or mounted in the run.

`bwrap --unshare-all` creates isolated mount/PID/network namespaces. The run sees
read-only Linux `/usr` system libraries, a read-only Blender runtime, declared
read-only inputs, a new writable output directory, ephemeral `/tmp`, and private
`/proc` and `/dev`. It sees no `/mnt/c` or operator home. Inputs include only the
prepared payload, declared environment PNG, manifest, verification/preparation
scripts, and existing render worker. Input hashes are checked inside the namespace.
Linux `timeout` bounds each run; the host timeout includes 30 seconds for teardown.

## Fixed reference and comparisons

The existing studio-dark manifest supplies the camera, lighting, material and
compositing choices. The diagnostic profile fixes 900×625, 48 samples, Cycles CPU,
frame 1, seed 0, OpenImageDenoise, AgX Medium High Contrast, exposure -0.15, gamma 1,
8-bit lossless PNG. This is half the existing 1800×1250 reference resolution, with
half its sample count; it is a review/calibration reference, not a final master.

Before rendering, capture evaluated mesh-instance identities, transforms, counts,
bounds, material assignments, camera, lights, frame and relevant settings. Compare
the original source snapshot to the isolated prepared reopen; compare the repeat
render snapshot to the reference. Names and counts are exact; float tolerance is
absolute 1e-5 in Blender scene units. This is not full mesh or CAD certification.

Two separate good renders must pass the initial plan thresholds: mask IoU ≥0.995,
coverage delta ≤0.005, eroded opaque-interior RGB MAE ≤0.01 and P99 ≤0.05. Images
must decode with exact dimensions, ≥1% visible coverage and nonempty opaque pixels
and eroded interior. Masks must agree with saved beauty alpha to within one byte.
Numerical RGB uses the inverse sRGB transfer on display-referred AgX PNG channels,
not a claim of recovering scene-linear radiance. Heatmaps amplify errors 4×.

The camera-shift and material-change controls must render successfully and fail
image comparison. The missing-environment-texture control must fail before render
with `MISSING_DEPENDENCY`; RL300 itself has no external texture datablocks. The
reference composite uses the existing compositor and checks reloaded saved opaque
product pixels. General compositor hardening remains T05.

## Run and acceptance

Prerequisites: the worktree `.venv` with `requirements-test.txt` installed
(`jsonschema` is required or the preparation tests fail to import). A bare
`python` on PATH is not sufficient.

Run from **PowerShell**, not Git Bash — MSYS rewrites the leading `/home/...` of
`--linux-runtime` into a Windows path and the runtime hash check fails before
any render starts.

From the worktree in PowerShell, choose a **new** evidence directory:

```powershell
./.venv/Scripts/python.exe scripts/verify_scene.py `
  --preparation-report output/verification/rl300-prepared-v1/reviewed-preparation-20260910/preparation-report.json `
  --linux-runtime /home/markimus/.cache/studiomark/blender-5.1.1-20260910/blender-5.1.1-linux-x64 `
  --output-dir output/verification/rl300-prepared-v1/reference-candidate-new `
  --timeout 600
./.venv/Scripts/python.exe -m unittest discover -s tests -v
```

Exit 0 means the machine proof produced an `awaiting_reference_acceptance` report.
An initial blocked report remains if the process fails; any failed numerical gate
returns exit 1. Existing evidence directories are refused. Artifacts are inventoried
with hashes in `scene-parity-report.json`; logs contain local paths and stay local.
The profile records `proposed_pending_owner`, with thresholds unchanged from the
approved plan's proposals. Mark must compare the candidate composite with the
intended existing RL300 studio-dark image and accept the reference hash before the
profile is accepted and T04/cloud parity work advances. No automatic approval path
exists in this verifier.

## Run record

| Evidence directory | Status | Read as |
|---|---|---|
| `parity-20260910-v1` | `awaiting_reference_acceptance`, no failures | **Stale pass — do not cite.** It was produced before the mask/alpha consistency check existed. Its `mask.png` files are blank, identical to v2's; only the gate differed. |
| `parity-20260910-v2` | `blocked` — `MASK_ALPHA_MISMATCH` ×4 | Correct verdict on a real defect. Same `prepared_sha256`/`source_sha256` and pixel-identical artifacts to v1. |
| `parity-20260910-v3` | `awaiting_reference_acceptance`, no failures | Current candidate, produced after the matte fix below. |

The v1/v2 divergence was not a run-to-run instability: the two runs are
pixel-identical. Nothing regressed between them; the check that catches the
blank mask was added after v1 was measured.

**The defect.** Every `mask.png` was solid black while the beauty alpha was
correct. `render_worker.write_matte_pass` assigned
`matte.colorspace_settings.name` *after* writing `matte.pixels`. Assigning a
colorspace to a generated image frees and regenerates its buffer from
`generated_color` (opaque black), so the matte was discarded and a blank mask
saved. Reproduced in isolation on Blender 5.1.1: identical code with the
colorspace set before the pixel write produces a faithful matte. The read side
was never at fault — `img.pixels[3::4]` on a loaded beauty PNG returns correct
alpha.

This survived a full five-mode run because no numerical gate reads `mask.png`.
`image_metrics()` derives silhouette, coverage and interior masks from
`beauty.png`'s alpha channel, so the IoU, coverage-delta and RGB thresholds
were all measured on data the blank mask never touched — including the "≥1%
visible coverage" floor. **`mask.png` currently carries no gate weight of its
own.** Either promote it to the authoritative silhouette input or drop it from
the payload; a third unverified copy of the silhouette is how this happened.
That is an owner/architect decision, not a verifier change.

**The fix.** Colorspace is set before the pixel write; the writer re-reads the
saved matte and raises `MATTE_DEGENERATE` or `MATTE_ALPHA_MISMATCH` rather than
shipping a bad one, and the former blanket `except Exception` that swallowed
matte failures is gone. `tests/test_matte_pass.py` drives the real writer inside
Blender and asserts byte agreement with the beauty alpha; it skips when Blender
is absent (`MSP_BLENDER_BIN` overrides the search).

**v3 measurements.** All four rendered modes: `mask.png` vs `beauty.png` alpha
max byte difference **0**, 49 distinct mask values, coverage matching alpha
exactly. `repeat` is bit-exact against the reference (IoU 1.0, RGB MAE 0.0, P99
0.0). Both image controls fail as designed — `camera_shift` on
`SILHOUETTE_MISMATCH` + `RGB_MISMATCH` (IoU 0.735, coverage delta 0.018) and
`material_change` on `RGB_MISMATCH` alone (IoU 1.0, coverage delta 0.0).
`missing_texture` blocks before render with `MISSING_DEPENDENCY:
world_environment`. `source_to_prepared` reports zero structural differences.

Mark's review artifact is
`parity-20260910-v3/reference/composite.png`. Owner acceptance,
`g0_passed` and `cloud_authorized` all remain false.

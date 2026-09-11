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

Two separate good renders must pass the initial plan thresholds: saved-mask IoU ≥0.995,
coverage delta ≤0.005, eroded opaque-interior RGB MAE ≤0.01 and P99 ≤0.05. Images
must decode with exact dimensions, ≥1% visible coverage and nonempty opaque pixels
and eroded interior. The required `mask.png` is authoritative for visible occupancy,
IoU and coverage delta. Masks must agree with saved beauty alpha to within one byte;
missing, corrupt, incorrectly sized or inconsistent masks block the proof. With
`shadow_catcher: true`, mask coverage includes the product and its ground shadow.
It is not a product-only segmentation. RGB gates use the eroded jointly opaque
beauty-alpha region. `mask_checks` records the per-mode alpha agreement, and the
profile binds reference beauty, mask and composite hashes plus mask semantics.
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
./.venv/Scripts/python.exe scripts/prepare_scene.py `
  --source cad/RL300-SAFE-photoreal.blend `
  --output-dir output/verification/rl300-prepared-v1/grounded-preparation-new `
  --blender-bin 'C:/Program Files/Blender Foundation/Blender 5.1/blender.exe'
./.venv/Scripts/python.exe scripts/verify_scene.py `
  --preparation-report output/verification/rl300-prepared-v1/grounded-preparation-new/preparation-report.json `
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
| `parity-20260910-v3` | `awaiting_reference_acceptance`, no failures | **Superseded.** Matte fix verified, but shadow catcher was off. Not eligible for reference acceptance after the ground-shadow fix. |

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

This originally survived a full five-mode run because no numerical gate read `mask.png`.
The original `image_metrics()` derived silhouette, coverage and interior masks from
`beauty.png`'s alpha channel, so the IoU, coverage-delta and RGB thresholds
were all measured on data the blank mask never touched — including the "≥1%
visible coverage" floor. **September 11 ruling:** retain the required artifact and
promote it to the authoritative coverage input. The production consistency check
also runs on every rendered mode; tests invoke it rather than mirror its formula.

**The fix.** Colorspace is set before the pixel write; the writer re-reads the
saved matte and raises `MATTE_DEGENERATE` or `MATTE_ALPHA_MISMATCH` rather than
shipping a bad one, and the former blanket `except Exception` that swallowed
matte failures is gone. `tests/test_matte_pass.py` drives the real writer inside
Blender and asserts byte agreement with the beauty alpha; it skips when Blender
is absent (`MSP_BLENDER_BIN` overrides the search).

**v3 measurements.** All four rendered modes: `mask.png` vs `beauty.png` alpha
max byte difference **0**, 49 distinct mask values, coverage matching alpha
exactly. `repeat` is pixel-exact against the reference (IoU 1.0, RGB MAE 0.0, P99
0.0). Both image controls fail as designed — `camera_shift` on
`SILHOUETTE_MISMATCH` + `RGB_MISMATCH` (IoU 0.735, coverage delta 0.018) and
`material_change` on `RGB_MISMATCH` alone (IoU 1.0, coverage delta 0.0).
`missing_texture` blocks before render with `MISSING_DEPENDENCY:
world_environment`. `source_to_prepared` reports zero structural differences.

The v3 artifacts remain historical evidence only. Owner acceptance,
`g0_passed` and `cloud_authorized` all remain false.

## Grounded reference rebuild — September 11

The committed studio-dark job enables the ground shadow. Both catcher construction
paths mute diffuse, glossy, transmission and volume-scatter visibility so the
ground does not brighten the product through indirect bounce. Keep failed matte
writes fatal; an incomplete required output cannot be a successful render job.

Fresh preparation: `grounded-preparation-20260911/preparation-report.json`.
Fresh proof: `parity-20260911-grounded-v4/`. Both paths are under
`output/verification/rl300-prepared-v1/`; earlier evidence is preserved.

Preparation handles the scene, not the job manifest. The verifier builds a new
payload from the current studio-dark job and hashes its manifest/environment and
scripts. A shadow-setting change invalidates the reference through these inputs;
it need not alter the source or prepared geometry. No threshold, source geometry,
camera, material, or other job's shadow setting is changed by this continuation.

### v4 run results

Blender 5.1.1 build `b70da489d7f4`, archive `6f9fff89...a7c7f2a`. Source
`e6d6adc1...`, prepared `cbda813b...`. `source_to_prepared` reports zero
structural differences, and every mode reopened with
`source_paths_inaccessible: true`.

| Mode | Verdict | IoU | Coverage delta | Linear RGB MAE | p99 |
|---|---|---|---|---|---|
| `repeat` | pass | 1.0 | 0.0 | 0.0 | 0.0 |
| `camera_shift` | fails as intended | 0.827 | 0.0177 | 0.127 | 0.775 |
| `material_change` | fails as intended | 0.943 | 0.0314 | 0.299 | 0.761 |
| `missing_texture` | blocks before render | - | - | - | - |

`repeat` is pixel-identical to the reference across the full RGBA frame -
max channel delta 0, zero differing pixels, including the penumbra, anti-aliased
edges and fully transparent region that `image_metrics` does not measure. The
saved PNG *files* differ in bytes because Blender stamps Date and RenderTime
metadata into each render; the image data does not. The grounded scene is
therefore as deterministic as the ungrounded one. `missing_texture` blocks with `MISSING_DEPENDENCY:
world_environment`. All four rendered modes pass the mask/alpha binding with
`max_alpha_byte_difference: 0`.

One behavioural change from v3 is worth recording: `material_change` now trips
`SILHOUETTE_MISMATCH` alongside `RGB_MISMATCH`, where under v3 it failed on
`RGB_MISMATCH` alone at IoU 1.0. This is the shadow catcher working as
specified - the mask is product-plus-shadow coverage, so a material change that
alters the cast shadow legitimately alters coverage. It is a stricter negative
control, not a regression.

### Candidate reference hashes, pending Mark's ruling

Under `parity-20260911-grounded-v4/reference/`:

| Artifact | SHA-256 |
|---|---|
| `beauty.png` | `592df350fea5510e12fe1e696bd63efa047c5fe677797ffbad645b8c77c3276d` |
| `mask.png` | `a20686604c4be507a4b4aacfe480b5d5c2f0d7484cd470ee63b1a1c814667d6f` |
| `composite.png` | `9a173cf12d7798dd4ddb0e073755069c0feff770de15f51d46a8d46b99b2d795` |

### Known calibration risk

The mask is product-plus-shadow, so the IoU >=0.995 and coverage-delta <=0.005
gates now sit on a soft boundary: the shadow's edge is illumination- and
denoise-dependent, and coverage is decided at mask byte 8. This is the most
likely threshold to break first on different hardware during T04 cloud parity.
Recorded as a calibration risk to watch, not a reason to change any threshold
now - thresholds stay as proposed until Mark rules.

The report status is `awaiting_reference_acceptance` with no failures, and the
profile remains `proposed_pending_owner`. `g0_passed`, `owner_accepted` and
`cloud_authorized` are all still false. A zero-failure machine proof is not
acceptance; Mark rules on the composite above against the intended studio-dark
image before the profile is frozen and T04 advances.

## Powder coat rebuild - September 11 (v5)

`MSP_YELLOW_PAINT` arrives from the CAD file as Bevel -> Principled -> Output:
constant roughness 0.42, `Coat Weight` 0.0, and nothing on the Normal input
except the bevel. One lobe with a uniform roughness returns an identical,
analytically smooth highlight on every panel, which is what read as computer
generated. `photoreal.powder_coat` in the studio-dark job now drives
`apply_powder_coat()`, which edits the named CAD materials in place rather than
replacing them - the aluminium, stainless, rubber and plastic materials keep
doing their own work.

Three changes, in the order they matter at this framing:

| Change | From | To |
|---|---|---|
| Coat layer | `Coat Weight` 0.0 | 0.85 @ coat roughness 0.05 |
| Roughness | constant 0.42 | noise-driven 0.34-0.52, ~2 cm cells |
| Normal | bevel only | bevel -> peel 1.54 mm + flow 7.69 mm bump |
| Bevel radius | CAD value (job's 0.4 mm never applied) | 1.0 mm |

### What orange peel can and cannot do here

Orange peel is a 1-2 mm feature. Framed full width at 900x625 the machine gets
roughly 4 mm per pixel, and at production 1800x1250 roughly 2 mm - so a
physically correct peel is at or below one pixel and contributes nothing to the
proof image. This was measured, not assumed: at 16.7 mm and strength 1.0 the
same shader produces obvious stucco, and at 1.5 mm it disappears. Rendering it
undenoised at 256 samples does not bring it back either, so the denoiser is not
the cause. A photograph at this framing would not show peel for the same reason.

What carries the finish at this distance is the coat layer and the noise-driven
roughness: roughness varies over many pixels, so it survives both resolution and
denoising, and it mottles the highlight instead of leaving a smooth gradient.
The peel stays in the shader at honest physical values for close crops and
higher-resolution output.

A further gain would come from lighting, not material. Peel reads in real
product photography because there is a structured softbox reflection for it to
distort; a dark studio with broad soft sources gives it nothing crisp to
disturb. That is a separate change with its own review and is not made here.

### v5 run results

Identical runtime, source and prepared hashes to v4 - only the manifest and
`render_worker.py` changed, which is what invalidates the reference through the
verifier's hashed inputs.

| Mode | Verdict | IoU | Coverage delta | Linear RGB MAE | p99 |
|---|---|---|---|---|---|
| `repeat` | pass | 1.0 | 0.0 | 0.0 | 0.0 |
| `camera_shift` | fails as intended | 0.827 | 0.0177 | 0.128 | 0.766 |
| `material_change` | fails as intended | 0.943 | 0.0314 | 0.297 | 0.760 |
| `missing_texture` | blocks before render | - | - | - | - |

`repeat` is pixel-identical across the full RGBA frame (max channel delta 0).
Both negative controls now satisfy the stricter check added with the review
fixes: each fails on its own expected code with no degenerate codes present.

### v5 candidate reference hashes, pending Mark's ruling

Under `parity-20260911-powdercoat-v5/reference/`:

| Artifact | SHA-256 |
|---|---|
| `beauty.png` | `758b74fdea933cb6978470e45cfe2966807b5e0780565213827e28ac90813a05` |
| `mask.png` | `ae7b9c4028b2d9cabc5c101821f71439b7479167487b1aa0b2e267e7d3a278f9` |
| `composite.png` | `cb993ebdb66b64ec820c6afffcbd2cf2076f164a0591d9c298bbfc78af76a708` |

v4 is superseded as a reference candidate but preserved as evidence. Status is
`awaiting_reference_acceptance` with no failures; the profile stays
`proposed_pending_owner`; `g0_passed`, `owner_accepted` and `cloud_authorized`
remain false.

# RL300 local reference proof — T03

> **Current acceptance (2026-09-13): v12 approved by Mark. T03 is complete.**
> The studio-dark v12 proof is the accepted T04 reference for source
> `115fd725…`. See the
> [v12 owner acceptance record](#2026-09-13--v12-owner-acceptance-and-t03-complete).
> The reference-acceptance blocker is closed, and with it the last open clause of
> the T03 contract. G0 and cloud authorization remain separate and have not been
> granted — `g0_passed` and `cloud_authorized` are hardcoded false in verifier
> output by design.

**Superseded acceptance (2026-09-13): v11 approved by Mark**, source `af875e41…`,
voided by the washer widening. See the
[v11 owner acceptance record](#2026-09-13--v11-owner-acceptance), the
> [v11 material record](#2026-09-13--v11-cad-material-corrections-moved-into-the-source)
> and the [v10 flange joint record](#2026-09-13--v10-flange-joint-rebuilt).
> The reference-acceptance blocker is closed. G0 and cloud authorization remain
> separate and have not been granted.
> The reference-acceptance blocker is **open again**. G0 and cloud authorization
> remain separate and have not been granted.

**Superseded acceptance (2026-09-13): v9 approved by Mark**, source `d74b9b19…`,
voided the same day by the flange joint rebuild. See the
[v9 owner acceptance record](#2026-09-13--v9-owner-acceptance).

**Superseded acceptance (2026-09-12): v6 approved by Mark and frozen as the T04
engineering anchor, appearance expected to change.** See the
[owner acceptance record](#2026-09-12--v6-owner-acceptance). That record remains
accurate about what was accepted and when; it is no longer the current state.
Earlier pending-owner statements below describe historical run state.

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
Blender and asserts byte agreement with the beauty alpha; it fails hard when the
pinned Blender is absent rather than skipping - a silent skip would let a broken
matte writer ship (`MSP_BLENDER_BIN` overrides the pinned path).

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

## 2026-09-11 — v6 exposure candidate and missing-beauty failure

Resume from `HANDOFF-2026-09-11.md`: `write_matte_pass()` now raises
`MISSING_BEAUTY` when its required beauty source is absent. Its production call
is guarded by `passes.alpha_mask`; the verifier's missing-texture control raises
before importing the renderer. A real-Blender regression asserts the failure
message, nonzero process exit, and absence of a written mask.

The studio manifest retains AgX / Medium High Contrast and changes exposure from
-0.15 to -1.5. Same-radiance view-transform and exposure comparisons support this
choice; see [the colour study](color-study-2026-09-11.md). Source CAD, paint,
lighting, numerical thresholds, and parity schema are unchanged in this session.

Fresh preparation: `output/verification/rl300-prepared-v1/grounded-preparation-20260911-v6/`.
Fresh proof: `output/verification/rl300-prepared-v1/parity-20260911-exposure-v6/`.
The v5 candidate is superseded; all older evidence is preserved.

- Full virtual-environment suite: 50 tests passed (latest run 50.600 seconds).
- Five-mode isolated proof: `awaiting_reference_acceptance`, no failures.
- Repeat: full decoded RGBA max difference 0; IoU 1.0, RGB MAE/p99 0.
- Camera control: `SILHOUETTE_MISMATCH` and `RGB_MISMATCH`; IoU 0.827126.
- Material control: `RGB_MISMATCH` and `SILHOUETTE_MISMATCH`; IoU 0.942842.
- Missing texture blocks on `MISSING_DEPENDENCY: world_environment` before render.
- All four saved masks agree byte-for-byte with beauty alpha.
- Source-to-prepared structural differences: none. Source hash unchanged.
- Parent recomputed all 42 inventory hashes: no mismatches.
- Independent saved-composite check: opaque RGB max drift 0, 222,085 opaque
  pixels, no opaque product clipped by placement.

| v6 reference artifact | SHA-256 |
|---|---|
| beauty.png | `bfe42875da17c72fd1ab3f0189e8eb3aacc85b985d8d328534e29a6afef40920` |
| mask.png | `ae7b9c4028b2d9cabc5c101821f71439b7479167487b1aa0b2e267e7d3a278f9` |
| composite.png | `a9f57faa505cc1ffea15cd0bb43b38083b3461787b915f2f678585c4202892b7` |

Mark selected studio-dark as the formal parity reference; sunlit remains
additional visual evidence. `owner_accepted`, `g0_passed`, and `cloud_authorized`
remain false. This is a 900x625 / 48-sample proof, not a production-size render.

Fresh read-only review returned `ship` with no implementation blockers. The
reviewer independently ran matte (8/8) and parity (15/15) tests and verified
the saved hashes. Residual debt: `mask_checks` is emitted and validated when
present, but is not required by the report schema; future independent producers
must not rely on its omission being rejected. (Closed 2026-09-15: the schema
now requires `mask_checks` on `awaiting_reference_acceptance` reports.)
Product-plus-shadow coverage is
still sensitive to the denoised shadow edge near mask byte 8. These are recorded
for T04; thresholds and schema were not widened here.

Orchestration: parent `gpt-6-astra / high` confirmed by this task's local
`turn_context` runtime record. Requested delegates: `gpt-5.6-luna / medium`
for read-only command extraction and `gpt-5.6-sol / high` for fresh review.
Both completed; delegate model/effort realization and token usage are not exposed.

API-equivalent cost receipt: unavailable for the whole task. Parent cumulative
usage is observable in the local task log, but includes per-call input above the
calculator's supported 128,000-token boundary; delegate usage and final parent
usage are unavailable. No USD estimate, Astra repricing, or savings claim is made.

## Reference photographs (standing, do not lose again)

```
C:\Projects\work-assets\photograph-studio\rl-200-safe-back-iso-older-whtbkgrd.jpg
C:\Projects\work-assets\Renderings\rl200-safe-iso-back-render-older-std-bkgrd.png
```

A professional photograph of the previous RL200/RL300-SAFE revision - identical
but for some sheet-metal slots - and the same photograph with the dark studio
composited behind it. The second therefore sits in the exact environment this
pipeline targets. These are the closest thing to ground truth available to the
project and are the intended basis for owner visual approval.

Recorded here because the instruction to use them was given in an earlier
session and lost; it survived only because it was repeated. It is now a document,
not a recollection.

Note for anyone comparing against them: they show no resolved orange peel at
full-machine framing either, which is consistent with peel being sub-pixel at
this size. They are not calibrated paint samples, and they are a different
machine revision under different illumination, so their RGB values are evidence,
not a target to fit exactly.

## 2026-09-12 — v6 owner acceptance

Mark's explicit ruling: **"I approve v6. It is no longer blocking"**.
This supersedes the pending owner acceptance in `HANDOFF-2026-09-11-b.md`.

The accepted T04 engineering anchor is the studio-dark v6 proof at
`output/verification/rl300-prepared-v1/parity-20260911-exposure-v6/`, produced by
the implementation committed in `e27d4a9`. **Appearance expected to change**:
this reference may be re-anchored after future material or lighting work.

| Frozen reference artifact | SHA-256 |
|---|---|
| `reference/beauty.png` | `bfe42875da17c72fd1ab3f0189e8eb3aacc85b985d8d328534e29a6afef40920` |
| `reference/mask.png` | `ae7b9c4028b2d9cabc5c101821f71439b7479167487b1aa0b2e267e7d3a278f9` |
| `reference/composite.png` | `a9f57faa505cc1ffea15cd0bb43b38083b3461787b915f2f678585c4202892b7` |

All three artifact hashes were recomputed on 2026-09-12 and match the v6 record.
The saved report still has zero failures. The original report and rendered
artifacts remain unchanged: their `awaiting_reference_acceptance` / false
owner flag records the machine run before this subsequent human ruling.
This section is the authoritative acceptance addendum: `owner_accepted: true`
for the frozen v6 reference; `g0_passed: false` and `cloud_authorized: false`.
No thresholds were changed, and no tests or renders were rerun for this
documentation-only acceptance update.

The v6 reference-acceptance blocker is closed. Next: parameterise the verifier's
job path, then build and verify the white soft studio reference for continued
appearance review against the standing photographs.

## PNG file hashes are not a parity comparator

Recorded 2026-09-12. This is a T04 trap, found while re-verifying the September
12 evidence.

Blender writes the render wall-clock into the beauty PNG's `tEXt` chunks —
`Date`, `RenderTime`, `cycles.ViewLayer.total_time`, `render_time`. Two
bit-identical renders therefore produce two different file SHA-256 values. The
accepted v6 reference and the September 12 default-dark regression are the
proof: both `beauty.png` files are 501,813 bytes with the same IDAT payload
(sha256 `101347d996e3b7ed…`, 500,441 bytes), differing only in `Date`
(`2026/09/11 18:11:31` vs `2026/09/12 05:07:53`) and the three timing strings.
Their recorded file hashes differ; their decoded pixels are identical.

`mask.png` and `composite.png` do not show this, because Pillow writes them and
stamps no timestamp — which is exactly why the drift is easy to miss. Only the
one artifact that comes straight out of Blender is affected.

Consequence for T04: a cross-device comparison keyed on
`scene-parity-profile.json`'s `reference_sha256` would fail on identical
hardware for no reason but the clock. Nothing compares that field today, so this
is a latent trap rather than a live bug. The profile now also records
`reference_pixels_sha256`, `reference_mask_pixels_sha256` and
`reference_composite_pixels_sha256`, each a SHA-256 over the decoded image's
mode, dimensions and pixel bytes (`pixel_digest()` in `scripts/verify_scene.py`).
**Compare those across devices.** The file hashes stay in the profile as a
record of the exact bytes produced, not as a comparator.

Reproduced live on 2026-09-13 by re-running the white proof through the modified
verifier into `parity-20260913-studio-white-pixeldigest/`. Against the September
12 white proof, zero failures and all five modes behaving as before:

| Artifact | File SHA-256 | Decoded-pixel SHA-256 |
|---|---|---|
| `reference/beauty.png` | **differs** (`889b4283…` → `4dade7a3…`) | same (`40c59cf5…`) |
| `reference/mask.png` | same (`c3290899…`) | same (`7abf1ad9…`) |
| `reference/composite.png` | same (`0fa7a804…`) | same (`6dc31890…`) |

Two independent renders of the same scene, and only the Blender-written artifact
changed hash. That is the whole trap in one table.

No threshold, gate flag or report schema changed. The evidence already on disk
is untouched.

## Why `owner_accepted` is `const: false` in the report schema

Recorded 2026-09-12, in answer to a question that will otherwise be re-asked
every time someone notices the mismatch.

Mark accepted v6, and yet every `scene-parity-report.json` says
`owner_accepted: false`, because `docs/scene_parity.schema.json` pins the field
to `const: false`. That is deliberate and it stays.

The report is the verifier's own testimony about a run it performed. Owner
acceptance is an out-of-band human decision the verifier cannot observe, so a
verifier-authored `true` would be a claim it has no standing to make — and a
hand-edited `true` in a machine-generated file is precisely the failure mode the
frozen-hash discipline exists to prevent. Acceptance therefore lives in the
[acceptance addendum](#2026-09-12--v6-owner-acceptance), keyed to the reference
composite SHA-256 that identifies exactly what was accepted.

If T04 later needs a machine-readable acceptance gate, add a separate acceptance
record keyed to that hash. Do not widen this schema: `owner_accepted`,
`g0_passed` and `cloud_authorized` being unforgeable in verifier output is the
property that makes the reports worth trusting.

## 2026-09-13 — v7 CAD geometry re-anchor

Mark authorised editing `cad/RL300-SAFE-photoreal.blend` directly, which
supersedes the standing "material changes go through the manifest" rule for
**geometry only**. The edits are scripted in
[`scripts/edit_rl300_geometry.py`](../scripts/edit_rl300_geometry.py) so they can
be replayed against a re-exported CAD file; a 30 MB binary is not reviewable, a
diff of intent is.

| | |
|---|---|
| Source before | `e6d6adc1a993a7ac67a5bc13e535d72d00eeb6c651782773dbfed59acefca065` |
| Source after | `9c3fe7f79ed3487356db523d69fd362dc4d5b85a52f251ee209ae9498923ce61` |
| Preparation | `output/verification/rl300-prepared-v1/grounded-preparation-20260913-v7/` |
| Dark candidate | `output/verification/rl300-prepared-v1/parity-20260913-v7-dark-anchor/` |
| White proof | `output/verification/rl300-prepared-v1/parity-20260913-v7-studio-white/` |

Both proofs report `awaiting_reference_acceptance` with `failures: []`, all four
render modes passing and `missing_texture` blocking as designed; mask checks pass
with `max_alpha_byte_difference: 0` in every mode. 59 tests pass. `owner_accepted`,
`g0_passed` and `cloud_authorized` remain false in every report.

New dark reference digests, for comparison **by pixel digest, not file hash**:

| Artifact | Pixel SHA-256 |
|---|---|
| beauty | `d07ad027fc287df031a245e97d3811d489fb1fe6302ee630a88d98d15529a792` |
| mask | `ae9953caa72acc0f63200c9fc59db16a8c4b6f1e64c95ab828c0563ca7a4ae37` |
| composite | `51588aafa781cec4828fa86ddbeda5bdbfa7ead1f9a4dc636b0435813d529f26` |

### What changed, and what was measured rather than assumed

**The fittings were replaced, and the bolt holes did not line up.** The two
`V28 inch to 6 inch coupling 8 bolt` meshes gave way to `V2FTG-CAMLOCK-800AL-1/-2`,
instances of the ASME B16.5 Class 150 8 in flange × 8 in male camlock Mark
generated (the generator is preserved at
[`cad/generators/flanged_camlock_800al.py`](../cad/generators/flanged_camlock_800al.py)).

Seating it by inheriting the old coupling's transform placed it perfectly and
still produced a defective assembly: the generator starts its eight holes at
local 0°, while this assembly's bolts sit at **half a bolt pitch** — 22.493° on
one fitting, 18.268° on the other. Every one of the 32 bolts would have passed
through solid flange metal with the holes sitting in the gaps between them. The
script now probes the flange at the bolt circle with ray-crossing parity, reads
where the holes actually are, and solves for the correction instead of carrying
22.5 as a constant that a re-generated part would silently invalidate.

| Fitting | Bolt circle (assembly / drilled) | Bolt phase | Holes inherited | Correction | Residual |
|---|---|---|---|---|---|
| `-1` | 149.222 / 149.225 mm | 22.493° | 0.000° | −22.493° | **−0.118°** |
| `-2` | 149.224 / 149.225 mm | 18.268° | 40.875° | −22.393° | **−0.143°** |

Residuals are at the 0.25° probe resolution, against roughly 1.2° of real angular
slack from a 0.875 in hole on a 0.750 in bolt. Flange-face seating error is
0.000 mm and barrel-centre error is under 5×10⁻⁵ mm on both.

**Washers went to the wide pattern, not to a scale factor.** The 32 flange washers
(16 per fitting, all sharing `Mesh_205`) measured as a dimensionally exact ¾ in
**SAE** flat washer — 37.316 mm OD on a 20.623 mm bore, against a 37.31/20.62 mm
spec. So they were never modelled wrong; the photographs show the wider standard.
They are now ¾ in **USS**: 50.80 mm OD, **bore unchanged**. A uniform scale would
have opened the bore to 28 mm and produced a washer that fits no bolt in the
assembly, so only the outer ring of the annulus was moved.

**The pump is one fused solid, so its internals cannot be deleted.** Mark asked
whether the Vogelsang VX186-520QD pump end could lose its internals, thread
helices and bolt shanks. It cannot, by part surgery: welding the glTF at one
micron takes it from 549,630 vertices and 354,350 boundary edges to 361,271
vertices and **zero** boundary edges — the entire pump is a single closed
manifold. "Volumenkörper" is literally "solid body", and the re-export Mark
produced is still one node of 727,602 triangles, so there is no hierarchy to
grip. Two approaches were measured and rejected:

- *Shell deletion* — after welding there is exactly one shell, so there is nothing
  to delete.
- *Visibility culling* — the never-hit face count did not converge with sampling
  density (59.8% → 32.7% → 16.7% → 11.0% as the ray step went 30 mm → 5.4 mm), so
  any threshold would have deleted geometry that was merely unsampled.

What was applied is the weld plus a 1° limited dissolve: 549,630 → 323,193
vertices (−41.2%), 727,602 → 324,476 stored faces, 646,666 render triangles
(−11.1%), and 33.72 → 30.26 MB. **The real saving is upstream.** 727k triangles is
far finer than this part needs at any framing where it sits inside the enclosure;
a coarser chord deflection on re-export from the Vogelsang CAD would beat
anything achievable here. Aggressive dissolve was measured for reference — 2° gives
27.98 MB, 5° gives 21.10 MB at 419,324 render triangles — but 5° starts to facet
the turned barrels.

**Anisotropy is now set, and scoped.** The axis was left unset in `00f4dc8`
because the couplings' orientation was unknown. It is now measured: a solid of
revolution has a single-valued radius at each axial station, and by that test the
8 in couplings revolve about local Y. `ShaderNodeTangent` in radial mode takes an
**object-space** axis, so `edit_rl300_geometry.py` bakes the replacement's 90°
authoring rotation into its mesh, putting its axis of revolution on local Y.

The four objects on `MSP_ALUMINUM_CAST` do **not** agree on an axis —
`V251415K55_Aluminum Cam and Groove Hose Coupling-1` revolves about local X — so
one shared axis would have streaked that coupling across its barrel instead of
around it. The turned fittings therefore carry a cloned `MSP_ALUMINUM_CAST_TURNED`,
and `anisotropy: 0.4` with `anisotropy_axis: "Y"` applies only to it. This is why
the handoff's warning not to set an axis blind was right: the axis is real, the
material scope is what makes it true.

**Two pieces of authoring scaffolding were removed.** `Bolt_Hole_Cutters` was an
empty mesh (0 vertices) left from generating the fitting. An embedded `Text`
datablock — the 198-line generator — blocked preparation with
`UNSUPPORTED_DEPENDENCY` on `texts:Text`, correctly, since the still-scene policy
rejects embedded scripts and `prepare_scene.py` refuses to drop a dependency
silently. It is removed explicitly here and preserved as a file, so the fitting's
dimensions survive outside the blend.

**The pump is shaded from the manifest, not the blend.** It arrived with eight
auto-named glTF colour materials, 95% of its faces on flat white. It is cast steel
painted black, so a `reassign` rule sends `^PUMP_END_CASTSTEEL-1$` to
`MSP_BLACK_CHASSIS` — all eight slots, reviewable in git rather than baked in.

### A note on where the source actually lives

`cad/RL300-SAFE-photoreal.blend` in this repository is what the pipeline renders
and hashes. Mark authors in `C:/Projects/CAD/RL300-SAFE/RL300-SAFE-photoreal.blend`.
Those had silently diverged: the authoring master carried the pump and the
generated fitting while the repository copy did not. Both now hold the same bytes,
and the pre-edit master is kept at
`RL300-SAFE-photoreal.PRE-GEOMETRY-EDIT-20260913-003118.blend`. **An edit made
only in the authoring master does not reach any render.**

## 2026-09-13 — v8 corrected fitting

The fitting swapped in for v7 was the wrong part. Mark authored a corrected one,
`8in_Flange_x_8in_Camlock`, and parked it at (0, 2, 0); v8 is v7 replayed with
that part in place of `Flanged_Camlock_800AL`. Source
`9c3fe7f7…` → **`17b2abf03a6b5dca5d366c07a480cb066f5ed40756506bec227dfc682dcb3939`**.

| | |
|---|---|
| Preparation | `output/verification/rl300-prepared-v1/grounded-preparation-20260913-v8/` |
| Dark candidate | `parity-20260913-v8-dark-anchor/` — `awaiting_reference_acceptance`, `failures: []` |
| White proof | `parity-20260913-v8-studio-white/` — `awaiting_reference_acceptance`, `failures: []` |
| Tests | 59 pass |

New dark reference pixel digests — compare these, not file hashes:

| Artifact | Pixel SHA-256 |
|---|---|
| beauty | `b24be3c6297da341a395584d22cb742d9786f20cabfd311737e551b682fc37d0` |
| mask | `c16d468c2df1aa9394f5e2cf5c5cd5d6abacf30e0e4a5f530a62177ac0d4765c` |
| composite | `cf990dcc355845f2872d262ba38d90385084712af29ff64d3785b8cc9b065fe2` |

### The part changed, so the script stopped trusting the part

v7 probed the flange at a bolt-circle radius taken from the *generator's*
constant and found the flange plate at a hardcoded depth. Both were true of the
first part and would have quietly measured the wrong circle on the second. They
are now derived:

- **Bolt-circle radius comes from the assembly's own bolts**, measured off the 16
  washers per fitting. The generator's 11.750 in remains only as a cross-check.
  Measured 149.222 and 149.224 mm against the drawing's 149.225 mm.
- **The flange plate is found from the part's own profile** — walk in from the +Y
  face while the section still reaches 97% of maximum radius. On this part that
  band is 31.0 mm, against the 28.575 mm the drawing states for plate thickness;
  the extra is the hub transition, and probing its midpoint is correct either way.

The phase correction reproduced exactly: bolts at 22.493° and 18.268°, holes
inherited at 0.000° and 40.875°, corrections −22.493° and −22.393°, **residuals
−0.118° and −0.143°**. Flange seating 0.000 mm, barrel-centre error 0.000 mm.
Part measures 342.9 mm OD (13.50 in flange) and 136.53 mm long.

### `Smooth by Angle` is geometry nodes, and had to be baked out

The corrected part was shade-auto-smoothed in the GUI. Since Blender 4.1 that is
not a mesh property — it is a **geometry nodes modifier** that links
`geometry_nodes_essentials.blend` out of the Blender installation. Preparation
blocked on all three faces of it at once: `library:geometry_nodes_essentials.blend`
(×2), `modifier:V2FTG-CAMLOCK-800AL-1/Smooth by Angle`, and
`node_tree:Smooth by Angle`. That is the right verdict — a still-scene proof
cannot depend on a node graph evaluated from a file outside the payload.

The shading intent is preserved rather than discarded. `static_smooth_shading()`
writes what auto-smooth computes straight into the mesh: every face smooth, and
every edge whose two faces disagree by more than 30° marked sharp — 2,036 sharp
edges of 5,892. Then `strip_geometry_nodes()` removes the modifier, the node
group and the library entries, and asserts `bpy.data.libraries` is empty
afterwards.

Two traps there, both now handled in the script: `bpy.ops.outliner.orphans_purge`
does **not** clear library entries in background mode, and the two entries point
at the same file, so reading `.filepath` after removing the first raises
`ReferenceError: StructRNA of type Library has been removed`. Snapshot the paths,
then drain the collection by index.

The seven remaining external paths are the known `LibraryWeakReference` entries to
the former `RL300-SAFE-webexport-v1.blend`, which the preparer records and clears
by design.

### Also in v8

The two `V296659A111_…SAE Washer` parts came off `MSP_YELLOW_PAINT` — two
stainless washers were shading as powder coat. Fixed with a manifest `reassign`
rule to `MSP_STAINLESS_FASTENER`, matched on the short form `SAE Washer` because
the part number contains regex metacharacters. Confirmed in the render log:
`Reassigned 2 object(s) matching 'SAE Washer'`.

The host render passes the product fidelity gate at 100% exact machine pixels,
drift 0, frame coverage 41.3%.

## 2026-09-13 — v9 coarse pump replacement

Mark explicitly approved v8 in the continuation session; the earlier statements
that v8 acceptance is pending are superseded. That approval belongs to source
`17b2abf03a6b5dca5d366c07a480cb066f5ed40756506bec227dfc682dcb3939`.
The approved source is preserved at
`C:/Projects/CAD/RL300-SAFE/RL300-SAFE-photoreal.APPROVED-V8-17b2abf0.blend`.
Historical machine reports were not rewritten. Approval does not authorize cloud work.

The owner then requested the next task: replacing the pump with the supplied coarse
GLB. `scripts/edit_rl300_geometry.py` now accepts paired `--pump-glb` and
`--pump-reference` arguments. Replay uses the PRE-V8 source; the approved v8 blend
supplies the actual pump matrix and local/world bounds. Bounds must agree within
0.5 mm before replacement, and a coarse pump that fails to weld watertight cannot
be saved. No visibility culling or washer changes were added.

- GLB SHA-256: `5c12f0342d0f02be915e3213613cf4f095e1302178f0a197b74120ad65735d00`.
- Imported triangles: 276,666; after weld/dissolve: **247,944**, versus 646,666 in v8.
- Welded boundary edges: **0**; nonmanifold edges: **0**.
- Maximum local bounds difference: 0.075608 mm; world difference: 0.075579 mm.
- Independently reopened both scenes: 579 object names and parent relationships
  preserved, all object matrices agree within 1e-6, and all non-pump mesh vertex/
  polygon counts and world bounds are unchanged. `HWR-WSH-F8Z-075-2.007` remains.
- Both master and repository copies now hash to
  `d74b9b19f0d2a1fa7945c92950eb582960ec52de1b61c7ee5103515d47563c94`
  (17,414,369 bytes).
- Geometry evidence: `output/verification/rl300-geometry-v9/report.json` and
  `saved-check.json`; the independent check script is alongside them.
- Preparation: `output/verification/rl300-prepared-v1/grounded-preparation-20260913-v9/`;
  status `prepared`, no blockers.
- Dark proof: `parity-20260913-v9-dark-anchor/`; no failures, all mask checks pass,
  repeat IoU 1.0, coverage delta 0, RGB error 0. Negative controls detected.
- White proof: `parity-20260913-v9-studio-white/`; no failures, all mask checks pass,
  repeat IoU 1.0, coverage delta 0, RGB error 0. Both proofs exit 0 and report
  `awaiting_reference_acceptance`; neither grants owner acceptance automatically.
- Tests: **59 passed**, with Blender available.

At the end of the machine run, v9 was a new source candidate. Mark subsequently
approved it as recorded below; the earlier v8 approval remains historical.

## 2026-09-13 — v9 owner acceptance

Mark's explicit ruling: **"v9 approved"**.

The accepted T04 reference is the studio-dark proof at
`output/verification/rl300-prepared-v1/parity-20260913-v9-dark-anchor/`.
Source SHA-256:
`d74b9b19f0d2a1fa7945c92950eb582960ec52de1b61c7ee5103515d47563c94`.
Prepared SHA-256:
`2f63c29c4cf48f932cb72a4d1bd379e4df91cbdd26602c0e4f1c24d278a90a91`.

| Frozen reference artifact | SHA-256 |
|---|---|
| `reference/beauty.png` | `f50df8bdc2655eab372c6dac554b5bb03936fb42f38e656f2d32158de7ec79c7` |
| `reference/mask.png` | `f07255b1f919f819a85ce7e5bdb0253127334a028fb829df29ca66fe01c1e743` |
| `reference/composite.png` | `a051196f18186caf702d4e5a507ee59408cd6286f34c2e795cf7753bc958c6e2` |

Both live source hashes and all three reference artifact hashes were freshly
checked when recording approval; they match the v9 report, which has no failures.
This is the authoritative human acceptance addendum: `owner_accepted: true` for
v9; `g0_passed: false`, `cloud_authorized: false`. The white proof remains
supporting visual evidence; studio-dark remains the formal reference.

Historical machine reports and schemas remain unchanged, preserving their
pre-approval state. No tests or renders were rerun for this documentation-only
update. V9 reference acceptance is no longer blocking.
## 2026-09-13 — v10 flange joint rebuilt

Mark, looking at the v9 render: "the bolts and washers didn't move when we
replaced the flanged fitting ... Both the bolts and washers are resting INSIDE of
the flange fitting."

He was right, and the gap was in this script's own checks. Every placement gate
was radial or rotational — bolt circle to 3 µm, hole phase to 0.12° — so a
replacement flange of a different thickness passed everything while burying the
hardware it was supposed to clamp. Nothing measured the axial stack.

Four fixes, replayed from the PRE-V8 source:

1. **The raised face is gone.** `HAS_RAISED_FACE` is now `False`. The joint's
   gasket `V2GSK-FLG-A200-125-1` is full-face, reaching r=171.9 mm past the bolt
   circle at r=149.2 mm, so the 1/16 in boss (r=135.4 mm) left the bolts clamping
   a 1.6 mm air gap. Flange plate is now a flat 28.575 mm.
2. **The inboard washers and bolts are seated**, moved 15.872 mm inboard
   onto the flange back face. Seating residual 0.0 mm.
3. **The bolt heads are seated on their washers.** In the source CAD each head
   sank 3.655 mm into its own washer — invisible while the whole
   stack was buried, but not once the joint closed up.
4. **The bolts are 3.25 in**, up from 2.75 in, at Mark's direction. Under-head
   69.855 mm → 82.55 mm. The stretch is applied across the plain
   shank (26.06 → 38.755 mm), so thread pitch is carried, not scaled.
   560 vertices moved on `Mesh_203_LP`, whose 16 users are exactly these bolts.

The fitting is no longer a hand-authored object in the .blend. The script now
**runs** `cad/generators/flanged_camlock_800al.py`, so a dimension change is a
one-line edit plus a replay and nobody has to open Blender.

The measured stack, inboard to outboard (mm along the barrel axis):

| Component | From | To | Thickness |
|---|---|---|---|
| Bolt head | −1524.12 | −1507.70 | 16.42 |
| Washer | −1507.70 | −1501.88 | 5.82 |
| Fitting flange | −1501.883 | −1473.308 | 28.575 (1.125 in) |
| Gasket | −1473.32 | −1470.14 | 3.18 (0.125 in) |
| Mating flange `V2FLG-WO-A200-1` | −1470.14 | −1457.44 | 12.70 (0.500 in) |
| Washer | −1457.44 | −1451.62 | 5.82 |
| Nut | −1451.62 | −1435.35 | 16.27 |
| Bolt tip | | −1425.15 | 10.20 proud of the nut |

Clamped material 44.443 mm = 1.7497 in, matching Mark's 1.125 + 0.125 + 0.500.
Under-head 82.55 mm = 3.250 in. No gaps and no interference anywhere in the stack.

`seat_flange_hardware()` now asserts all of this and exits non-zero if the stack
does not close, so a future flange of the wrong thickness fails loudly instead of
rendering wrong.

- Source SHA-256: `ae41bc567bbaa4849627e37c3f0e2c497784f28f2abc64c7054d0f8c64677b87`.
- Geometry evidence: `output/verification/rl300-geometry-v10/report.json`.
- Preparation: `grounded-preparation-20260913-v10/`; status `prepared`, no blockers.
- Dark proof: `parity-20260913-v10-dark-anchor/`; exit 0, no failures, all mask
  checks pass, repeat coverage delta 0. Negative controls detected.
- White proof: `parity-20260913-v10-studio-white/`; exit 0, no failures, all mask
  checks pass, repeat coverage delta 0.
- Tests: **59 passed**, with Blender available.
- Both master and repository copies hash to the source above.

Both proofs report `awaiting_reference_acceptance`. **v10 is a candidate, not an
anchor**; `owner_accepted: false`, `g0_passed: false`, `cloud_authorized: false`.

## 2026-09-13 — v11 CAD material corrections moved into the source

Mark, on the v10 anchor: "What happened to the latches? I thought we fixed those
to have stainless steel latches and key barrel because it was assigned a plastic
look."

They were never fixed in that render. The four `metal_finish.reassign` rules
added on 2026-09-12 went into `jobs/rl300_04_studio-white.json` **only**.
`00023779` and `reassign` have never appeared in `jobs/rl300_02_studio-dark.json`
in any commit, so the studio-dark anchor — and `rl300_01_no-background` and
`rl300_03_excavation-pit` — rendered the latch on `MSP_PLASTIC` the whole time,
v9 included. The white proof was the only place the fix was ever visible.

These rules correct the CAD *assignment*, not the material: the latch is
stainless whatever the environment. Keeping them in one job manifest out of four
is what let this hide. `correct_cad_materials()` in
`scripts/edit_rl300_geometry.py` now applies them to the source, so every job
inherits them:

| Match | Material | Objects | Slots written |
|---|---|---|---|
| `00023779` | `MSP_STAINLESS` | 6 | 1 |
| `^V2HWR-(BLT|WSH)` | `MSP_STAINLESS_FASTENER` | 27 | 4 |
| `^PUMP_END_CASTSTEEL-1$` | `MSP_BLACK_CHASSIS` | 1 | 8 |
| `SAE Washer` | `MSP_STAINLESS_FASTENER` | 2 | 1 |

It refuses a rule that matches nothing — a silent regression the next time a part
number changes — and, unlike the manifest version, refuses a mesh shared between
a matching and a non-matching object rather than dragging the stranger along.

`metal_finish.reassign` is removed from the white job; `metal_finish.materials`
is added to the dark job so the anchor gets the same turned-aluminium, stainless
and fastener tuning the white reference has.

**The cost of this move:** these corrections are now part of the source hash.
Changing one means a new source version and a new acceptance round, where in the
manifest it was free. That is the trade for having all four jobs correct.

Side effect: the eight auto-named glTF colour materials the pump carried are now
unused and dropped on save, taking the material count from 20 to 12.

- Source SHA-256: `af875e4100e84113393f91bfb4f471d942b07fa7f3f4fb77d1d881b4b1ea7372`.
- Geometry evidence: `output/verification/rl300-geometry-v11/report.json`.
- Preparation: `grounded-preparation-20260913-v11/`; status `prepared`, no blockers.
- Dark proof: `parity-20260913-v11-dark-anchor/`; exit 0, no failures, all mask
  checks pass, repeat coverage delta 0.
- White proof: `parity-20260913-v11-studio-white/`; exit 0, no failures, all mask
  checks pass, repeat coverage delta 0.
- Tests: **59 passed**.
- Both master and repository copies hash to the source above.

Both proofs report `awaiting_reference_acceptance`. **v11 is a candidate, not an
anchor**; `owner_accepted: false`, `g0_passed: false`, `cloud_authorized: false`.

## 2026-09-13 — v11 owner acceptance

Mark's explicit ruling, on the v11 dark and white composites: **"i approve them"**.

The accepted T04 reference is the studio-dark proof at
`output/verification/rl300-prepared-v1/parity-20260913-v11-dark-anchor/`.
Source SHA-256:
`af875e4100e84113393f91bfb4f471d942b07fa7f3f4fb77d1d881b4b1ea7372`.
Prepared SHA-256:
`f43db9a177fdf2bda350d5a9452cca75b99d0e15c97192b3a95d8b3592551633`.

| Frozen reference artifact | SHA-256 |
|---|---|
| `reference/beauty.png` | `cba9cfbfe24f9cb73aabe7eba995d996b1d529b306505eac7d0c460f77c58ddb` |
| `reference/mask.png` | `875ad41b6152c3d9d2a5a7cc102730549dfaa8f74cb579ac9f28b3de49756825` |
| `reference/composite.png` | `abad9d3e26bb1066c08a79689b2b897e380e05cfba27bce74c468a86f8493c59` |

Both live source hashes and all three reference artifact hashes were freshly
checked when recording approval; they match the v11 report, which has no
failures. The approval covers both composites he was shown — the dark anchor and
the white proof — but studio-dark remains the formal reference and the white
proof remains supporting visual evidence.

This is the authoritative human acceptance addendum: `owner_accepted: true` for
v11; `g0_passed: false`, `cloud_authorized: false`. Neither follows from
reference acceptance. Historical machine reports and schemas remain unchanged,
preserving their pre-approval state. No tests or renders were rerun for this
documentation-only update. V11 reference acceptance is no longer blocking.

The v6, v8 and v9 approvals are historical. Any further edit to
`cad/RL300-SAFE-photoreal.blend` — including a change to the material
corrections, which now live in the source — voids this one the moment it lands.

## 2026-09-13 — v12 USS washers everywhere

Mark, shown the enclosure joint against the photographs: **"we definitely need the
larger washer (USS style)."**

This closes the question `HANDOFF-2026-09-13-b.md` raised and nobody had put to
him. `F8Z-075` appears at two joints. v7 widened `Mesh_205` — the 32 flange
washers — and left `Mesh_226` alone, so the machine wore two different washers
for the same part number: 50.80 mm at the flanges and 37.31 mm on the enclosure
side panels.

| Mesh | Joint | Instances | Before OD | After OD |
|---|---|---|---|---|
| `Mesh_205` | flange washers, 16 per fitting | 32 | 37.316 | 50.800 |
| `Mesh_226` | enclosure side panel brackets, 4 bolts per side | 16 | 37.314 | 50.800 |

Both are plain annuli, so the same outer-ring-only move applies: the rim goes out
to the USS OD and the bore stays at the bolt size (20.623 mm). `widen_washers()`
now iterates `WASHER_MESHES` instead of naming one mesh, and derives the plate's
thin axis rather than assuming local X, so a washer authored on a different axis
fails loudly instead of being scaled in the wrong plane.

At this joint the washer was standing 2.2 mm proud of a 33.00 mm nut; it now
stands 8.9 mm proud. That is the visible change Mark asked for.

Also in this version, carried from the previous commit: the
`outboard_washer_gap_to_mating_flange` gate now finds the mating flange by
proximity rather than by name, so it verifies **both** fittings —
`V2FLG-WO-A200-1` and `V2FLG-WO-A200-1.001`, both at 0.000 mm — where it
previously reported `null` on the second.

- Source SHA-256: `115fd725a9659901e035f0b6cc474449bb7d740c816d0107aa6dd7520bf3bb6a`.
- Prepared SHA-256: `3da94b93eefb2aa41da01505d2dd6ef2b415f6daf484f3381d3acf943073e51e`.
- Geometry evidence: `output/verification/rl300-geometry-v12/report.json`.
- Preparation: `grounded-preparation-20260913-v12/`; status `prepared`, no blockers.
- Dark proof: `parity-20260913-v12-dark-anchor/`; exit 0, no failures, all mask
  checks pass, repeat coverage delta 0.
- White proof: `parity-20260913-v12-studio-white/`; exit 0, no failures, all mask
  checks pass, repeat coverage delta 0.
- Tests: **59 passed**.
- Flange seating residuals 0.000 mm on both fittings; both master and repository
  copies hash to the source above.

Both proofs report `awaiting_reference_acceptance`. **v12 is a candidate, not an
anchor**; `owner_accepted: false`, `g0_passed: false`, `cloud_authorized: false`.

## 2026-09-13 — v12 owner acceptance, and T03 complete

Mark's explicit ruling on the v12 composites: **"approved"**.

The accepted T04 reference is the studio-dark proof at
`output/verification/rl300-prepared-v1/parity-20260913-v12-dark-anchor/`.
Source SHA-256:
`115fd725a9659901e035f0b6cc474449bb7d740c816d0107aa6dd7520bf3bb6a`.
Prepared SHA-256:
`3da94b93eefb2aa41da01505d2dd6ef2b415f6daf484f3381d3acf943073e51e`.

| Frozen reference artifact | SHA-256 |
|---|---|
| `reference/beauty.png` | `af37fbf90aaeb169873bf38d84f98276604959dcdc5ab11ae177b93db23714b5` |
| `reference/mask.png` | `d5d6cc457d9b9df135fa3a44ce1600dc1b797317717c0e02b884cfa574d2b7a7` |
| `reference/composite.png` | `1dd895250989d1d0342f18a75e078ed4fff27d8a743e79b5db17a7905dd4555d` |

Both live source hashes and all three reference artifact hashes were freshly
checked when recording approval; they match the v12 report, which has no
failures. `owner_accepted: true` for v12; `g0_passed: false`,
`cloud_authorized: false`. Every earlier approval — v6, v9, v11 — is historical.

**This closes T03.** [`docs/scene-preparation.md`](scene-preparation.md) set five
clauses for it: reopen the payload in Linux with source directories inaccessible,
capture evaluated structure, render the fixed reference and negative controls,
freeze measured tolerances, and obtain Mark's reference acceptance. All five are
satisfied by the v12 evidence. The reference that leaves T03 is the studio-dark
composite above; the white proof remains supporting visual evidence.

Compare anything downstream against this reference **by pixel digest, never file
hash** — `reference_pixels_sha256`, `reference_mask_pixels_sha256` and
`reference_composite_pixels_sha256` in `scene-parity-profile.json`. Blender
stamps the render wall-clock into `beauty.png`, so the file hash drifts between
two bit-identical renders. See
[PNG file hashes are not a parity comparator](#png-file-hashes-are-not-a-parity-comparator).

Any further edit that reaches `cad/RL300-SAFE-photoreal.blend` voids this
acceptance the moment it lands — including a change to the CAD material
corrections or the washer meshes, which now live in the source.

## 2026-09-16 — excavation-pit scale fix (pending owner pick), T04 merged

Mark rejected the 09-14 excavation-pit composite on scale: *"the pump is only a
few feet long"* against the pit. The DD6 reference on the same plate
(`C:/Projects/work-assets/Renderings/DD6-Rendering-jobsite.png`) fills **85.2%
of frame width** (yellow-body profile, x[130,1185] of 1239); the rejected
composite's mask fills **53.0%** (x[202,678] of 900).

Scene measurement first (`output/scratch_measure_bbox.py`,
`scratch_measure_extremes.py`, headless Blender, replicating the worker's
all-MESH world-bounds rule): the visible product is **63.0 × 129.6 × 81.0 in**.
The 129.6-in length is real product — `V2FTG-CAMLOCK-800AL` suction fittings
set the front at −63.4 in, `G2RL200-SAF-2027` sets the rear at +66.3 in; the
`hide_misplaced_isolators` rule hides only six z-min mounts (−2 in of height).
Mark's 111-in figure matches the skid rails exactly (`V2RL300-FTS-2003/2004`:
111.0 in); the shipped machine is longer than its skid. No worker defect; the
camera is the right lever. `render_worker` computes bounds before hiding
isolators — radius 1.6463 m either way, immaterial here.

The handoff's 8.5→5.3 start (÷1.60) was rendered and measured: width 84.8%
(on datum) but height 96.0% **clipping the frame bottom** — the RL300 is ~1.35×
taller for its length than the DD6 (whose yellow band fills only 54.4% of
height, ground contact ~79%), so a literal 85.2%-width placement cannot fit the
frame at any vertical seating. This is the art-direction-vs-literal-backdrop
question made concrete: this plate was shot for a smaller machine.

Two unclipped candidates were rendered (900×625 parity profile, preparation
`grounded-preparation-20260913-v12`, status `awaiting_reference_acceptance`,
no failures):

| Candidate | `distance_multiplier` | `target_offset_z` | `product_offset_pct` | width | height | composite ground line |
|---|---|---|---|---|---|---|
| A — `parity-20260916-v12-excavation-pit-scaleA3` | 5.6 | 0.85 | [0.02, 0.0] | 80.3% | 92.3% | 95.8% |
| B — `parity-20260916-v12-excavation-pit-scaleB` | 5.9 | 0.85 | [0.02, 0.02] | 76.3% | 87.4% | 95.0% |

`jobs/rl300_03_excavation-pit.json` is left at candidate A's values (matching
the scaleA3 evidence). Intermediate runs `…-scale` and `…-scaleA`/`…-scaleA2`
record the clipping iterations (dm 5.3 and 5.5 at aim 0.92 clip row 624; aim
0.78 trades it for a row-1 top graze). **Awaiting Mark's A/B ruling**; neither
is a recorded acceptance. The composites predate the T05 compositor gates; the
parity path seats via product alpha, so the T05 mask fix does not alter them.

Also this session: the ten pending scene-prep fixes were committed (`57c257e`,
content identical to the T04 lane baseline `1d493d5`), the 09-15 renewal and
handoff recorded (`717953d`), and T04 merged via `lane/t04-result-contract`
(`f5b468a` → merge `18d4b2c`); merged suite 92 OK. A DeepSeek cross-vendor
review returned fix-first with one verified blocker (`cloud_parity.py` direct
invocation) plus honesty fixes in `_normalise_compute` — fixes applied same
session (see `docs/remote-job-contract.md` and the test suite for the pinned
behaviour).

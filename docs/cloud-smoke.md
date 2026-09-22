# v12 cloud parity proof

## Authorization and scope

On 2026-09-13 (America/New_York), Mark authorized cloud work in this task:
“you re approved for clioud wokr” and “you are approved to test on the cloud as well”.
This records human authorization separately from immutable T03 verifier reports.
The accepted composite is
`1dd895250989d1d0342f18a75e078ed4fff27d8a743e79b5db17a7905dd4555d`.
No schema or frozen acceptance evidence is changed.

The immediate scope is a bounded experimental cloud parity proof of the frozen
v12 dark anchor, plus a required-GPU failure control. This does not complete the
approved plan's production T04 result contract, T05 compositor hardening, or T06
shared CLI transport. The handoff uses “T04” more broadly for cloud parity.

### Renewed authorization, 2026-09-15

That bounded scope was spent by run `cloud-v12-l4-20260914-05`. On 2026-09-15
Mark reopened it, verbatim: “msp-rendering-pipeline: continue moving forwards.
i approve the current renderings and cloud work and modal work.”

What this does and does not authorize:

- **Does** authorize resuming the approved plan's production units — T04 result
  contract, T05 compositor hardening, T06 shared CLI transport — and the cloud
  and Modal work they lead to. T04/T05/T06 are local and cost nothing to run.
- **Does not** supply a spend ceiling. T07's acceptance is explicitly
  “price/limit approval before live call”, and no figure was named here. Bring
  Mark a named per-run cost and a run count before the first T07 dispatch, and
  record his answer here the way the 09-13 quotes are recorded.
- `cloud_authorized` stays hardcoded false in verifier output by design. A human
  authorization in this file is not a machine gate, and a passing cloud run does
  not flip it.

## Execution bounds

- One ephemeral Modal app, one L4, four physical CPU cores, 16 GiB RAM.
- Function timeout 1,200 seconds; Blender timeout 1,080 seconds; negative control 60 seconds.
- One container maximum; no application retries; no deployment or persistent volume.
- Modal may retry infrastructure crashes independently of application retry settings.
- Base allocation estimate at full function timeout: about USD 0.372;
  build/startup and provider infrastructure retries are additional. This is an
  estimate, not a billing cap or invoice.
- Rates checked at [Modal pricing](https://modal.com/pricing): L4 $0.000222/s,
  CPU $0.0000131/core/s, memory $0.00000222/GiB/s.

## Method

`scripts/cloud_parity.py` verifies every declared frozen payload hash and all
three reference pixel digests before any cloud call. It carries runtime version,
build and archive SHA-256 from the accepted report and frozen verifier. Image
construction fails on an archive mismatch; there is no version fallback.

Only the frozen payload and dedicated harness are explicitly mounted. The
Blender harness reuses the frozen dependency audit and deterministic render
settings, changing the device to an explicitly enabled NVIDIA GPU. The original
probe's hardcoded CPU policy describes its original use; the separate compute
evidence is authoritative for the cloud harness. NVIDIA process samples supply
additional evidence that Blender opened a GPU compute context.

Outputs are explicitly enumerated and hashed, with request and attempt identity
checked before local comparison. Pixel digests are reported separately from
tolerance-based parity; different hardware need not produce identical pixels.
The accepted verifier supplies image metrics and structural comparisons with
unchanged thresholds. The composite is generated locally, as in T03; this proof
does not claim a cloud compositor implementation.

PowerShell invocation (each output directory must be new):

```powershell
.\.venv\Scripts\python.exe scripts/cloud_parity.py `
  --reference-dir output/verification/rl300-prepared-v1/parity-20260913-v12-dark-anchor `
  --output-dir output/verification/rl300-prepared-v1/cloud-v12-preflight
# Add --execute and select a fresh output directory for the authorized live test.
```

## 2026-09-13 execution result: provider workspace disabled

The accepted v12 input hashes, runtime pins, pixel digests, and backup snapshot
were checked live. Local preflight passed. Nine focused tests passed; the full
repository suite ran 68 tests in 57.013 seconds and exited zero. Independent
review found no blocking harness integration defect. Composite digests are
informational: the comparison pass gate covers beauty/mask/structure only.

Evidence directory:
`output/verification/rl300-prepared-v1/cloud-v12-l4-20260914-03/`
(UTC date in directory names; local date was September 13).
The directory contains request identity, copied profile, and terminal status.
Provider log: `output/cloud-v12-l4-20260914-03.log`.

Modal built the image and verified the Blender archive SHA-256 successfully.
The function invocation then failed with:

```text
modal.exception.ConflictError: workspace ac-B9A5ODnjcergtOae4PfZAd is disabled
```

Only one configured Modal profile exists: `mhintz1980`, workspace `mhintz1980`.
Read-only provider inspection confirmed all three proof apps stopped, with zero
tasks. Final app: `ap-IhWzAM98xshxIBegmpg7au`. No GPU render artifacts returned;
no GPU parity, timings, or cloud acceptance can be claimed. Build charges were
not queried; the run estimate above is not an actual billed total.

Two preceding launch issues were corrected: PowerShell redirected output using
an encoding unable to print Modal's checkmark; the serialized Python function
required matching local/container Python versions. Wrapper Python now matches
the caller and remains separate from the pinned Blender runtime. A preflight
import cache write was also prevented, and its sole generated cache was removed.
All original frozen payload hashes remain unchanged.

Resume after the Modal workspace is enabled, using a new output directory and
`--execute`; cloud testing is already authorized. Do not rerun geometry edits or
rebuild the accepted payload. Any calibration failure must be reported with
measurements; it does not authorize threshold changes.

## 2026-09-14 execution: render passed, GPU-evidence matcher false negative

After the workspace was re-enabled, run
`output/verification/rl300-prepared-v1/cloud-v12-l4-20260914-04/` (provider
log `output/cloud-v12-l4-20260914-04.log`) completed the full protocol: image
built with the verified archive hash, frozen payload mounted, OptiX armed
(only `CUDA_NVIDIA L4_0000:00:07_OptiX` enabled, CPU disabled), render
completed in 238.5 s with Blender exit 0, and the required-GPU negative
control exited 1 with `GPU_REQUIRED`.

The run was still marked failed by `NO_BLENDER_GPU_PROCESS_EVIDENCE`. Root
cause: `nvidia-smi --query-compute-apps` in Modal's PID-namespaced container
reports the compute application as PID 1 under the init binary's name
(`/bin/dumb-init`), so the harness's substring match on "blender" can never
succeed. The raw samples show one sole compute app whose GPU memory ramps
10 -> 814 MiB and peaks at 1,642 MiB, holding 814 MiB across the entire
238 s render window — Blender's OptiX context attributed to PID 1.

`comparison.json` in that directory was computed afterwards, locally, with the
same `compare()` the normal flow runs; the original copy held only
`{"passed": false}` because the failed gate skipped comparison, and
`status.json` is unchanged. The frozen verifier's metrics pass on the
hash-verified downloaded artifacts: mask IoU 0.99996, coverage delta 3.6e-06,
linear RGB MAE 0.000336, p99 0.00693, zero structural differences. Pixel
digests differ as expected across hardware. No threshold was changed.

`scripts/cloud_parity.py` now accepts GPU-process evidence as either a
compute app named blender or a sole compute app holding at least
`MIN_SOLO_GPU_MIB` (256 MiB); five focused tests were added and the full
suite passed (73 tests, exit zero).

## 2026-09-14 execution: corrected harness passes end to end

Run `output/verification/rl300-prepared-v1/cloud-v12-l4-20260914-05/`
(provider log `output/cloud-v12-l4-20260914-05.log`, UTF-16 from PowerShell
redirection) passed the full protocol under the corrected matcher:
`status.json` "passed", wall 273.2 s, no failures, Blender exit 0, OptiX
backend, render phase 259.1 s, `blender_gpu_process_seen: true` from 249
samples of the sole PID-1 compute app (peak 1,642 MiB), required-GPU
negative control exited 1, all eight artifacts hashed and downloaded.
`request.json` records the corrected harness SHA-256. Comparison on the
frozen verifier's unchanged thresholds: mask IoU 0.99996, coverage delta
3.6e-06, linear RGB MAE 0.000336, p99 0.00693, zero structural differences;
composite executed locally as designed. Pixel digests differ from the CPU
reference and from run -04 by GPU nondeterminism, which the tolerance gate,
not digest equality, covers.

This completes the authorized bounded experimental cloud parity proof of
the frozen v12 dark anchor, including the required-GPU failure control. It
does not complete the approved plan's production T04 result contract, T05
compositor hardening, or T06 shared CLI transport.

## 2026-09-20 authorization: Modal is the render platform

Mark, 2026-09-20, verbatim: *"no videos locally. Always in Modal. There is
$30 per month free usage and it's way faster. This laptop can't handle it
well."*

What this does and does not authorize:

- **Does** make Modal the default platform for all render work - video frames
  and preview frames alike. The local workstation is retired as a render
  device (its 4.5% HIP crash rate and single-job wall clock are recorded in
  `docs/video-pipeline-brief.md` sections 3.5 and 6.1).
- **Does** name a recurring ceiling: USD 30 per month, the free-tier
  allowance. Per-run cost estimates are recorded in each dispatch's
  `request.json` (`cost_estimate_usd`), with measured seconds recorded after
  the run so estimates converge on reality.
- **Does not** flip `cloud_authorized` in verifier output; that flag stays
  hardcoded false by design, exactly as the 09-13/09-15 entries state.

This supersedes the video brief's "no cloud spend" T-V2 scope
(`docs/video-pipeline-brief.md` section 9): the turntable proof renders on
Modal, and the frame batching analysis in its section 4.3 becomes the
sequencer's core constraint - batched frames per container, not one
container per frame.

### First dispatch under this authorization: turntable environment preview

Recorded before dispatch, per the standing rule: **2 frames** of
`jobs/rl300_04_studio-white.json` (the two-map turntable pattern), azimuths
42 (the job's own framing) and 222 (the back-of-orbit sector where the
single-plate defect measured median luminance 36/255), via
`scripts/cloud_job_render.py`, one L4, 4 cores, 16 GiB, one Blender process
per frame. Estimate **USD 0.13** at the local-measured marginal rate
(101.65 s/frame, brief section 3.1) plus one 229 s cold start; **USD 0.60
ceiling** if both frames pay full cold-process cost. The true L4 marginal
rate is unknown until this run measures it (brief section 4.5), and that
measurement is a stated purpose of the dispatch.

### 2026-09-20 execution: preview passed, and the L4 pricing question closed

Three dispatch attempts under the preview authorization. Attempt 1 failed at
function hydration (Modal 1.5.1 pickles imported functions by reference;
`msp_render_cli` was not in the image — no user code ran, no GPU time
billed); fixed by evaluating GPU-process evidence locally from the returned
samples. Attempt 2 (`...-run2`) failed in 4.4 s — CAD and HDRI were mounted
flat at `/input/` while the manifests referenced `/input/cad/...`; fixed by
keying mounts by container destination, with the invariant pinned by test.
Attempt 3 (`output/preview-turntable-20260920-run3/`) **passed**:

- Both frames rendered, exit 0, OptiX (`NVIDIA L4` sole enabled device),
  GPU-process evidence true, all artifacts hashed and downloaded.
- **The `render-report.json` bytes-build_hash fix (2026-09-17) is proven on
  real cloud Blender**: valid report, `"build": "b70da489d7f4"` decoded,
  enabled devices and timings recorded.
- Measured wall: **frame az42 188.6 s** (cold container: includes Blender
  startup and OptiX kernel compilation), **frame az222 11.4 s** (warm
  container, same production settings: 1800 x 1250, 96 samples, OIDN, AgX).
- **Warm marginal render cost is now measured, not bounded: ~10 s/frame** at
  production settings (render phase 10.05 s). The video brief's 4.2 cost
  bounds ($9.45-$24.09 per 300-frame shot) are retired by measurement:
  300 warm frames at 10 s plus one cold start is about **USD 1.00 and
  ~55 minutes of wall clock** on one L4, and the brief's 4.5 measurement
  ask (one $0.372 run) was answered by this $0.07 run instead.
- Two independent photorealism reads of the composited frames found the
  render "borderline indistinguishable from photography" at web scale with
  these watch-items: no visible depth of field at f/11 (a manifest knob,
  not a pipeline gap), no directional floor shadow (`shadow_opacity: 0.0`
  in this job's compositing block — a job setting), over-clean/outlier-free
  metal and floor (no fingerprints, smudges, dust, scratches), a faintly
  textured white plate backdrop, and soft edges where high-frequency
  geometry meets the backdrop (a known composite limitation at AA depth).
  All are recorded as T-V2 touch-up candidates, not defects of this render.

### 2026-09-20 batch-1 preview: touch-ups verified, DOF cost measured

`output/preview-turntable-batch1-20260920/` - same two azimuths as run3,
with three taste overrides applied via the new `--set` machinery (source
job file untouched, overrides recorded in `request.json`): DOF f/11 -> f/3.2
(`camera.depth_of_field.f_stop`), contact shadow on
(`compositing.shadow_opacity` 0 -> 0.35), deepened sweep plate
(`backgrounds/env_studio-white-v2.png`, floor-darkening 16 + vignette 0.8;
builder defaults regenerate the accepted plate byte-identically,
sha256-verified). Passed, both frames, OptiX evidence true.

- **Measured DOF cost: warm marginal 10.2 s vs 10.05 s baseline (+1.5%)** -
  effectively free, resolving the touch-up table's 0-20% estimate. The cold
  frame's +52 s (184.2 -> 236.0 s) is one-time OptiX kernel compilation for
  the DOF variant; at 30 frames/container it amortizes to ~USD 0.05/shot.
- Independent vision read verifies all three effects: graduated front-sharp/
  rear-soft focus across the machine, a plausible anchoring shadow (tiny
  brightness halo at the left skid rail worth re-checking in motion), and a
  visible bottom/corner falloff in the sweep. New caveat: the machine-to-
  backdrop boundary now reads slightly sharper than the machine's own DOF
  gradient - the known composite limitation the real-floor touch-up (batch
  3) exists to remove.
- Two dispatcher guards landed along the way: `--set` rejects unknown paths
  (a typo must fail locally, not render the unmodified job), and frame_plan
  rejects missing local inputs before any billable call.

### 2026-09-20 batch-2: 30-frame orbit probe, all sequence gates pass

`output/preview-turntable-batch2-20260920/` - 30 frames, azimuths 42..390
step 12 (one full orbit), same kept batch-1 look, one warm container after a
single cold start. All 30 rendered, exit 0, OptiX evidence true per frame.
`scripts/probe_sequence.py` then composited every frame through the T05
gates (all pass, machine pixels byte-exact on every frame), applied the new
lens pass (vignette 0.45 / bloom 0.3 / grain 2.2, per-frame seed), and
encoded the first motion artifact, `turntable-loop.mp4` (H.264 crf 18,
12 fps, looped).

- **Declared gates, all measured, none widened:** no flicker outlier frame
  (max frame MAE 28.1 vs median 21.4, under the 3x neighbour factor); no
  duplicate consecutive digests; uniform azimuth steps; decode-back PSNR
  39.59/40.40/39.60 dB on first/mid/last against the declared 35 dB floor;
  grain determinism proven adversarially (a rerun of the mid frame
  reproduced the delivered bytes' sha256 exactly).
- Section 7.4 scalars recorded for the first time at 12 deg/frame: max
  second difference - coverage 0.063, mean interior luma 13.0, p95 39.0.
  These are MEASUREMENTS, not yet gates; their thresholds get declared in
  the T-V2 manifest when the step is 1.2 deg, not retrofitted from a 12 deg
  probe.
- Independent vision read of the lensed frame: vignette subtle, bloom
  visible on the hottest metal highlights, fine grain present - "real
  optics" character, no banding or artifacts. Grain judged the single most
  effective realism lever of the three.
- Cost: estimate USD 1.0161 recorded pre-dispatch (still priced at the
  stale 101.65 s/frame local figure); measured container time will be
  recorded from Modal's usage when it settles - the warm rate is now well
  known (~10.2 s/frame), so the true figure is near USD 0.18.

### 2026-09-20 batch-3a: no-duplicate-frames ruling implemented — zero dispatch

Recorded here because the convention is that *every* run is recorded, including
the ones that spend nothing: **no Modal call was made, no frame was rendered,
estimated and measured cost both USD 0.00.** Batch 3a is pure local Python.

Trigger: Mark approved `batch2-turntable-loop.mp4` and ruled that no delivered
video may contain duplicated frames (verbatim in `docs/rl300-parity.md`,
2026-09-20 acceptance entry). The accepted file was `nb_frames=150` — 30 unique
frames played five times — because `scripts/probe_sequence.py` passed
`-stream_loop 4` to ffmpeg.

Landed (see `docs/video-pipeline-brief.md` §13 for the reasoning and the 3a/3b
split):

- Encode is one pass; `encoded_frame_count()` reads the **encoded file** via
  `ffprobe` (with an `nb_read_frames` fallback) and gates
  `ENCODED_FRAME_COUNT_MISMATCH`. The pre-existing duplicate gate digests the
  composited PNGs and passed correctly — it could never have caught a
  duplication introduced downstream at encode.
- `orbit_azimuths(count, start)` generates one orbit with no wrap-around repeat;
  `reject_duplicate_azimuths()` runs in `frame_plan` preflight, **before any
  billable call**, keyed on `frame_name()` — the frame label is the billing
  unit, so two azimuths naming the same frame are one frame however different
  the floats look. A duplicate azimuth now costs USD 0.00 instead of a full
  frame that gets overwritten.
- `--orbit N` on the dispatcher, mutually exclusive with `--azimuths`, recorded
  as `orbit: {count, step_deg}` in `request.json`.
- `MATTE_COVERAGE_CEILING = 0.90` + `matte_plausibility_pass` in the compositor:
  the tripwire for batch 3b, where an opaque in-scene floor would otherwise
  enter the alpha-derived matte as "product" and make three gates pass while
  measuring nothing. Grounded on measured coverage near 0.42 (0.4197–0.4442
  across a full orbit), so it cannot fire on a legitimate product matte.

**Cost avoided, measured against this repo's own rates:** at the known warm L4
marginal 10.2 s/frame and the recorded all-in USD 0.00030992/s, one duplicate
frame that the preflight now rejects would have cost ~USD 0.0032 and produced
nothing. The real saving is at shot scale: a 300-frame orbit mis-specified with
a repeated azimuth previously rendered and silently discarded frames; and the
encoder defect, had it reached a 300-frame shot, would have produced a 1500-frame
file — 80% of it duplicated bytes.

The duplicate check keys on `frame_name()` rather than the raw float **because
the frame label is the billing unit** — it names the frame directory, the
per-frame `job_id`, and the container output dir. Measured before that fix:
`reject_duplicate_azimuths([42.0, 42.4])` returned clean while
`frame_name(42.0) == frame_name(42.4) == "az42"`, so `--azimuths 42,42.4` would
have dispatched two billable renders into one destination and the second would
have overwritten the first — two frames paid for, one image. The modulo-360
check is kept alongside the label key, so a same-pose repeat such as `[42, 402]`
still fails even though its labels differ.

**A measured ceiling this establishes: 360 frames per orbit.** `frame_name`
rounds to whole degrees, so 400 unique azimuths collapse to 360 unique labels.
`--orbit 400` now fails at preflight (`DUPLICATE_AZIMUTH: 46.5 repeats 45.6`)
rather than paying for 40 frames that overwrite others. Orbits of 30, 100, 300
and 360 all pass, so the T-V2 target of 300 frames at 1.2°/frame is unaffected.
Past 360 frames the pipeline needs a finer frame label — a real change, not a
threshold to widen.

A second readback defect was fixed in the same round: `probe_sequence` recovered
each frame's azimuth from the **rounded directory label**, so any orbit whose
step is not a whole degree produced non-uniform steps and tripped
`NON_UNIFORM_AZIMUTH_STEPS`. Measured: at 300 frames the true step is 1.200 but
the label steps were {1, 2}, so a 300-frame shot — the T-V2 target — would have
failed its own sequence gate. It now reads `camera.azimuth_deg` from the frame's
own manifest (`frame_azimuth`), falling back to the label only for older run
directories that predate per-frame manifests. Verified against the real batch-2
run dir: `frame-az102` reads back 102.0.

No threshold was widened. The new frame-count check is an equality; the 35 dB
decode PSNR floor, the 3× neighbour-outlier factor, IoU 0.98/0.995, MAE 0.01 and
p99 0.05 are unchanged.

Delegation record (orchestration doctrine): implemented by `zai/glm-5.3-flash`
via the ocx proxy — **proven** from 48 proxy-log rows resolving to
`glm-5.3-flash`/provider `zai` inside the dispatch window, not from the CLI's
own echo. Adversarially reviewed in fresh context by `deepseek/deepseek-flash`
(different vendor family), which returned FIX-FIRST with two blockers; both were
reproduced independently before being accepted, and a correction round followed.
Details in the handoff.

### 2026-09-21 batch-3b FINAL: rendered studio floor — 2-frame probe technically approved, owner look pending

Three dispatch attempts on 2026-09-21, 2 frames each (az 42 + 222, the
standing preview pair) of `jobs/rl300_05_studio-floor.json` via
`scripts/cloud_job_render.py`, one L4, one Blender process per frame, all
renders on Modal, composited locally. Per-dispatch corrected estimate
**USD 0.197** recorded pre-dispatch in each `request.json`
(`render_passes_per_frame: 2`; the preflight-only dir
`output/preview-studio-floor-3b-20260921/` carries a superseded 0.134 from
the corrected frame-count bug and had no dispatch).

**Attempt record (all attempts counted in cost totals):**

| Run | Outcome | Recorded container s |
|---|---|---|
| `...-run1/` | passed; wall 279.1 s; both frames Blender exit 0 with GPU-process evidence; artifacts hashed + downloaded | 253.762 + 12.594 = 266.356 |
| `...-run2/` | **failed** on az42: `BLENDER_FAILED_OR_NO_OUTPUT exit=20`, wall 12.304 s | 3.417 |
| `...-run3/` | **passed**; wall 270.175 s; both frames Blender exit 0 with GPU-process evidence; artifacts hashed + downloaded | 233.877 + 13.005 = 246.882 |

**Run2 failure cause (recorded):** the camera projection ran before Blender's
depsgraph update, so `camera.matrix_world` was stale when the floor-mode
projection computed. Fix: explicit depsgraph update before projection. Run3
confirms the fix.

**Run3 measured timings (per-frame `render-report.json` / `measured-matte-shadow.json`):**

| Frame | Beauty | Matte | Render phase | Frame total | Container s |
|---|---|---|---|---|---|
| az42 (cold, OptiX compile) | 222.69 s | 2.74 s | 225.69 s | 228.50 s | 233.877 |
| az222 (warm) | 8.38 s | 2.63 s | 11.27 s | 11.72 s | 13.005 |

Render phase and frame total are distinct numbers and are labeled separately
from here on. **Warm RENDER phase 11.27 s vs the 10.2 s batch-1 warm baseline
is +10.5% — inside the declared +10-30% band, numerically true.** The warm
frame total (11.72 s) is NOT compared against the 10.2 s render baseline;
no total-vs-baseline percentage is claimed.

**Cost totals, all attempts included, RATE-DERIVED NOT BILLED** (recorded
all-in USD 0.00030992/s; Modal usage not queried, no invoice figure claimed):
516.655 container-s across run1+run2+run3 ≈ **USD 0.160** (run1 ≈ 0.083,
run2 ≈ 0.001, run3 ≈ 0.077).

Run3 mechanism and gates (from `measured-matte-shadow.json` and
`sequence-report.json`): product-only matte from the second floor-hidden
transparent render; pre-lens RGB byte-exact against full beauty (max drift 0
both frames); mask consistency vs the independently rendered matte alpha;
`matte_plausibility_pass` (coverage 41.28% az42 / 41.32% az222, ceiling 0.90
unfired); synthetic shadow suppressed (configured 0.35, effective 0.0 — real
floor shadows); lens applied after gates. `probe_sequence
--expect-frames 2 --no-encode` passed in `rendered_floor` mode: grain
deterministic, no outliers, frame MAE 44.14. Suite: **211 tests OK**
(`output/batch3b-tests-transform.log`). Model routing for the implementation
rounds: `output/batch3b-routing-evidence.json` (196 ocx rows: 153
glm-5.3-flash, 24 glm-5.3, 43 deepseek-flash); no model spend figure asserted.

**Mask IoU correction.** The 0.966 (az42) / 0.800 (az222) numbers are raw-mask
IoU measurements of the floor-mode raw masks against the raw batch-2 masks at
the matching azimuths (reproduced independently in
`output/batch3b-evidence-review-deepseek.txt`); earlier text saying they were
"computed against shifted composites, raw batch-2 IoU unmeasured" is wrong and
is corrected here. They are **not a matte defect**: the floor mask is a strict
subset of the batch-2 mask (zero product pixels missing in both), and the
batch-2 masks include the shadow-catcher contact shadow while the floor-mode
masks are product-only — so the two are definitionally incomparable and the
0.98 threshold does not apply across them. Camera blocks are identical
(azimuth 42/222, elevation 11.0, distance 6.6, 85 mm, target offset
[0,0,0.92]); framing is not the cause.

**Visual status (owner gate).** Run1's lensed composites showed a finite-floor
diagonal edge against the dark world (FIX-FIRST). After the run3 fix, the
parent visually inspected both run3 `composite-lens.png` frames: the diagonal
finite-floor edge is eliminated, the background is smooth, and shadows are
grounded. This was technical approval for the TWO-FRAME probe only.

**Owner look review, 2026-09-21: FIX-FIRST — floor look NOT accepted.** Mark
annotated run3 az42 and identified three defects (markup files in
`output/preview-studio-floor-3b-20260921-run3/cloud/frame-az42/`:
`composite-lens-markup1.png`, `composite-prelens-markup2.png` — the white
ellipse "approximates the outline of the artifact" — and
`composite-prelens-markup3.png`, a mirrored-halves comparison). Diagnosis
(parent, accepted by owner): the background above the floor line is the HDRI's
own baked backdrop, and the rendered floor plane does not match it at the
horizon seam; the softbox panel in `env_studio-softbox.png` reflects off the
floor at grazing angle as an apparent "spotlight" pool on the right side
(markup1/2); the mirror mismatch (markup3) is partly the deliberately
asymmetric light rig (normal) and partly that floor/backdrop seam (defect).
**Owner decision: replace the flat plane with a curved studio cyclorama
(infinity cove)** — one continuous neutral surface, rotationally symmetric,
orbit-safe. Plan and constraints: `HANDOFF-2026-09-21-batch3b.md`. The
batch-3b floor engineering (matte mechanism, gates, timing) stands; the floor
*geometry* is the open item.

Workspace note: a residual `.test_deps/` directory at the repo root was
created against instruction by a prior agent and is permission-inaccessible;
it is left untouched (not deleted, ACL not changed). All batch-3b code changes
are uncommitted; unrelated existing work is untouched.

### 2026-09-21 batch-3c: studio cyclorama (owner Option B) — 2-frame probe passed, owner look pending

The batch-3b plane was replaced by a rotationally symmetric studio cyclorama
(flat disc + tangent quarter-arc fillet + vertical wall), sized per frame from
the actual camera's frame-corner rays — below-horizon corner hits bound the
disc radius (Euclidean radial metric), above/at-horizon corner rays bound the
wall height via the wall-cylinder crossing (wall derived against the FINISHED
radius; ordering load-bearing). Implementation delegated to GLM-5.3-Flash and
adversarially reviewed by DeepSeek-Flash (fresh context; FIX-FIRST verdict —
guard-ordering, CYC_MESH_INVALID unit coverage, degenerate zero-height wall
ring when no corner ray is above the horizon, test-fidelity fixes — all
addressed before dispatch). `FLOOR_HORIZON_IN_FRAME` retired; new error codes
`CYC_WALL_UNREACHABLE`, `CYC_CAMERA_OUTSIDE`, `CYC_MESH_INVALID`; roughness
0.6 → 0.7 (the owner-sanctioned pool-softening knob). Suite: **220 tests OK,
exit 0** (venv interpreter, `${PIPESTATUS[0]}` checked). Preflight dry-run
(headless Blender, NO render — `output/batch3c-preflight-derive.py`): both
azimuths derive disc r=52.19 m (grazing corners; legacy min 23.05 m), fillet
3.29 m, zero above-horizon corner rays → wall ring correctly skipped, wall
top z=3.29 m sits above the frame top, camera inside the cylinder, mesh
1665 verts / 1664 faces.

**Dispatch (1 attempt, 2 frames, az 42 + 222), per-dispatch estimate USD
0.197 in `request.json`; measured RATE-DERIVED NOT BILLED:** 296.874
container-s ≈ **USD 0.092** (all-in rate 0.00030992/s; no invoice queried).
Run dir `output/preview-studio-floor-3c-20260921/`; Modal app
ap-BF5WG9POgmERjJOyPNHtC0.

| Frame | Beauty | Matte | Render phase | Frame total | Container s |
|---|---|---|---|---|---|
| az42 (cold, OptiX compile) | 275.70 s | 2.84 s | 278.83 s | 279.34 s | 282.929 |
| az222 (warm) | 8.97 s | 2.73 s | 11.99 s | 12.44 s | 13.945 |

**Warm RENDER phase 11.99 s vs the 10.2 s batch-1 warm baseline = +17.5% —
inside the declared +10-30% band.** Against run3's plane (11.27 s) the cyc
mesh costs +6.4%. Frame totals are distinct numbers and are not compared
against the render baseline.

Gates (run dir + recomputed from downloaded artifacts): both frames Blender
exit 0 with GPU-process evidence; dispatcher floor finishing `success` in
`rendered_floor` mode both frames; `probe_sequence --expect-frames 2
--no-encode` **passed** — fidelity_gate_all_pass true, grain deterministic,
no outlier frames, no problems, frame MAE 44.15; mask coverage 41.28% /
41.32% (MATTE_COVERAGE_CEILING 0.90 unfired), mask==matte-alpha agreement
100.000% both frames. **No encode was run — a 2-frame probe supports no
full-orbit claim.**

Lighting risk (wall occluding low-angle HDRI light) — MEASURED, negligible:
product-pixel luminance over mask==255, cyc vs run3 plane: az42 130.119 vs
129.924 (**+0.15%**), az222 100.481 vs 100.217 (**+0.26%**).

Vision read (parent, on 3c composites): (1) the softbox pool right of the
machine is now a soft broad falloff — no hard "spotlight" ellipse (roughness
0.7 doing its sanctioned work); (2) no plane edge or hard seam anywhere —
floor blends into a continuous cove gradient in both frames; (3) mirror test
(regenerated `composite-prelens-mirror-check.png` per frame, Mark's markup3
exercise): the floor line and background gradient now continue across the
mirrored seam; the residual left/right difference is the deliberately
asymmetric light rig (accepted as normal); mirrored-half mean abs diff 29.35
(az42) / 34.39 (az222) — dominated by product structure and rig, not a
backdrop seam. **Owner look review is the open gate** — "looks good" from
anyone else is not acceptance; no encode, no full orbit, no batch-4 work
until Mark's explicit words.

### 2026-09-22 batch-3d: cove-in-frame cyclorama — structural gates green, background-band gate FAILED on az42 as declared

Owner verdict on 3c (2026-09-22): az222 good, az42 rejected ("identical to
3b"). Pixel measurement confirmed 3c was a visual no-op (backgrounds within
1.5/255 of 3b) because the 3c derivation put the cove OUTSIDE the frame
(fillet at 55.65 m; frame-top rays land ~56 m). Root cause fixed in 3d:
`required_floor_radius` deleted, replaced by `required_cove_profile`
(disc sized just past the product; fillet+wall/arc carry the backdrop; dense
65-sample top-edge scan per the spec-phase adversarial review; legacy minimum
retired). Spec `output/batch3d-cove-inframe-spec.md` (DRAFT-2, 9 review
findings incorporated), implementation by DeepSeek-Flash via ocx after a
glm-5.3 attempt 429'd, implementation review by GLM via ocx (no code defects
at BLOCKER; the deepseek reviewer seat 429'd mid-read, re-routed). Suite:
**233 tests OK, exit 0** (venv interpreter, `${PIPESTATUS[0]}` checked; was
220).

**Preflight fidelity, now proven:** the 3c-era preflight/Modal divergence
(52.19 vs 58.94 m) is root-caused to `view_frame()` shaping the frustum from
the SCENE resolution; preflights must set the manifest resolution. The 3d
preflight (real `build_studio_floor`, headless, NO render,
`output/batch3d-preflight-final.py`) and the Modal run's new run-side
derivation log agree field-for-field, both azimuths: corner ground radials
[56.069, 2.865, 2.865, 56.069], top-edge max crossing z=1.920 m (65 samples;
matches the reviewer's independent full-frame scan 1.9194), floor r=10.560,
wall r=14.666, fillet r=4.107, wall segment SKIPPED (rim z=4.157, arc tops
the profile; `cyc_mesh_data` strict `>` — documented regime), cove line
row=0.323 (declared band 0.25-0.45), resolution 1800x1250@100%. 56.069 x 1.05
+ blur = 58.94 m reconciles the 3c run record exactly.

**Dispatch (1 attempt, 2 frames, az 42 + 222):** run dir
`output/preview-studio-floor-3d-20260922/`; Modal app ap-NeDqs7isloqsGUPQzUNOAt;
estimate <= 3c's USD 0.197/dispatch; measured RATE-DERIVED NOT BILLED:
280.877 container-s ≈ **USD 0.087** (all-in rate 0.00030992/s; no invoice
queried).

| Frame | Beauty | Render phase | Container s |
|---|---|---|---|
| az42 (cold, OptiX compile) | 252.81 s | 255.94 s | 267.135 |
| az222 (warm) | 9.11 s | 12.04 s | 13.742 |

Warm render phase 12.04 s vs the 10.2 s batch-1 baseline = **+18.0% — inside
the declared +10-30% band** (3c: +17.5%).

Gates: both frames Blender exit 0 with GPU-process evidence; dispatcher floor
finishing `success` both frames; `probe_sequence --expect-frames 2
--no-encode` — fidelity_gate_all_pass true, grain deterministic, no outlier
frames. Matte coverage and mask==matte-alpha: unchanged mechanism, re-checked
in the sequence report. Product luminance over mask==255 vs run3 plane:
az42 116.988 vs 116.131 (**+0.74%**), az222 88.801 vs 87.136 (**+1.91%**) —
small but larger than 3c's, consistent with the nearer wall occluding some
low-elevation env light (the spec's declared risk).

**NEW GATE, DECLARED 2026-09-22 (ruling 4):** background band step
`measure_background_step` on composite-prelens.png (background columns =
mask column max < 0.01; max |row-to-row| mean-luma delta; lens pass excluded
— it inflates the metric via grain/bloom: az42 2.15 pre-lens vs 2.21
post-lens on 3c). Threshold 1.8/255/row; provenance measured on the shipped
3c artifacts with the same function: az42 defect 2.0623 (row 553), az222
approved 0.6891.

**GATE RESULT: az42 2.1536 (row 553) — FAIL (> 1.8). az222 0.7545 (row 3,
frame-edge noise) — PASS.** The geometry did exactly what it was designed to
do (cove line in frame at row 0.323, rim above frame, no ray escapes), but
the az42 two-tone persists: the env lights the arc's upper region dark on
that side (top-of-frame rows ≈ 92.5 vs 3c's far-floor 97-106), so the
pool-edge contrast at row 553 barely moved. This is the spec's declared
§7 fallback: the remaining mechanism is the ENV horizon-band (an asset round
under ruling 2), not more geometry. No encode was run — a 2-frame probe
supports no full-orbit claim. Vision read (parent): az222 unchanged from its
approved character (smooth sweep, no seam); az42 upper background now shows
a subtle arc gradient instead of a flat void, but the dark-backdrop/lit-floor
step remains. Mirror-check markups regenerated per frame
(`composite-prelens-mirror-check.png`). **Owner look review is the open
gate**; a look rejection here is expected to resolve through the env round.

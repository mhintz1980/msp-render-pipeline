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

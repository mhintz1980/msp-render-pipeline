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

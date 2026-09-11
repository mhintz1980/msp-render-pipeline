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

# RL300 additional job parity — 2026-09-14

Scope: local evidence for `jobs/rl300_01_no-background.json` and
`jobs/rl300_03_excavation-pit.json`, using the accepted v12 prepared scene.
Studio-dark remains the formal accepted reference. These jobs produce separate
review candidates; they do not authorize cloud execution or production dispatch.

## Source and preparation

- Source SHA-256: `115fd725a9659901e035f0b6cc474449bb7d740c816d0107aa6dd7520bf3bb6a`.
- Prepared SHA-256: `3da94b93eefb2aa41da01505d2dd6ef2b415f6daf484f3381d3acf943073e51e`.
- Preparation: `output/verification/rl300-prepared-v1/grounded-preparation-20260913-v12/preparation-report.json`.
- Runtime: checksum-pinned Blender 5.1.1, build `b70da489d7f4`, in local WSL Ubuntu.
- Proof settings: 900 × 625, 48 samples, CPU, fixed frame and seed, declared
  read-only payload inside bubblewrap. The original jobs request 1800 × 1250
  and 96 samples; this is the existing bounded parity protocol.

Both job manifests name the CAD master, while preparation names the repository
copy. Their bytes were checked and match the accepted source hash. No job,
geometry, prepared scene, or accepted reference needs to be rewritten.

## Preflight history

`output/verification/rl300-prepared-v1/parity-20260914-v12-excavation-pit/`
is the failed first preflight: the old verifier rejected the two different source
paths despite identical bytes. No render was launched. Keep that evidence as-is;
successful retries use new directories.

## Results

Both proofs exited 0 with no failures and status `awaiting_reference_acceptance`.
Evidence directories under `output/verification/rl300-prepared-v1/`:

| Job | Evidence directory | Repeat mask IoU | RGB MAE / p99 | Structural differences |
|---|---|---|---|---|
| No background | `parity-20260914-v12-no-background/` | 1.0 | 0 / 0 | None |
| Excavation pit | `parity-20260914-v12-excavation-pit-02/` | 1.0 | 0 / 0 | None |

Both repeat coverage deltas are zero. Camera shifts trigger silhouette mismatch;
material changes trigger RGB mismatch. Injected missing environment dependencies
exit nonzero with `MISSING_DEPENDENCY`. All four rendered modes per job pass the
mask/beauty-alpha checks. Both source and prepared hashes remain unchanged.
The excavation composite passes the saved product-pixel fidelity check.

Decoded reference pixel SHA-256 values:

- No-background beauty: `3594321bd81e7edd035ced83c74bcdaeacf4980a0914645c88fe6085e45940ad`.
- Excavation beauty: `4d239c4e0ce91069df972df84942359b90e94999dee9d349fa8c525be7e2b334`.
- Excavation composite: `a319394b3800f7bf02c9a7cc64cab5e7accd0c0baee1005c326f1fcc98e2b2cd`.

No-background has no composite artifact. All owner, G0, and cloud authorization
fields in these new reports remain false. Human visual review is still pending.

Validation: full suite **77 passed** in 53.809 s; after a test-only portability
adjustment, the focused parity suite **28 passed** in 0.765 s. Logs are
`output/parity-20260914-tests.log` and
`output/parity-20260914-focused-tests.log`. `git diff --check` passed.
The final frozen-anchor check also confirmed the original source/prepared hashes
and the beauty, mask, and composite pixel digests; see
`output/verify-20260914-frozen-anchor.py`.
Fresh independent read-only review returned **ship**, with no findings, after
inspection of the staged changes and saved proof evidence. This code-review
verdict does not supply human visual acceptance.

## Verifier behavior

For no-background, the payload contains no environment image or backdrop and
the compositor does not run. Its profile identifies product-only coverage and
omits composite hashes. The missing-texture control deliberately adds a missing
HDRI dependency to the control manifest; it tests rejection of that injected
dependency, not removal of a texture from the texture-free reference job.

For excavation-pit, the declared image drives lighting and compositing. The
saved composite must preserve every placed, fully opaque product pixel exactly.
Both jobs retain the existing image thresholds, structure comparison, camera
shift, material-change, and missing-dependency controls.

Run from PowerShell, with a fresh output directory on each invocation:

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
.\.venv\Scripts\python.exe scripts/verify_scene.py `
  --preparation-report output/verification/rl300-prepared-v1/grounded-preparation-20260913-v12/preparation-report.json `
  --linux-runtime /home/markimus/.cache/studiomark/blender-5.1.1-20260910/blender-5.1.1-linux-x64 `
  --job jobs/rl300_01_no-background.json `
  --output-dir output/verification/rl300-prepared-v1/<new-evidence-directory>
```

Use `jobs/rl300_03_excavation-pit.json` for the other job. These commands run
locally; the cloud harness remains outside this task's scope.

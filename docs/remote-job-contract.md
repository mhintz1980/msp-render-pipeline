# T04 — honest result contract and compute evidence

Built 2026-09-15 in the worktree `C:/Projects/msp-rp-t04`, branch
`lane/t04-result-contract`, baselined at `1d493d5` (which carries the ten pending
scene-prep fixes from the working tree of `msp-render-pipeline-scene-prep`).

Implemented by the `codex-implementer` lane (GPT-5.6 Luna, high effort) against a
written spec; reviewed, corrected and re-verified here. **Nothing is committed** —
the change is one reviewable diff in the worktree.

Local work only. No cloud call, no Modal call, no `.blend` opened.

## What exists now

`msp_render_cli/remote_job.py` — host-side, no `bpy`, no third-party imports.

| | |
|---|---|
| `job_id(request)` | SHA-256 over a canonical serialisation of `IDENTITY_INCLUDED_FIELDS` only |
| `build_request(...)` / `validate_request(...)` | pins inputs by per-file SHA-256, runtime, render settings, expected artifacts, `require_gpu` |
| `build_result(...)` / `validate_result(...)` | status, `failure_code`, compute, observed runtime, per-phase timings, artifact hashes and sizes |
| `gpu_process_evidence(samples)` | moved here verbatim from `cloud_parity.py`; the PID-namespace / 256 MiB sole-app rule is unchanged |
| `FAILURE_CODES` | `GPU_REQUIRED`, `MISSING_OUTPUT`, `RENDER_NONZERO_EXIT`, `ARTIFACT_HASH_MISMATCH`, `CONTRACT_INVALID` |

Identity **included**: `manifest`, `input_assets`, `runtime`, `render_settings`,
`expected_artifacts`, `require_gpu`. Identity **excluded**: `request_id`,
`attempt_id`, `submission_id`, `submitted_at`, `output_dir` — bookkeeping that
cannot change the pixels a rerun produces.

Validation is schema-backed against `docs/remote_job_request.schema.json` and
`docs/remote_job_result.schema.json` (Draft 2020-12, `additionalProperties: false`
throughout). `jsonschema` was **not** added as a dependency; the validator walks
the schema documents directly, so the schemas stay the single source of truth.

`scripts/cloud_parity.py` now imports `MIN_SOLO_GPU_MIB` and `gpu_process_evidence`
from the contract module instead of defining its own copy. Its behaviour,
thresholds and output shape are unchanged and `tests/test_cloud_parity.py` passes
unmodified.

## Three defects found in review, and fixed

The lane's diff was sound in structure and wrong in three places that all pointed
the same way — a result that would have *looked* honest while reporting something
the worker never observed.

1. **`cpu_in_mix` lied on the CPU-fallback path.** It was initialised from
   `scene.render.engine != "CYCLES"` and only recomputed inside the branch where a
   GPU device was successfully enabled. A Cycles job that failed to enable any GPU
   and fell back to CPU therefore reported `cpu_in_mix: false` with an empty
   `enabled_devices` — the exact silent-CPU-fallback dishonesty T04 exists to
   remove. Now: if no compute device was enabled, the render is on the CPU and the
   report says so, whatever the engine.
2. **`GPU_REQUIRED` was emitted twice in one message.** The `for…else` raise sits
   inside the outer `try`, so its `RuntimeError` was caught by
   `except Exception as exc` and re-wrapped, producing
   `GPU_REQUIRED: GPU_REQUIRED: no GPU device was enabled`. The outer handler now
   re-raises an already-tagged error unchanged.
3. **The worker asserted a GPU verdict it has no standing to make.** The report
   hardcoded `gpu_evidence: {verdict: false, samples: []}`. The worker cannot
   sample `nvidia-smi` for itself — the dispatching harness does. The block is now
   absent, and `_normalise_compute` supplies the same conservative default. Two
   tests pin this: a `require_gpu` job cannot pass on the worker report alone
   (an enabled OPTIX device is what was *asked for*, not proof it rendered), and a
   report with no `gpu_evidence` key still validates.

Also: `import time` at module scope, replacing three `__import__('time')` calls.

## `require_gpu`-absent parity

When a manifest carries no `require_gpu` key, the device-enabling control flow and
printed output are unchanged from baseline, and `render-report.json` is not
written at all. Existing jobs and existing tests are unaffected.

## Verification

Run with the project interpreter, **not** the system Python:

    C:/Projects/msp-render-pipeline-scene-prep/.venv/Scripts/python.exe -m unittest discover -s tests

| | |
|---|---|
| Baseline (`1d493d5`) | 77 tests, OK |
| After | **92 tests, OK** — 13 from the lane, 2 from review |
| `python -m py_compile render_worker.py` | OK |
| `import msp_render_cli.remote_job` | OK |
| `python -m json.tool` on both schemas | valid |
| `git rev-parse HEAD` | `1d493d5` — nothing committed |

### Mutation checks (run here, not taken from the lane's report)

1. `request_id` added to `IDENTITY_INCLUDED_FIELDS` — an attempt id leaking into
   job identity. 1 failure. Restored.
2. `_normalise_compute`'s missing-evidence default flipped `False → True` — absent
   evidence read as a pass. 2 failures. Restored.

Both bit; the suite is evidence, not decoration.

## Note on the interpreter — a real trap

The lane ran the suite with the uv-managed system Python and reported
"75 tests, 3 errors (pre-existing)". Those three errors are
`ModuleNotFoundError: No module named 'jsonschema'` in `test_scene_parity.py` and
`test_scene_preparation.py` — the system interpreter never had
`requirements-test.txt` installed. Under
`msp-render-pipeline-scene-prep/.venv/Scripts/python.exe` the same tree is
**green**. The lane was not wrong about the errors being pre-existing; it was
wrong that they were unavoidable, because it never found the venv.

**Every future spec for this repo must name the interpreter explicitly.** A lane
that silently runs on the wrong Python reports a red suite as the baseline, and a
reviewer who trusts that number accepts a lower bar than the project actually has.

## Not done

- T05 (compositor mask and saved-image gates) and T06 (shared CLI transport).
  `composite_worker.py`, `msp_render_cli/cli.py` and `manifest.py` are untouched.
- Any live dispatch. T07 still needs a named price and run count from Mark before
  the first billable call — see `docs/cloud-smoke.md`.

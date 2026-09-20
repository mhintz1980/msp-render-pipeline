# AGENTS.md — operating index for this repository

One job: turn Myers-Seth pump CAD into finished marketing photography and,
now, turntable video. A job is one JSON manifest in `jobs/`. This file is an
INDEX, not a second source of truth — each fact below lives in exactly one
authoritative place, linked. When those change, change them there.

## Entry point

`HANDOFF-*.md` at the root form a chain; each supersedes the last. **Read the
newest one first** — it carries the current owner rulings, open tasks, and
the state of the video lane. `README.md` is the product/architecture intro.

## Authoritative documents (docs/)

| Topic | Where |
|---|---|
| Acceptance/parity discipline, every owner ruling (verbatim) | `docs/rl300-parity.md` |
| Cloud/Modal: authorizations, run records, measured costs | `docs/cloud-smoke.md` |
| Video lane: measured budgets, gates, T-V2 scope | `docs/video-pipeline-brief.md` |
| Remote job result contract (T04) | `docs/remote-job-contract.md` |
| Photorealism pass: what it adds and why | `docs/PHOTOREAL_CHANGES.md` |
| Schemas (job manifest, remote job request/result, scene parity) | `docs/*.schema.json` |

## Standing owner rulings — the ones that bite

1. **All rendering on Modal, never local** (2026-09-20). Local machine does
   dispatch, compositing, encoding. Ceiling USD 30/month; per-run estimates
   in each dispatch's `request.json`, measured seconds recorded in
   `docs/cloud-smoke.md`. `cloud_authorized` stays hardcoded false — human
   authorization is a doc record, never a machine gate.
2. **Material changes mean a new source `.blend` version and an acceptance
   round.** Never move material fixes into job manifests (the latch lesson).
3. **"Looks good" is not formal acceptance** — parity artifacts stay
   `awaiting_reference_acceptance` until Mark's explicit words.
4. **No gate threshold is widened without new numbers.** Record thresholds
   when declared.
5. **Single upstream**: `origin` (GitHub). The `main` worktree at
   `C:/Projects/msp-render-pipeline` is a separate checkout with none of
   this branch — work happens in `C:/Projects/msp-render-pipeline-scene-prep`
   on `codex/studiomark-scene-prep`.

## Environment facts that will waste your time otherwise

- Python: always `./.venv/Scripts/python.exe` (absolute path). The system
  Python reports phantom pre-existing failures.
- Suite: `./.venv/Scripts/python.exe -m unittest discover -s tests`; from
  Git Bash check `${PIPESTATUS[0]}` — a PowerShell `2>&1` merge corrupts the
  exit code even when the suite prints OK.
- Blender is not on PATH; the proven local path is headless
  `blender --background --python` (and local *renders* are banned by ruling 1).
- ffmpeg 8.1.1 IS on PATH (encoding is local and allowed).
- `output/` is gitignored — it holds evidence directories cited by run
  records; never assume it is reproducible, read the run record instead.

## The machines (repo root, one line each)

- `render_worker.py` — Blender-side job executor: camera, lighting, photoreal
  pass, render report (T04 contract). Runs inside Blender via `--python`.
- `composite_worker.py` — local compositor: T05 integrity gates, contact
  shadow, lens pass (vignette/bloom/frame-seeded grain, after the gates).
- `msp_render_cli/` — CLI transport, remote job schemas, GPU-process
  evidence matcher.
- `scripts/cloud_job_render.py` — Modal dispatcher: one azimuth per Blender
  process, pinned Blender 5.1.1 archive, `--set path=value` taste overrides.
  Trap: Modal 1.5.1 pickles imports by reference — never call local modules
  inside the container function.
- `scripts/probe_sequence.py` — sequence gates (video brief section 7.4) +
  H.264 encode + decode-back PSNR.
- `scripts/cloud_parity.py` — the frozen v12 cloud parity proof (do not
  extend; `cloud_job_render.py` is the production path).
- `scripts/build_studio_softbox_env.py`, `scripts/build_studio_white_plate.py`
  — environment/plate generators; defaults reproduce accepted assets
  byte-identically.

## Conventions

- Every change ships with tests; the suite count is cited in commit
  messages and run records. Honest reporting: measured vs estimated is
  always labeled.
- Cloud runs: estimate before dispatch (in `request.json`), record after
  (in `docs/cloud-smoke.md`), including failures — failed launches are
  recorded too.
- Commit messages state what was verified and how; failures are stated
  plainly, never buried.

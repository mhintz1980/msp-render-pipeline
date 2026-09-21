# Handoff — 2026-09-21 (batch 3b: floor engineering verified; owner look FIX-FIRST → cyclorama)

Worktree: `C:/Projects/msp-render-pipeline-scene-prep`, branch
`codex/studiomark-scene-prep` (single upstream GitHub `origin`). Supersedes
`HANDOFF-2026-09-20-batch3a.md`. Suite **211 tests OK, exit 0**
(`output/batch3b-tests-transform.log`). Everything below is **uncommitted**
in this worktree; existing unrelated work is untouched.

## Short version

**Batch 3b's engineering is done and verified — real rendered floor,
product-only matte from a second floor-hidden render, two-frame Modal probe
passed (run3), 211 tests. Mark then reviewed the look and rejected the floor
*appearance*: the rendered plane doesn't blend with the HDRI backdrop at the
horizon, and the softbox reflects off the floor as a "spotlight" pool.
Decision made with Mark: replace the flat plane with a curved studio
cyclorama (infinity cove). The cyc geometry is the next session's task —
constraints below. The matte mechanism, gates, and timings all stand.**

## Read first, in order

1. This file.
2. `AGENTS.md` — environment facts (venv Python absolute path, suite command
   + `${PIPESTATUS[0]}` trap, Blender not on PATH, ffmpeg on PATH, `output/`
   gitignored evidence).
3. `docs/rl300-parity.md` — every standing owner ruling, verbatim. The biting
   ones: all rendering on Modal (USD 30/month ceiling; estimate in every
   `request.json`, measured seconds in `docs/cloud-smoke.md`, failures
   recorded too); material changes mean a new source `.blend` + acceptance
   round (never in manifests); "looks good" ≠ formal acceptance; no gate
   threshold widened without new numbers.

## Owner look review, 2026-09-21 — FIX-FIRST (the open item)

Mark annotated run3 az42 (`output/preview-studio-floor-3b-20260921-run3/cloud/
frame-az42/`): `composite-lens-markup1.png` (arrows at a "spotlight" light
pool on the floor right of the machine), `composite-prelens-markup2.png`
(white ellipse — "a shape that approximates the outline of the artifact"),
`composite-prelens-markup3.png` (image halves mirrored — backgrounds don't
match).

**Diagnosis (accepted by owner):** above the floor line, the visible backdrop
is the HDRI's own baked gradient (`env_studio-softbox.png` renders as world
environment, strength 2.0); the rendered floor plane doesn't match it at the
horizon seam. The softbox panel in that map reflects off the plane at grazing
angle = the pool. The mirror mismatch is partly the deliberately asymmetric
light rig (normal — it gives the metal its tonal range) and partly the seam
(defect). Run3's derived sizing guarantees frame-corner rays hit the plane,
but a finite plane + photographic backdrop can never blend at the horizon.

**Owner decision: Option B — curved studio cyclorama (infinity cove).**
(A bigger flat plane was rejected: horizon tonal mismatch can persist, GI
brightens, fragile for orbit.)

## Next task: the cyclorama — constraints, not suggestions

1. **Geometry**: revolved cyc profile around the product ground center
   (`_visible_product_ground`): flat disc under/around the machine, tangent
   arc curving up into a vertical wall. Rotationally symmetric (orbit-safe).
   Replaces the plane in `build_studio_floor` for floor mode; keep
   `FLOOR_OBJECT_NAME` and the direct-reference contract — the matte render
   hides the cyc by that same reference (`render_floor_hidden_matte`).
2. **Sizing**: adapt the existing analytic camera-corner logic. Below-horizon
   rays bound the floor radius (reuse `required_floor_half_extent`);
   above-horizon rays now hit the WALL, so `FLOOR_HORIZON_IN_FRAME` is
   replaced by a derived wall height: top-of-frame ray + margin + DOF blur
   must intersect the wall. Derive it from camera geometry — no arbitrary
   multiplier. Keep the axial-depth clip semantics (`dot(hit-origin,
   forward)` vs `clip_end`, never raw `t`), scale-invariance, and the
   `view_layer.update()` before `matrix_world` (run2's lesson).
3. **Material**: same neutral floor material family. A roughness bump (≈0.7)
   is the sanctioned knob to soften the softbox pool on the curve — decide
   from the probe, don't pre-tune. Render-time environment geometry: NOT a
   source-`.blend` change, no acceptance round; never touch product materials.
4. **Lighting risk — measure it**: the wall ring occludes low-angle HDRI
   light; machine luminance may shift vs run3. Keep the wall only as high as
   the derived minimum, and have the probe compare product-pixel luminance
   vs run3, recording the delta.
5. **Gates unchanged**: full-scene saved-bytes gate, product-only metrics,
   matte plausibility (~0.41 expected; cyc hidden in matte pass), sequence
   gates, thresholds — none move.
6. **Tests**: keep all 211 green; new cyc tests mirror the floor-geometry
   ones (fake camera, scale invariance, wall-height derivation, matte hides
   cyc). The `FLOOR_HORIZON_IN_FRAME` test changes semantics (wall covers
   above-horizon rays now).
7. **Process**: delegate implementation (GLM-5.3-Flash), adversarial review
   (DeepSeek-Flash, fresh context, diff + spec only, bounded reads) via ocx
   before dispatch; parent runs the suite and all measurements. Then ONE
   2-frame probe: `./.venv/Scripts/python.exe scripts/cloud_job_render.py
   --manifest jobs/rl300_05_studio-floor.json --azimuths 42,222 --output-dir
   output/preview-studio-floor-3c-<date> --execute` + `probe_sequence.py
   --run-dir <dir> --expect-frames 2 --no-encode`. Estimate ≈ USD 0.20;
   record measured seconds + a vision read (pool, seam, mirror test,
   luminance delta) in `docs/cloud-smoke.md`. Mark's look gates anything
   bigger.

## What ran (evidence, not memory)

Full attempt record and run3 measurements: `docs/cloud-smoke.md`
"2026-09-21 batch-3b FINAL".

- **Run1** (`output/preview-studio-floor-3b-20260921-run1/`): passed,
  wall 279.1 s, 266.356 container-s, but both lensed composites showed the
  finite floor's far diagonal edge against the dark world (FIX-FIRST).
- **Run2** (`...-run2/`): failed on az42, `BLENDER_FAILED_OR_NO_OUTPUT
  exit=20`, 3.417 container-s. Cause: camera projection ran before the
  depsgraph update, so `camera.matrix_world` was stale. Fixed.
- **Run3** (`...-run3/`): passed, wall 270.175 s, 246.882 container-s.
  Warm az222: beauty 8.38 s + matte 2.63 s; **RENDER phase 11.27 s vs the
  10.2 s batch-1 warm baseline = +10.5%, inside the declared +10-30% band**
  (render phase vs render baseline; frame totals are a distinct number and
  are not compared against the baseline). az42 paid the cold OptiX compile
  (beauty 222.69 s, frame total 228.50 s).
- **Cost, all attempts included, RATE-DERIVED NOT BILLED** (recorded all-in
  USD 0.00030992/s; no invoice queried): 516.655 container-s total ≈
  **USD 0.160**. Per-dispatch estimate was USD 0.197 in each `request.json`.
- Gates (run3): pre-lens RGB byte-exact vs full beauty, mask vs the
  independently rendered matte alpha, matte plausibility 41.28/41.32%
  coverage (ceiling 0.90 unfired), synthetic shadow suppressed (0.35
  configured, 0.0 effective), lens after gates, sequence gates pass in
  `rendered_floor` mode, grain deterministic. **No encode was run — a
  2-frame probe supports no full-orbit claim.**
- Model routing proven from `output/batch3b-routing-evidence.json` (196 ocx
  rows: 153 glm-5.3-flash, 24 glm-5.3, 43 deepseek-flash). No model spend
  figure is asserted.

## Mask IoU correction (supersedes the earlier "unmeasured" claim)

The 0.966 (az42) / 0.800 (az222) numbers ARE raw-mask IoU measurements
against the raw batch-2 masks at the matching azimuths — earlier text calling
them "shifted composites, raw IoU unmeasured" was wrong. They are
**incomparable by definition, not a defect**: batch-2 masks include the
shadow-catcher contact shadow; floor-mode masks are product-only. The floor
mask is a strict subset of the batch-2 mask (zero product pixels missing in
both). Reproduced independently in
`output/batch3b-evidence-review-deepseek.txt`; camera blocks are identical,
so framing is not the cause.

## Batch-3b machinery (landed, keep intact through the cyc work)

- **Matte mechanism** (`render_worker.py`): cutout from a second
  floor-hidden transparent render (`beauty-matte.png`; seed pinned, denoise
  off, state restored in `finally`) — never from the opaque beauty's alpha.
  `write_matte_pass(output_dir, source_filename=…)`.
- **Floor mode**: `lighting.floor.enabled=true` + `output.film_transparent=false`,
  both defaulted (every existing job/accepted hash untouched). Floor created
  after the ground-keyword hide pass AND after the photoreal pass; catcher
  suppressed; `alpha_mask=false` rejected pre-dispatch.
  `render_worker.validate_output_config` is self-contained (Modal pickles by
  reference — the container sees only `render_worker.py`); it is mirrored by
  `composite_worker.validate_floor_config` (shared authority for
  dispatcher/probe/CLI); a test pins their error codes together.
- **Full-scene finishing** (`composite_worker.composite_rendered_floor_asset`):
  saved-bytes RGB equality vs full beauty; product metrics on `mask==255`;
  mask-vs-matte-alpha consistency (labeled: proves mask-vs-matte agreement,
  NOT stochastic beauty-silhouette alignment); synthetic shadow suppressed
  with configured-vs-effective reported; lens exactly once after gates.
  Legacy `composite_asset` untouched.
- **Dispatcher/probe**: estimate counts both passes per frame
  (`render_passes_per_frame: 2`); mode-routed finishing; sequence report
  declares `composite_mode`. New job: `jobs/rl300_05_studio-floor.json`
  (batch-2 look: DOF f/3.2, lens .45/.3/2.2).
- Tests: `tests/test_floor_mode.py`, `tests/test_cost_and_lens_fixes.py`.

## Working tree — read before committing

- Batch-3b files (uncommitted, verified): `render_worker.py`,
  `composite_worker.py`, `scripts/cloud_job_render.py`,
  `scripts/probe_sequence.py`, `msp_render_cli/{cli,manifest,remote_job}.py`,
  `docs/job_manifest.schema.json`, `docs/remote_job_result.schema.json`,
  `docs/cloud-smoke.md`, `docs/video-pipeline-brief.md`,
  `jobs/rl300_05_studio-floor.json`, `tests/test_floor_mode.py`,
  `tests/test_cost_and_lens_fixes.py`, `tests/test_remote_job.py`, this file.
- **NOT part of this work, pre-existing dirty — never sweep into a batch-3b
  commit**: `AGENTS.md` (one-line mod), `.zcodeignore`,
  `docs/agent-tooling.md`.
- `.test_deps/` (~100 MB, repo root): created against instruction by a prior
  agent, permission-inaccessible. **Do not delete it or change its ACL.**
- **Commit discipline**: explicit `git add <file>…` per file group, never
  `-A`/`.`. Recommended sequencing: commit the verified batch-3b engineering
  NOW as its own commit (the owner look feedback is already recorded in
  `docs/cloud-smoke.md`, so the message can be honest), then the cyc lands
  as a second commit after its probe. Push after Mark accepts the cyc look.

## Exact next actions

1. Commit the verified batch-3b engineering (explicit paths; message states
   owner look FIX-FIRST and points here).
2. Implement the cyc per the constraints above (delegate → adversarial
   review → parent gates the diff).
3. Two-frame probe → Mark's look review (same markup exercise if he wants).
4. On acceptance: push, then batch 4 (owner-gated imperfections) or the
   T-V2 sequencer (300-frame orbit; 3a's orbit/frame-count prerequisites are
   landed).

## Standing constraints (unchanged)

- All rendering on Modal, never local (2026-09-20 ruling); USD 30/month
  ceiling; estimates in `request.json`, measured seconds in
  `docs/cloud-smoke.md`; `cloud_authorized` stays hardcoded false.
- No threshold widened without new numbers; "looks good" is not owner
  acceptance; material changes need a new source `.blend` + acceptance round.
- Single upstream `origin`; the `main` worktree at
  `C:/Projects/msp-render-pipeline` has none of this branch.
- Python: `./.venv/Scripts/python.exe`. Blender not on PATH; local renders
  banned; ffmpeg 8.1.1 on PATH. `output/` is gitignored — read run records.

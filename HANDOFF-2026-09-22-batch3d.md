# Handoff — 2026-09-22 (batch 3d: cove is IN frame, all structural gates green; az42 band gate FAILS as declared — the fix left is the env round)

Worktree: `C:/Projects/msp-render-pipeline-scene-prep`, branch
`codex/studiomark-scene-prep` (single upstream GitHub `origin`). Supersedes
`HANDOFF-2026-09-21-batch3c.md`. Suite **233 tests OK, exit 0** (venv).
Commit `d598cea` — **LOCAL ONLY**, like `b3b46a9`+`3f2351d`+`42ad974`: push
waits for Mark's words on the whole batch-3 chain.

## Short version

Mark's 09-22 look ruling: 3c az222 good, az42 rejected ("identical to 3b").
Measured: 3c was a visual no-op — its derivation buried the cove outside the
frame (fillet at 55.65 m; frame-top rays land ~56 m). Batch 3d re-targets the
derivation: disc sized just past the product, fillet+arc carry the backdrop,
cove line lands at row 0.323 INSIDE the frame (declared band 0.25-0.45).
One 2-frame Modal probe (USD 0.087 measured rate-derived): every structural
gate green, warm render +18.0% (in band), product luminance +0.74/+1.91%,
derivation log matches preflight field-for-field. **The declared
background-band gate FAILED on az42 exactly as designed to fail: 2.1536 >
1.8** — the az42 two-tone persists because the env lights the arc dark on
that side (the spec's declared §7 fallback: next mechanism is the ENV
horizon-band round, an asset round under ruling 2). No encode, no full-orbit
claim, no batch-4 work until Mark's explicit words.

## Read first, in order

1. This file.
2. `AGENTS.md` — environment facts (venv Python absolute path,
   `${PIPESTATUS[0]}` trap, Blender not on PATH, local renders banned,
   ffmpeg on PATH, `output/` gitignored evidence).
3. `docs/rl300-parity.md` — standing owner rulings, verbatim.
4. `docs/cloud-smoke.md` "2026-09-22 batch-3d" — the measured run record.

## What to review (Mark)

Frame dirs: `output/preview-studio-floor-3d-20260922/cloud/frame-az42/` and
`.../frame-az222/` — `composite-lens.png` (shipped look),
`composite-prelens.png` (pre-lens), `composite-prelens-mirror-check.png`
(your markup3 exercise). Compare az42 against 3c's
(`output/preview-studio-floor-3c-20260921/...`): the upper background is now
the cyc arc (subtle gradient, row 0.323 cove line) instead of a flat void —
but it renders DARK on that side, so the bright-pool / dark-backdrop step at
row 553 remains (gate: 2.15 vs 3c's 2.06).

**The decision that is yours:**
- **Env round next (recommended):** soften/lift the softbox env's
  horizon-band structure so the arc's upper region isn't dark at az42-type
  azimuths. Asset round under ruling 2 (new env generation + acceptance);
  the geometry now in place is the foundation and stays.
- **Or accept az42 as-is** (your eye, your call — the step is now
  "dim studio wall behind lit floor", not "spotlight in a void"; the gate
  says it is still above the declared defect line).
- Either way: on final acceptance of the chain, push the 4 local commits.

## What the next agent must know

- `render_worker.py`: `required_floor_radius` is DELETED;
  `required_cove_profile` is the derivation (spec §3.1, 9 steps); dense
  top-edge scan via `_camera_top_edge_rays` (65 samples); `required_wall_height`
  takes `floor_radius` and covers below-horizon rays that miss the disc;
  assertions `COVE_RAY_ESCAPE` / `COVE_TANGENT_OUT_OF_BAND` /
  `COVE_AXIS_AIM_DIVERGENT` / `COVE_PERSP_REQUIRED` /
  `COVE_FILLET_CLAMP_INVALID` / `COVE_FLOOR_UNDER_PRODUCT`; `legacy_min`
  retired. `wall skipped` in the log is the NORMAL regime (rim = arc top).
- **`view_frame()` shapes the frustum from the scene resolution** — any
  preflight MUST set `scene.render.resolution_{x,y}` (+ percentage) from the
  manifest before camera/frustum work. This caused the 3c 52.19-vs-58.94
  divergence. The run-side `Cove derivation:` log line now makes any
  preflight-vs-Modal mismatch visible without a render.
- Probe gate: `measure_background_step` (probe_sequence.py) on
  **composite-prelens.png**, threshold 1.8/255/row declared 2026-09-22,
  provenance 2.0623 (az42 defect) / 0.6891 (az222 approved) measured with the
  same function. Do not widen without new numbers + owner words.
- Delegation state this session: glm-5.3 (codex slug normalized the
  `-flash` away — upward substitution, reported) 429'd mid-task with nothing
  landed; deepseek-flash landed the implementation but both later deepseek
  seats 429'd (provider saturated ~20:00-21:00 local); the implementation
  review re-routed to glm/zai. Verify seat claims with your own suite run —
  one seat claimed completion with an EMPTY diff.

## Standing constraints (unchanged)

- All rendering on Modal, never local (2026-09-20 ruling); USD 30/month
  ceiling; estimates before dispatch, measured seconds after;
  `cloud_authorized` stays hardcoded false.
- No threshold widened without new numbers; "looks good" is not owner
  acceptance; material/asset changes need a new source asset + acceptance
  round (the env round, if Mark picks it, is exactly this).
- Single upstream `origin`; the `main` worktree at
  `C:/Projects/msp-render-pipeline` has none of this branch.
- Python: `./.venv/Scripts/python.exe`. Blender at
  `C:/Program Files/Blender Foundation/Blender 5.1/blender.exe`. ffmpeg on
  PATH. `output/` is gitignored — read run records. `.test_deps/` (~100 MB,
  permission-inaccessible): do not delete, do not touch ACL. Explicit
  `git add <file>…`, never `-A`. Deliberate dirty tree (never sweep in):
  `AGENTS.md`, `.zcodeignore`, `docs/agent-tooling.md`.

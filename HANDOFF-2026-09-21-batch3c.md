# Handoff — 2026-09-21 (batch 3c: cyclorama landed, 2-frame probe passed — owner look is THE gate)

Worktree: `C:/Projects/msp-render-pipeline-scene-prep`, branch
`codex/studiomark-scene-prep` (single upstream GitHub `origin`). Supersedes
`HANDOFF-2026-09-21-batch3b.md`. Suite **220 tests OK, exit 0** (venv
interpreter). Both batch-3b engineering (`b3b46a9`) and the cyclorama
(`3f2351d`) are **committed locally — NOT pushed**: push waits for Mark's
acceptance of the cyc look.

## Short version

**The owner's Option B is implemented and probed.** The flat floor plane is
replaced by a rotationally symmetric studio cyclorama (disc + tangent fillet
+ wall), sized per frame from the real camera's corner rays. One 2-frame
Modal probe (az 42/222) passed every gate: warm render +17.5% vs the 10.2 s
batch-1 baseline (inside the declared +10–30% band), sequence gates pass,
matte plausibility 41.28/41.32%, mask==matte-alpha 100%, product luminance
delta vs run3 +0.15%/+0.26% (wall light-occlusion measured negligible).
Vision read: no plane edge, no hard seam, pool softened to a broad falloff,
mirrored-halves test continuous across the seam. **Mark's look review on the
3c frames is the only open gate** — run records in
`docs/cloud-smoke.md` ("2026-09-21 batch-3c").

## Read first, in order

1. This file.
2. `AGENTS.md` — environment facts (venv Python absolute path,
   `${PIPESTATUS[0]}` trap, Blender not on PATH, local renders banned,
   ffmpeg on PATH, `output/` gitignored evidence).
3. `docs/rl300-parity.md` — standing owner rulings, verbatim.

## What to review (Mark)

Frame dirs: `output/preview-studio-floor-3c-20260921/cloud/frame-az42/` and
`.../frame-az222/` — `composite-lens.png` (graded final) and
`composite-prelens.png` (pre-lens). The batch-3b markup exercises are
pre-staged per frame: `composite-prelens-mirror-check.png` (the markup3
mirrored-halves test). Compare against the run3 markups in
`output/preview-studio-floor-3b-20260921-run3/cloud/frame-az42/`:
the "spotlight" pool (markup1/2) and the floor/backdrop seam (markup3) were
the rejected defects.

- On acceptance: push both commits, then batch 4 (owner-gated imperfections)
  or the T-V2 sequencer (~USD 1.30/300 frames; 3a prerequisites landed).
- On rejection: annotate as before; the sizing knobs are all derived — any
  change (fillet size, roughness) is a new spec round, never a manifest hack
  (ruling 2 discipline).

## How the cyc was built (for the next agent)

- Spec → GLM-5.3-Flash (ocx, proven) → DeepSeek-Flash fresh-context
  adversarial review (FIX-FIRST, all findings fixed) → parent gate →
  preflight derivation in headless Blender (NO render,
  `output/batch3c-preflight-derive.py`) → ONE probe. Spec chain:
  `output/batch3c-cyc-spec.md` + `batch3c-cyc-amendment1.md` +
  `batch3c-cyc-amendment2.md`; review verdict
  `output/batch3c-cyc-review-deepseek.txt`; diff `output/batch3c-cyc-diff.patch`
  (as of first review).
- Geometry: `required_floor_radius` (below-horizon corner hits, EUCLIDEAN
  radial metric — not the old Chebyshev) then `required_wall_height` against
  the FINISHED wall cylinder (ordering load-bearing). `FLOOR_HORIZON_IN_FRAME`
  retired; new codes `CYC_WALL_UNREACHABLE`, `CYC_CAMERA_OUTSIDE`,
  `CYC_MESH_INVALID` (validate() True = corrected = loud refusal). Roughness
  0.7 = the owner-sanctioned knob. Fillet = max(2·product_radius, 0.5) —
  shape constant, not a margin.
- **Production fact: 0/4 corner rays are above horizon at the probe camera**
  (85 mm, 11° elevation) → wall ring is correctly SKIPPED (amendment 1's
  degenerate-ring fix is load-bearing; a straight-down real-Blender smoke
  test pins it). Probe derivation: disc r=52.19 m, fillet 3.29 m, wall top
  z=3.29 m (above frame top — no visible edge).
- Matte mechanism, gates, dispatcher, schemas: untouched. `render_worker.py`
  + `tests/test_floor_mode.py` are the only code changes.

## Measured (3c probe, all RATE-DERIVED NOT BILLED)

Estimate USD 0.197/dispatch in `request.json`; 296.874 container-s ≈ USD
0.092 (rate 0.00030992/s, no invoice queried). az42 cold: beauty 275.70 s,
container 282.929 s (OptiX compile). az222 warm: beauty 8.97 s + matte
2.73 s, RENDER phase 11.99 s = **+17.5% vs the 10.2 s batch-1 baseline**
(band +10–30%), +6.4% vs run3's plane. Modal app ap-BF5WG9POgmERjJOyPNHtC0.
**No encode was run — no full-orbit claim is supported.**

## Working tree / commit state

- Committed: `b3b46a9` (batch-3b engineering), `3f2351d` (cyclorama).
- Deliberately uncommitted (pre-existing dirty, never sweep in): `AGENTS.md`
  (one-line mod), `.zcodeignore`, `docs/agent-tooling.md`.
- `.test_deps/` (~100 MB, permission-inaccessible): do not delete, do not
  touch ACL.
- Commit discipline: explicit `git add <file>…`, never `-A`/`.`.

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

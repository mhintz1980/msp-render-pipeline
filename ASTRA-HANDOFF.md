# Handoff to Astra — 2026-09-10

Written by Claude (Opus 5) while Astra was out of quota. Branch
`codex/studiomark-scene-prep`. Scope was deliberately limited to unblocking T03;
everything requiring judgment was left alone. Read "What I did not touch" before
resuming.

## TL;DR

T03 is unblocked. `parity-20260910-v3` reports `awaiting_reference_acceptance`
with zero failures. The blocker was a one-line ordering bug in
`render_worker.write_matte_pass`. Your work is committed and safe. Two design
questions are queued for you at the bottom.

## State when I arrived

Your T01–T03 work was **uncommitted** — 10 files, 1447 insertions, part staged
and part untracked, in a worktree whose stash stack is shared with other
sessions. I committed it unchanged as `bd9b0cd` before touching anything, so the
diff of my own work is reviewable in isolation against it.

The parity verifier was blocked:

| Run | Status |
|---|---|
| `parity-20260910-v1` | `awaiting_reference_acceptance`, `failures: []` |
| `parity-20260910-v2` | `blocked` — `MASK_ALPHA_MISMATCH` ×4 |

## What was actually wrong

v1 and v2 have the same `prepared_sha256`, the same `source_sha256`, and
**pixel-identical artifacts**. I compared them directly. Nothing regressed
between the runs — v1 was measured before the mask/alpha check existed.

**Treat v1's pass as stale and do not cite it.** Per Mark's instruction the v1
evidence directory is untouched; the caveat lives in `docs/rl300-parity.md` and
here.

v2's verdict was correct. Every `mask.png` in both runs is solid black: one
unique value across all 562,500 px, while the beauty alpha has 49 distinct
values and 39.75% coverage.

Root cause, reproduced in isolation on Blender 5.1.1 (probe: four PNGs differing
only in ordering; only the current ordering came back blank):

> `write_matte_pass` assigned `matte.colorspace_settings.name` **after** writing
> `matte.pixels`. Assigning a colorspace to a *generated* image
> (`bpy.data.images.new`) frees and regenerates its buffer from
> `generated_color` — opaque black. The matte was discarded before `save()`.

The read side was never at fault. `img.pixels[3::4]` on the loaded beauty PNG
returns the correct alpha; I verified that first and it matched the expected
coverage exactly.

## Why no gate caught it

`image_metrics()` in `scripts/verify_scene.py` derives silhouette, coverage and
interior masks from **`beauty.png`'s alpha channel**. `mask.png` feeds no
numerical gate at all — not IoU, not coverage-delta, not the "≥1% visible
coverage" floor. Your late-added consistency check is the only thing in the
system that has ever read `mask.png`. That is why a blank mask survived a
complete five-mode verification run.

## Changes I made

All in one commit, separate from yours.

- `render_worker.py` — colorspace set before the pixel write; `_read_alpha` /
  `_write_grey` use `foreach_get`/`foreach_set` into numpy instead of
  `list(img.pixels)` plus a Python loop over 2.25M floats (9M at the 1800×1250
  reference), with a pure-Python fallback if numpy is unavailable;
  `_assert_matte_matches` re-reads the saved matte and raises
  `MATTE_DEGENERATE` / `MATTE_ALPHA_MISMATCH`.
- **Behaviour change worth knowing:** the blanket `except Exception` that
  printed `"matte pass skipped"` and continued is gone. A bad matte now fails
  the render job. `beauty.png` is already on disk at that point, so nothing is
  lost, but a job that used to complete with a silently broken mask will now
  return non-zero. That was the whole failure mode, so I made it loud — revert
  it if you disagree.
- `tests/test_matte_pass.py` — six tests. One drives the real `write_matte_pass`
  inside Blender against a synthetic RGBA plate and asserts byte agreement with
  the alpha; it skips cleanly when Blender is absent (`MSP_BLENDER_BIN`
  overrides the search). Five pure-Python tests pin the verifier's tolerance
  behaviour so the gate cannot be loosened back open.
- `docs/rl300-parity.md` — run record for v1/v2/v3, the root cause, the
  `mask.png`-carries-no-gate-weight finding, and two setup facts that cost me
  time: the suite needs `jsonschema` from `requirements-test.txt` in the
  worktree `.venv` (bare `python` fails to import), and the verifier must run
  from **PowerShell** — Git Bash rewrites the leading `/home/...` in
  `--linux-runtime` into a Windows path and the runtime hash check fails before
  any render starts.

## Verification

- `python -m unittest discover -s tests` — **44/44 pass** (your 38 + my 6).
- `parity-20260910-v3` — `awaiting_reference_acceptance`, `failures: []`.
  - All four rendered modes: `mask.png` vs beauty alpha **max byte diff 0**, 49
    distinct values, coverage matching exactly.
  - `repeat` bit-exact vs reference: IoU 1.0, RGB MAE 0.0, P99 0.0.
  - `camera_shift` fails as designed — `SILHOUETTE_MISMATCH` + `RGB_MISMATCH`,
    IoU 0.735, coverage delta 0.018.
  - `material_change` fails as designed — `RGB_MISMATCH` only, IoU 1.0,
    coverage delta 0.0.
  - `missing_texture` blocks pre-render on `MISSING_DEPENDENCY: world_environment`.
  - `source_to_prepared`: zero structural differences.
- `g0_passed`, `owner_accepted`, `cloud_authorized` all remain **false**. I did
  not advance any gate.

I verified the masks independently with PIL rather than trusting the report.

## Ground shadow — Mark's finding, fixed (2026-09-11)

Mark reported that every render through Modal and Blender leaves the machine
floating. Confirmed, measured, and fixed at his go-ahead.

**It was configuration, not lighting.** All four job manifests carried
`"shadow_catcher": false`, and `render_worker` doesn't merely skip the catcher
when that is off — it deletes any `GroundShadowCatcher` in the scene, commented
"to ensure clean transparent alpha". Nothing in the scene could receive a
contact shadow. Measured on the v3 reference beauty pass: partial alpha was
**0.61%** (3,407 px) with its bounding box within 2 px of the opaque bounding
box — pure edge antialiasing, no shadow footprint at all. The dark gradient
under the skid is painted into `env_studio-dark.png`; it was never the machine's
shadow.

Geometry was already correct for it: scene Z bounds are **0.0000 .. 2.1074**
with zero objects below Z=0, so the plane the code adds at `location=(0,0,0)`
lands flush under the skid. No repositioning needed.

**Flipping the flag alone was not enough.** The catcher is built at
`size = radius * 14` with `data.materials.clear()`, which leaves Blender's
default ~0.8 grey diffuse — a bounce card larger than the machine, aimed
straight up at it. A shadow catcher still participates in indirect light, so
the product got flooded:

| RL300 studio-dark, machine pixels only | mean R | mean G | mean B | shadow footprint |
|---|---|---|---|---|
| before (`shadow_catcher: false`) | 179.61 | 149.90 | 93.44 | 0.33% |
| flag flipped, bounce live | 194.73 | 168.87 | 124.30 | 22.79% |
| flag flipped + bounce muted | 179.03 | 149.31 | 92.35 | 26.47% |

Blue lifted +31 in the middle row — the yellow went pale and the black chassis
frame lifted to grey, across 87% of product pixels (mean luminance +19, p95
+52).

**Fix:** `mute_catcher_bounce()` clears `visible_diffuse` / `visible_glossy` /
`visible_transmission` / `visible_volume_scatter` on the catcher (with the
pre-3.0 `cycles_visibility` fallback). The shadow is a camera-ray effect on the
catcher itself and survives; the plane leaves every indirect bounce path.
Applied at both catcher construction sites. Result is the bottom row: product
colour restored to within **0.76 mean absolute channel levels** of the original
(99.9th percentile 6), with a stronger shadow than the bouncing version.

Only `jobs/rl300_02_studio-dark.json` was flipped. `rl300_01_no-background`,
`rl300_03_excavation-pit` and `jgun_01_no-background` are still `false` and
untouched — worth a look, since the no-background jobs may want it off by
design while `excavation_pit` almost certainly does not.

A/B artifacts: `output/shadow-ab/{before,after,after-nobounce}/` (git-ignored).

**This invalidates the v3 parity baseline.** The prepared payload manifest at
`parity-20260910-v3/payload/manifest.json` has `shadow_catcher: false` baked in,
and a shadow catcher writes its shadow into the **alpha channel** on transparent
film — partial alpha goes 0.33% → 26.47%, which moves coverage, IoU and
`mask.png`. Re-baselining means regenerating the payload through
`prepare_scene.py` from the updated job, which changes `prepared_sha256` and the
whole evidence chain. That is your T01/T02 call, so I left it. Mark has not
accepted any reference.

## What I did not touch

Deliberately left for you:

- **The `mask.png` design question** (below) — architecture, your call.
- Anything in `jgun-portfolio`. Its RL300 "Quiet Machine" plan is still
  `Status: proposed; awaiting Mark's approval`, and its tree confirms no
  implementation has started. I read the plan and left it alone.
- Any Blender model geometry, render settings, thresholds, or the
  `proposed_pending_owner` profile.
- T04 / cloud parity, T05 compositor hardening.
- The v1 and v2 evidence directories — unmodified, per Mark.

## Queued for your decision

1. **`mask.png` is a third, ungated copy of the silhouette.** Promote it to the
   authoritative input for the IoU/coverage gates, or drop it from the payload
   entirely. Leaving it as a passenger is how this shipped blank. I did not
   change the gate topology because that is a contract change.
2. **Should a failed matte fail the render job?** I made it raise. The
   alternative is to write a `matte_status` field into the report and let the
   verifier adjudicate, which keeps render jobs completing but requires the
   verifier to check it.

3. **Do the other three jobs want a ground shadow?** Only studio-dark was
   flipped. The two `no-background` jobs may want it off deliberately (a
   transparent cut-out with a shadow in its alpha is not always wanted);
   `rl300_03_excavation-pit` almost certainly wants it on.

## Next atomic step

**Not** the v3 reference — it is superseded. It was rendered with
`shadow_catcher: false` and freezing it would make the floating machine the
target that cloud parity has to reproduce.

Regenerate the prepared payload from the updated studio-dark job, re-run the
verifier, and put *that* composite in front of Mark. Then he accepts or rejects
a reference that is actually grounded.

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

## Next atomic step

Mark compares `parity-20260910-v3/reference/composite.png` against the intended
existing RL300 studio-dark image and accepts (or rejects) the reference hash.
Nothing downstream of that — profile acceptance, G0, T04 — can move first.

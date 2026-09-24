# Handoff — 2026-09-24 (batch 3h: **the shipped rig fails the 30-azimuth orbit at az42 and az318; `pool_soft` and Rim-off clear the orbit metric; the transition is spread, not removed**)

Worktree: `C:/Projects/msp-render-pipeline-scene-prep`; branch
`codex/studiomark-scene-prep`. The round commit is **`e835c7f`** ("Batch 3h:
opt-in lighting.rim_profile …"); the branch is **10 local commits ahead of its
`origin/codex/studiomark-scene-prep` upstream** after it, and **the push waits
for Mark's words**. This supersedes `HANDOFF-2026-09-23-batch3g.md`.

Suite evidence, exactly as architect-run on the project venv:
`Ran 103 tests ... OK` for `./.venv/Scripts/python.exe -m unittest discover -s tests -p test_floor_mode.py`,
plus `22 + 6 + 8 + 7` OK across four adjacent files. No full-suite run was
made this round; any full-suite total is arithmetic, not a measurement.
Arithmetic total, labelled as arithmetic and never measured: this round added
18 tests to `tests/test_floor_mode.py` (85 → 103) on top of 3e's last measured
full-suite count of 239, so the arithmetic full-suite total is **264** — the
suite contains local render stubs and local renders are banned, so the total
is not a measurement.

## Short version

3h asked whether a Rim-targeted candidate clears the shipped 1.8 pre-lens gate
across the 30-azimuth orbit and what the owner would be choosing visually. It
measured REF (`pool_v1`, no override), SOFT
(`lighting.rim_profile=pool_soft`), OFF (`lighting.rim_enabled=false`), and
the REF2 A/A control. **REF fails at az42 and az318.** SOFT and OFF report no
problems at all 30 azimuths. SOFT **spreads** the transition: the pool-edge
step falls and the product proxies barely move, while `excursion`—the total
tonal span—is preserved. This is a candidate, not a fix claim and not
acceptance. The look call is Mark's.

## Read first

`AGENTS.md` and `docs/rl300-parity.md` for environment facts and standing
rulings; `output/batch3h-smoke-section.md` is the working copy of the
cloud-smoke section — the section itself is already appended verbatim to the
end of `docs/cloud-smoke.md`, committed in `e835c7f` and corrected in
`737e2c2` (the correction fixed that section's false "no test changed by
this round" footer), so the public record is published and needs no further
work; `output/batch3h-rim-fix-results.md` for the measured record;
`output/batch3h-rim-fix-probe-contract.md` for the frozen contract and its
pre-dispatch/post-dispatch addenda; `output/batch3h-impl-review-glm.md` and
`output/batch3h-fix-review-glm.md` for FIX-FIRST and the SHIP-TO-MODAL
re-review.

## The measured numbers

All gate numbers are `composite-prelens.png`, unchanged threshold 1.8. REF:
az42 `1.9744644165039062` @552 and az318 `1.9848175048828125` @553 FAIL;
the surrounding band is az330 `1.453765869140625` @530, az390
`1.4332199096679688` @530, az54 `1.2382965087890625` @588, and az306
`1.2236480712890625` @589. Nothing else in REF exceeds `0.87` (the next-highest are az354 `0.8620681762695312` and az366 `0.8615493774414062`, both at row 3). REF2
reproduces both REF crossings bit-exactly and is `failed` on that evidence.
SOFT is problem-free (worst az330 `0.8840484619140625` @3; az42
`0.7965774536132812`, az318 `0.8486175537109375`, az222
`0.8014755249023438`). OFF is problem-free (worst az90
`0.968292236328125` @1031; az42 `0.7167434692382812`, az222
`0.8149948120117188`).

At az42, SOFT moves the peak step off the pool edge (row 552 → row 3):
`smoothed_step` falls `1.596638149685333 → 0.5177680121527573`; the
per-column ramp at x=1600 falls `+3.9999923706054688 → +1.8860015869140625`,
and at x=1750 `+3.587005615234375 → +2`. But
`excursion` does **not** fall: `86.90695190429688 → 86.91739654541016`.
Az222 remains near its prior numbers
(`0.7901153564453125 → 0.8014755249023438`; excursion
`92.66735076904297 → 92.66834259033203`). Product proxies barely move: mean
luma az42 `133.24659729003906 → 133.22203063964844`; az222
`106.41605377197266 → 106.18280792236328`; az42 coverage
`0.412808 → 0.4128071111111111` and p95 luma
`182.4980010986328` on both sides.

Cost is four dispatches, not three. Each `request.json` recorded the same
pre-dispatch **estimate** `USD 1.9612` (`7.8448` total, conservative by
construction). Measured `result-az*.json:seconds` sums are REF `647.165`,
SOFT `646.300`, OFF `540.185`, REF2 `564.364`, total `2398.014` s.
At `0.00030992` USD/s this is **RATE-DERIVED** USD
`0.2005693768 / 0.2003012960 / 0.1674141352 / 0.1749076909`, total
`0.7431924989`—**no invoice was queried**. The slow frame is container
position 1, not an azimuth: REF `257.763` s and SOFT `254.755` s on first
frame az42, while OFF took `180.671` s on first frame az90 and `12.972` s
on az42. Price one warm-up per container.

## The A/A control and what it settled

The contract's strong reproduction clause required byte-identical
`composite-prelens.png`; it **failed** at all four pairs—409 / 525 / 511 /
471 of 2,250,000 pixels differ, max channel delta 1, none above 2, with
byte-identical masks. The metric clause passed bit-exactly at REF az42/az222
and OFF az42/az222. The fourth dispatch (REF2) ran the same build with no
override: REF vs REF2 differ by `527` px (az42) and `471` px (az222), max
delta 1—more at az42 than the cross-build `409`, and the same order as the
cross-build `525`. Masks are byte-identical and the metrics are bit-exact at
all four reproduction pairs. The contract's post-dispatch addendum — written
after the frames existed, and by its own terms left to review and to Mark,
never silently applied — sets the rule: if two runs of ONE build differ by the
same handful of ±1-LSB pixels, the byte clause's premise of bit-determinism is
refuted by measurement and the metric clause is the licensed basis for reading
SOFT; if the A/A pair is bit-identical, the cross-build difference is real and
SOFT's look statement stays withheld. The measured same-build spread landed on
the first branch. The bytes still differ; no threshold moved. The adjudication
is reviewable and Mark may overrule it. It is not a look verdict.

## What to review (Mark)

Frames are under
`output/preview-studio-floor-3h-{ref,soft,off}-20260924/cloud/frame-az*/`.
In each frame directory: `composite-prelens.png` is the gate input,
`composite-lens.png` is the shipped look, and `mask.png` is the matte.
Review images are `output/batch3h-looksheet.png`,
`output/batch3h-looksheet-crops.png`, and
`output/batch3h-profile-az{42,318,222,90}.png`. Visual read: REF has a hard
right-background pool-edge line; SOFT turns it into a wider, lower-contrast
falloff while the product reads much the same; OFF leaves the smooth background.

## Decisions that are Mark's

1. **Accept `pool_soft` as the Rig look.** Basis: 0/30 gate problems while
   `excursion` is preserved; acceptance would make the profile the job of
   record and is a separate, explicitly authorized change.
2. **Keep the shipped rig and accept az42/az318.** Basis: REF's measured two
   crossings and surrounding band; this is an owner look call, not a gate pass.
3. **Take the Rim-off null option.** Basis: 0/30 gate problems with the Rim
   absent.
4. **None of these.**

Attribution wording, stated once: **the ramp depends on the Rim given the other
lights and the v2 env** (Rim-off removes the ramp; Key-off worsens it; Fill-off
leaves it). **A Rim-only rig was never rendered, so "the Rim is the sole
origin" stays unmeasured.** The 3g handoff (its lines 25 and 104) licensed this
same measured fact as the Rim being *necessary*, while 3g's contract and this
round's record word it *sufficient given the other lights and the v2 env* —
two words for one measured fact, so a reader who finds either word is not
looking at a contradiction.

## Owner sign-offs still open

Carried unchanged from 3g/3e: LDR headroom (pre-clip in-band max `1.29997`;
`13,541` band pixels newly clipped), the half-azimuth-step bar (3g ratios
`0.529 / 0.676`), the v2 env's az~259/el~28.4 elevational edge (worst
smoothed gradient `18.96 → 33.19` byte/deg), any full-orbit claim, and owner
look acceptance.

## Next round — what a fresh session needs

- Implementation is default-absent: `lighting.rim_profile` in
  `render_worker.py`, `SCHEMA_OPTIONAL_OVERRIDE_PATHS` in
  `scripts/cloud_job_render.py`, the schema enum in
  `docs/job_manifest.schema.json`, and tests in `tests/test_floor_mode.py`.
- Dispatch recipe: `bash output/batch3h-dispatch.sh <ref|soft|off|ref2>` —
  30 azimuths at a 12° step are built in (`ORBIT=30` is hardcoded in the
  wrapper). For a non-default azimuth set:
  `bash output/batch3h-dispatch.sh <tag> "<comma list>"`. The form
  `scripts/cloud_job_render.py --orbit N` is the underlying dispatcher's own
  flag, not a wrapper argument. Override values are exactly
  `lighting.rim_profile=pool_soft` or
  `lighting.rim_enabled=false`; REF has no override. Measurement after a run:
  `./.venv/Scripts/python.exe scripts/probe_sequence.py --run-dir <dir>
  --expect-frames 30 --no-encode`.
- Methods live in `output/`: `batch3h-measure.py`,
  `batch3h-spread-vs-removed.py`, `batch3h-pixel-identity.py`,
  `batch3h-aa-control.py`, `batch3h-azcost.py` (the script behind the
  first-frame warm-up finding), and `batch3h-looksheet.py`.
- This round rendered only 30 of 360 frames on a 12° grid; it does not exclude
  a defect narrower than ~12°. No video or encode was produced.
- Carried open from 3g/3e, deferred hardening: (a) 3g review F1 — non-boolean
  `--set` values are still accepted and reinterpreted (`FALSE` → truthy
  string, `0`/`null` → silently off); the minimal fix is
  `if may_create and not isinstance(value, bool): raise ValueError(...)` in
  `apply_overrides`, plus an exact-boolean assertion in the dispatch path;
  (b) the two test-quality gaps — the 3f "only creatable path" test pins
  nothing new, and the absence-regression guard covers `key_enabled` only;
  (c) 3e's `ACCEPTED_OUTPUT` sha guard — refuse to overwrite
  `ACCEPTED_OUTPUT` in `scripts/build_studio_softbox_env.py` unless the
  existing sha matches.
- Optional attribution-closing run, still not dispatched: a Rim-only dispatch
  (Key off + Fill off + Rim on, via the existing `lighting.key_enabled` /
  `lighting.fill_enabled` controls) would upgrade the attribution claim
  above toward "the Rim is the sole origin"; ~USD 0.08 rate-derived as
  previously estimated. Worth it only if the stronger claim changes the look
  decision.

## What the next agent must know

- Worker/env SHA come from each run's `request.json`; never re-derive them by
  hashing the worktree—CRLF normalization gives a different digest.
- The dispatch guard machine-rejects anything but the exact allowed override;
  do not bypass it.
- A seat killed by harness infrastructure (exit 137) or a provider 429 is
  recovered with a completion spec naming surviving work and remaining work,
  not by redoing the paid work.
- `seatwrap` verify re-runs on Windows need `--verify-cmd` with backslashes,
  e.g. `.venv\Scripts\python.exe …`.
- Model attribution: `ocx logs --json`, filter by the seat's timestamp window
  and `requestedModel`, then read resolved `model`/`provider`.
- Pair-delegation protocol (owner instruction, carried from 3g): every
  implementation seat pairs with an adversarial reviewer from a different
  model family — never the same family on both seats; the reviewer gets the
  contract and the artifact only, and the architect re-runs every verification
  before dispatching a fix. This round was DeepSeek worker / GLM reviewer, so
  the next implementation task flips to GLM worker / DeepSeek reviewer.
- Concurrent webexport workstream files—untracked
  `scripts/*webexport*.py`, `.codex/`, `.zcodeignore`,
  `docs/agent-tooling.md`, and the modified `AGENTS.md`—are not this round:
  do not touch or commit them; commit explicit paths only.

## Standing constraints

`AGENTS.md` and `docs/rl300-parity.md` govern. Unchanged: Modal-only
rendering; USD 30/month ceiling; estimates before and measured seconds after
every dispatch, failures recorded too; `cloud_authorized` hardcoded false; no
threshold widened without new numbers; "looks good" is not acceptance. Ruling 2
covers source-material changes; the Rim profile is a renderer/look change
needing Mark's explicit look words. Single upstream `origin`; the separate
`main` checkout has none of this branch. Python is
`./.venv/Scripts/python.exe`; from Git Bash check `${PIPESTATUS[0]}`;
Blender is not on PATH; `output/` is gitignored evidence.

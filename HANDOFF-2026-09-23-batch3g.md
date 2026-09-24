# Handoff — 2026-09-23 (batch 3g: **removing the Rim alone clears the az42 ramp; the Fill is disproved**; the matched-build matrix retires 3f's build caveat and validates 3f's Key-off magnitude)

Worktree: `C:/Projects/msp-render-pipeline-scene-prep`, branch
`codex/studiomark-scene-prep`, **9 local commits ahead of `origin`** after this
round's commits (`3d4b6b5` is the round itself; the commit immediately after it
is this handoff's discipline correction — read both; push
waits for Mark's words). Supersedes
`HANDOFF-2026-09-23-batch3f.md`. No full-suite run this round (it contains
local render stubs; local renders are banned) — the last full number stands at
**239 tests OK** from 3e, and the targeted file
`-m unittest discover -s tests -p test_floor_mode.py` ran **85 tests OK**
(4.886 s) under the project venv, architect-verified. A full-suite run after
this round would be 246 by arithmetic (239 + 7 new); that number is arithmetic,
not a measurement.

## Short version

Batch 3g built two opt-in diagnostic controls (`lighting.fill_enabled`,
`lighting.rim_enabled`; GLM worker, DeepSeek adversarial implementation review
= SHIP-TO-MODAL), froze a pre-declared contract, and dispatched **three**
two-frame Modal runs on ONE worker build: a matched all-lights baseline, a
Fill-off, and a Rim-off. Result: **az42 Rim-off 0.7167434692382812 PASSES the
unchanged 1.8 gate** with the right-half excess collapsed; **Fill-off
1.9641952514648438 still FAILS**; the baseline reproduces 3e all-lights
**exactly** (1.9744644165039062, row 552). So **the Rim is necessary for the
az42 ramp under this rig** — with the Rim removed the ramp is gone and the gate
passes, which is the strongest statement the evidence licenses (sufficient
*given the other lights and the v2 env*; a Rim-only rig was never rendered, so
"the Rim is the sole origin" is not measured) — and the Fill is disproved as
the sole carrier. The Rim contributes essentially
nothing to the lit product appearance (product mean luma 133.07 vs 133.25),
which is what makes a Rim-targeted fix plausible without disturbing the
product. **This is a diagnostic, not owner acceptance**: no permanent rig
change, no threshold change, no asset version, no push. Next round: a
Rim-targeted fix — see "Next round — the Rim fix" below for the discipline that
actually applies (it is a renderer/look change; ruling 2's source-asset
versioning does **not** apply to the rig).

## Read first, in order

1. This file.
2. `AGENTS.md` — environment facts (venv Python absolute path,
   `${PIPESTATUS[0]}` trap, Blender not on PATH, local renders banned,
   `output/` gitignored evidence).
3. `docs/rl300-parity.md` — standing owner rulings, verbatim.
4. `docs/cloud-smoke.md` — the new "2026-09-23 batch-3g fill/rim isolation"
   section (appended, after the 3f section).
5. `output/batch3g-fill-rim-results.md` (measured results note, with the
   cross-family review-fix appendix) and `output/batch3g-records-review-deepseek.md`
   (the reviewer that returned FIX-FIRST) and
   `output/batch3g-controls-review-deepseek.md` (the control review).
6. `output/batch3g-fill-rim-probe-contract.md` — the frozen contract, its
   pre-declared rules, and the appended pre-dispatch audit.

## The measured numbers (pre-lens, `measure_background_step`, unchanged metric)

All three 3g runs on worker `ed11ba89038e…`, v2 env sha `617e63a7…`,
`jobs/rl300_05_studio-floor.json`, azimuths 42 + 222.

| metric | A baseline | B Fill-off | C Rim-off |
|---|---|---|---|
| az42 full max_step (row) | 1.9744644165039062 (552) FAIL | 1.9641952514648438 (553) FAIL | **0.7167434692382812 (3) PASS** |
| az42 left / right halves | 0.7721 / 3.3585 | 0.5537 / 3.4344 | 0.7496 / 0.6919 |
| az42 ramp x=1600 / x=1750 | +4.00 / +3.59 | +4.00 / +4.00 | +1.59 / +1.59 |
| az222 full (row) | 0.7901153564453125 (3) | 0.80059814453125 (3) | 0.8149948120117188 (3) |
| product mean luma az42 / az222 | 133.25 / 106.42 | 128.26 / 82.83 | 133.07 / 104.38 |

Eligible background columns identical in all runs and vs 3e/3f (az42 252 left /
319 right of 571; az222 240/326 of 566; symmetric difference 0) — no mask
drift, so the comparison basis did not move. Fidelity and grain gates pass in
all three.

**Build-invariance test (the contract's first read): PASSED.** 3g run A
(worker `ed11ba89…`, no override) reproduces 3e all-lights (worker
`15349738…`, no override) **exactly** — 1.9744644165039062 at row 552, halves
0.7721/3.3585, az222 0.7901153564453125, luma 133.25, ramps +4.00/+3.59 — so
adding the default-true gate wraps is pixel-neutral for the all-lights
condition, and B/C need no assumption at all (matched-build to A by
construction). **Labelled inference, not measurement:** 3f's Key-off ran worker
`fde78dea…`, which was never re-rendered against a same-build baseline, so its
"worse than all-lights" magnitude (2.4253) is supported **by analogy**, not
proven by a same-build test. Do not upgrade that claim.

## What to review (Mark)

Frames: `output/preview-studio-floor-3g-{baseline,fill,rim}-20260923/cloud/frame-az{42,222}/`
(`composite-prelens.png` = pre-lens gate input, `composite-lens.png` = shipped
look, `mask.png`; generated by `scripts/probe_sequence.py`, which the
dispatcher does not run). A visual read of az42: the baseline and Fill-off
backgrounds both show the same hard tonal boundary in the right background; the
Rim-off background is a smooth gradient while the product is visually
unchanged.

**Decisions that are yours:**

1. **Rim-targeted fix (recommended).** Removing the Rim alone clears the ramp
   under this rig and it contributes
   ~nothing to the product's lit appearance (133.07 vs 133.25; 3f's Key-off, by
   contrast, was 70.33). A targeted change to the Rim's rig parameters — not
   switching it off — is the plausible path to clearing the gate while keeping
   the product. **Discipline: it is a renderer/look change, so it needs your
   look review (ruling 3) and a measured probe — not a new source `.blend`
   version** (see the next section; an earlier draft of this handoff misapplied
   ruling 2 here). Note the licensed wording: the Rim is *necessary given the
   other lights and the v2 env*; if you want the stronger "the Rim is the sole
   origin", render a Rim-only condition (Key and Fill off, Rim on) — not yet
   measured.
2. **Or accept az42 as-is** — the owner look call; the gate stays failed until
   you say otherwise.
3. **Or revert the v2 env manifest flip** (one line in
   `jobs/rl300_05_studio-floor.json` back to `env_studio-softbox.png`) — the
   3e open items below stay unresolved either way.

**Owner sign-offs still open (unchanged — none cleared by 3g):**

- LDR headroom: constraint-11 band-local reading violated as measured
  (pre-clip in-band max 1.29997; 13,541 band pixels newly clipped).
- "Worst azimuth step ≤ half of v1" bar missed (ratios 0.529 / 0.676).
- New elevational edge: worst smoothed gradient 18.96 → 33.19 byte/deg at
  az ~259 / el ~28.4 — outside both probe frames but imaged by an orbit
  azimuth; must be smoothed before any full-orbit claim.
- Full-orbit claim and owner look acceptance (2-frame probes support neither).

## Next round — the Rim fix: what a fresh session needs

**Which ruling applies (corrected 2026-09-23).** Ruling 2 — "material changes
mean a new source `.blend` version and an acceptance round" — is scoped to CAD
**material assignments stored in the source `.blend`**
(`docs/rl300-parity.md:869-871`: "these corrections are now part of the source
hash"). The analytic Rim is created by `render_worker.setup_lighting` at render
time and is not in the `.blend`, so a Rim fix is a **renderer/look change**: it
changes the worker sha and the delivered look, it needs Mark's explicit look
words (ruling 3) plus the frozen gate measurement, and it does **not** need a
new source `.blend` version. An earlier draft of this handoff said otherwise.

**The Rim's current definition** (`render_worker.py`, studio branch): `SPOT`,
energy `600.0 * intensity * radius ** 1.5`, `spot_size = 60°`, color white,
object at `(0, radius*2.8, radius*3.2)` with **no rotation set** — it points
straight down, laying a pool on the floor behind the product, and the az42 ramp
is that pool's far edge crossing the cove region in the right background. Read
the block before designing anything.

**Design space, and the constraint that makes or breaks the evidence.** Levers:
soften (`spot_size` up, wider/softer emitter), re-aim (give it a rotation so it
rims the product instead of the floor), re-power (energy down), move (location).
The constraint: **the pre-fix look must stay reproducible on the same worker
build**, or the comparison crosses builds again — the exact caveat 3g spent
three dispatches retiring. Preferred shape: express the fix as a **versioned,
opt-in rig control in the manifest** (a `lighting.rim_profile`-style selector or
a new preset variant) so the pre-fix rig and the candidate render in one build
while the job of record stays untouched until Mark accepts. A silent value
change in `setup_lighting` destroys that comparability and should be refused.

**Pre-declare before dispatch** (freeze a contract like
`output/batch3g-fill-rim-probe-contract.md`): the exact override(s), the azimuth
set, the pre-fix/post-fix pair on one build, the reported measurement set
(reuse `output/batch3g-measure.py`: full max_step + row, halves, per-column ramp
at x≈1600/1750, product mean luma, eligible-column drift) and the decision rule.
Two traps to name in it: (a) the shipped full-frame metric **dilutes** a
right-localized ramp by ~1.7× (`(252·0.223 + 319·3.3585)/571 = 1.975`), so a fix
that spreads the ramp without removing it can lower the number while leaving the
visible tonal boundary — the **look** is what Mark judges, and softening a light
edge to shave one row of gradient must be presented as a look change, never as a
number fix; (b) moving or re-aiming the Rim moves the pool edge, so it can
**relocate the defect to an azimuth the two probe frames cannot see** — cover
enough azimuths to catch relocation (a coarse orbit is the honest check).

**Cheap attribution-closing run (optional, ~USD 0.08 rate-derived):** Rim-only
(Key off + Fill off + Rim on), using the existing `lighting.key_enabled` /
`fill_enabled` controls, would upgrade "necessary given the other lights" to
"sufficient alone". Worth it only if the stronger claim changes the fix decision.

**Reusable machinery (all `output/`, gitignored):** `batch3g-dispatch.sh`
(preflight → manifest check → `--execute`, with the exact-boolean guard),
`batch3g-measure.py`, `batch3g-verify-controls.py`, `batch3g-check-records.py`,
and this round's specs/contracts as templates. The local gate step is
`probe_sequence.py --run-dir <dir> --expect-frames 2 --no-encode` (it prints full
row profiles; pipe it). Cost shape: a two-frame dispatch measured USD 0.079–0.089
rate-derived; a coarse orbit multiplies render seconds, not container startup —
estimate in `request.json` before dispatch.

## What the next agent must know

- **Probes already paid for — do not re-dispatch.** 3g apps:
  `ap-nTFlLEKccqtQbwr2i8cpio` (baseline), `ap-xTF3wQmJ6S2CBhxnmJ3AD5`
  (Fill-off), `ap-OX3nRdDXZMP5r6kPUUInPM` (Rim-off); logs
  `output/batch3g-<tag>-modal.log`, preflight logs
  `output/batch3g-<tag>-preflight.log`. Estimates USD 0.197 each (0.591
  total); measured Blender seconds 287.944 / 253.576 / 276.334 → **USD 0.08924
  / 0.07859 / 0.08564, total 0.25347 RATE-DERIVED at 0.00030992 USD/s, no
  invoice queried**. 3f's apps remain as recorded in its section.
- **Implementation state (this round's commit):** `render_worker.py` three
  default-true gates (key/fill/rim), `docs/job_manifest.schema.json` three
  optional booleans, `scripts/cloud_job_render.py`
  `SCHEMA_OPTIONAL_OVERRIDE_PATHS` = the three paths,
  `tests/test_floor_mode.py` 7 new tests, plus the 3f work that had been left
  uncommitted. **Never inject defaults into unrelated jobs** — only an explicit
  operator override may create an optional path (the 3f lesson).
- **Worker-sha trap:** take the worker digest from each run's `request.json`
  (`inputs["/input/render_worker.py"]`, e.g. `ed11ba89038e…`). Do **not**
  re-derive it by hashing the worktree or `git show HEAD:render_worker.py` —
  git's CRLF normalization yields a different digest while reporting the file
  clean, so a fresh verifier false-fails. The same applies to the v2 env sha in
  `request.json:15`.
- **Harness-infrastructure lesson (new, costs a round if unknown):** the first
  GLM implementation seat was **killed by the ZCode harness mid-patch** (exit
  137) after completing and verifying TDD RED. Its writes survive as an orphan
  in the tree. Recovery that worked without redoing paid work: preserve the
  killed seat's note and test diff as evidence, verify the RED state yourself
  (`Ran 85 tests … FAILED (failures=5, errors=2)`, architect-reproduced on the
  project venv — the seat's own note still says "RED: (pending)" because the
  runner output died with its process, so that number rests on the architect's
  reproduction, not on a captured seat log), then dispatch a
  **GREEN-only** spec that names the production files, forbids editing the
  tests, and says the tests are the contract. Also: a background `Bash` call
  with a timeout above the 600 s tool maximum is what got killed — keep seat
  dispatches at or under 600 s, or expect to recover like this.
- **Pair protocol (owner instruction 2026-09-22) as exercised this round:**
  controls = GLM worker / DeepSeek reviewer (proxy-log proven: 17 rows
  `zai/glm-5.3-flash` → resolved `glm-5.3-flash`; 26 rows
  `deepseek/deepseek-flash` → resolved `deepseek-flash`); results record = GLM
  producer / DeepSeek reviewer (FIX-FIRST → GLM correction) / handoff = DeepSeek
  producer. **Next task flips to DeepSeek worker / GLM reviewer.** Plain
  dispatches (no workflow harness); seats write files, return ≤ 400 words;
  reviewer gets CONTRACT + ARTIFACT only; architect re-runs every verification
  and reproduces each claimed defect before dispatching a fix.
- **The producer seat caught an error in the architect's own spec** ("four
  default-true gates" — there are three) and flagged it rather than following
  it. Expect that; a spec is a claim to be checked, not scripture.
- **seatwrap trap:** its verify re-run uses Windows `cmd.exe`, which rejects
  `./.venv/...` ("'.' is not recognized"). Pass `--verify-cmd` with a
  cmd-compatible command using **backslashes**
  (`.venv\Scripts\python.exe -m unittest …`); the forward-slash form fails.
  Verified by direct test this round.
- **Model-attribution recipe:** `ocx logs --json` → a top-level object with a
  `logs` array; filter by `timestamp` window + `requestedModel`, and read
  `model`/`provider` as the resolved values. The window can contain other
  sessions' traffic (45 unrelated `deepseek-flash` rows appeared inside the GLM
  seat's window).
- **Review artifacts on file:** `output/batch3g-controls-review-deepseek.md`,
  `output/batch3g-records-review-deepseek.md`,
  `output/batch3g-results-spec.md`; the killed-seat evidence is
  `output/batch3g-killed-seat-{red-note.md,tests.diff,stdout.log}`. Frozen
  contracts: `batch3g-fill-rim-probe-contract.md`. All in `output/` (gitignored).
  Reusable verifiers: `output/batch3g-verify-controls.py` (20 checks),
  `output/batch3g-measure.py`, `output/batch3g-check-records.py`,
  `output/batch3g-dispatch.sh` (preflight → manifest check → execute).
- **Deferred hardening (open debt):** (a) 3g review F1 — a non-boolean
  `--set` value is still accepted and reinterpreted (`FALSE` → truthy string,
  `0`/`null` → silently off); the minimal fix is
  `if may_create and not isinstance(value, bool): raise ValueError(...)` in
  `apply_overrides`, plus an exact-boolean assertion in the dispatch path.
  It did not block this round because `batch3g-dispatch.sh` machine-rejects
  non-boolean manifests before `--execute`. (b) F2/F3 — the 3f "only creatable
  path" test pins nothing new, and the absence-regression guard covers
  `key_enabled` only. (c) 3e GLM finding 7 — refuse to overwrite
  `ACCEPTED_OUTPUT` in `scripts/build_studio_softbox_env.py` unless the
  existing sha matches.
- **Concurrent workstream:** untracked `scripts/*webexport*.py`, `.codex/`,
  `.zcodeignore`, `docs/agent-tooling.md` and the modified `AGENTS.md` are NOT
  this round's — do not touch, do not commit, do not clean up. Commit with
  explicit paths only.
- `probe_sequence.py --run-dir <dir> --expect-frames 2 --no-encode` is the
  2-frame probe invocation (no MP4). It prints the full row profile, so pipe it.

## Standing constraints (unchanged)

- All rendering on Modal, never local (2026-09-20 ruling); USD 30/month
  ceiling; per-run estimates in `request.json` before dispatch, measured seconds
  after, failures recorded too; `cloud_authorized` stays hardcoded false.
- No threshold widened without new numbers — the 1.8 gate and
  `measure_background_step` are untouched; 3g's Fill-off FAIL is reported, not
  rationalized. "Looks good" is not owner acceptance; diagnostics are not
  candidate looks.
- Material/asset changes need a new source asset + acceptance round (ruling 2).
- Single upstream `origin`; the `main` worktree at
  `C:/Projects/msp-render-pipeline` has none of this branch.
- Python: `./.venv/Scripts/python.exe`. Blender at
  `C:/Program Files/Blender Foundation/Blender 5.1/blender.exe` (headless
  `--background --python` only, never a render). ffmpeg on PATH. From Git Bash,
  check `${PIPESTATUS[0]}` — a PowerShell `2>&1` merge corrupts the exit code.

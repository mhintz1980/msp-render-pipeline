# Handoff — 2026-09-24 (batch 3l, session close: **hardening shipped, `pool_soft` accepted as the rig look of record, branch pushed, every owner decision closed — nothing is pending Mark; next lane is T-V2 with an approved probe at its head**)

Worktree: `C:/Projects/msp-render-pipeline-scene-prep`; branch
`codex/studiomark-scene-prep`, **in sync with `origin`** (pushed through
this handoff's commit under Mark's 2026-09-24 "Push"). Session commits, in
order: `55774b9` (3i hardening), `9db7054` (3i handoff), `f1b1071`
(pool_soft acceptance), `e88c94a` (3j handoff + first push), `dbbeee7`
(the five rulings), `fefb0df` (3k handoff), this handoff. This supersedes
`HANDOFF-2026-09-24-batch3k.md` and is the one document a fresh session
needs; older handoffs remain for detail.

Suite evidence, architect-run on the project venv, final state:
**`Ran 288 tests in 66.498s … OK`, exit 0 via `${PIPESTATUS[0]}`** — the
first measured full-suite counts since 3e were this session's (285 → 287 →
288 as rounds landed). The 3h handoff's "264" was arithmetic and
under-counted; 288 is the number to cite. Zero cloud dispatches, zero
spend, no thresholds moved, no renders (local renders remain banned).

## 1. Batch 3i — the carried 3g/3e hardening, closed with SHIP

Four items, five files, all tested (details: `HANDOFF-2026-09-24-batch3i.md`):

- **Typed boolean `--set` (F1, widened twice by review):**
  `BOOLEAN_OVERRIDE_PATHS` = all six schema-declared boolean lighting
  controls — `key/fill/rim_enabled`, `analytic_lights`, `shadow_catcher`,
  and the nested `lighting.floor.enabled`. Non-exact-JSON-boolean values die
  at override time (`BAD_OVERRIDE_VALUE`) or, for manifest-carried garbage,
  at plan time (`INVALID_LIGHTING_BOOLEAN`, one dotted-path walk, before any
  Modal object). `lighting.rim_profile` is deliberately NOT typed —
  `validate_rim_profile` owns its whole value contract and 3h's accepted
  `INVALID_RIM_PROFILE` labels are preserved.
- **F2/F3 test pins:** the creatable allowlist frozen at exactly four
  paths, each creatable-when-absent, `color_temperature_k` still rejected;
  all four optional controls pinned absent → never injected.
- **Accepted-asset sha guard (3e GLM F7):** `guard_accepted_output` in
  `scripts/build_studio_softbox_env.py` refuses writes to
  `ACCEPTED_OUTPUT` when the existing file no longer hashes to the pin or
  the bytes to be written don't; gate is file identity (normcase realpath +
  `samefile`) so links and case-variants can't slip it.
- **Review loop (GLM worker / DeepSeek reviewer, the 3h flip):** FIX-FIRST
  (MAJOR: string-comparison gate bypass) → fix → FIX-FIRST (MINOR: the
  sixth boolean) → fix → **SHIP**. Served model proven per-request from
  `ocx logs` (`deepseek/deepseek-flash → deepseek-flash`, 200s). One
  provider-429 seat kill recovered with a lean completion spec — no paid
  redo. Artifacts: `output/batch3i-{review-contract,artifact.diff,
  hardening-review-deepseek.md,fix-review-contract,fix-review-artifact.diff,
  fix-review2-deepseek.md,fix2-review-artifact.diff}`.

## 2. The look call — closed by Mark's explicit words

From the 3h four options, Mark chose **`pool_soft`** (*"1 (pool_soft is
approved)"*). Recorded verbatim in `docs/rl300-parity.md`. Consequences,
all landed (`f1b1071`):

- `jobs/rl300_05_studio-floor.json` (the job of record, the one the 3h
  orbit measured) now carries `"rim_profile": "pool_soft"`.
- `jobs/rl300_04_studio-white.json` deliberately stays **absent** (= the
  exact `pool_v1` rig its accepted stills parity was measured with);
  extending acceptance there would be its own round.
- Schema description corrected ("not an owner-accepted look" is gone);
  pin test `test_job_of_record_carries_the_accepted_rim_profile` holds
  both facts. Basis on record: 0/30 orbit gate problems at the unchanged
  1.8 pre-lens threshold with `excursion` preserved (transition spread,
  not removed). Ruling 2 (new source `.blend`) does not apply — renderer
  look change (3g ruling).

## 3. The five carried sign-offs — all ruled (verbatim in rl300-parity)

1. Rim-only attribution run — **SKIPPED**, never dispatched; "sole origin"
   stays unmeasured by owner choice, wording unchanged in the record.
2. v2 env LDR headroom — **ACCEPTED** with the approved look; numbers stay
   pinned, test note updated.
3. Half-azimuth-step bar — **RETIRED**; the pre-lens 1.8 orbit gate is the
   binding metric.
4. Elevational-edge probe — **APPROVED as the T-V2 pre-flight head**:
   azimuths 250–270 at 1° (21 frames), ~USD 0.16 rate-derived estimate,
   from the job of record (no override needed), measured with
   `scripts/probe_sequence.py --run-dir <dir> --expect-frames 21
   --no-encode` against the unchanged 1.8 gate, BEFORE the ~USD 1.30
   full-orbit spend. Scope: `docs/video-pipeline-brief.md` §13.5.
5. Full-orbit claim — **OPEN** until a 360-frame run exists.

## 4. Next session — exact next action

1. **T-V2 lane**, starting with the approved elevational-edge probe
   (dispatch recipe: `scripts/cloud_job_render.py --manifest
   jobs/rl300_05_studio-floor.json --azimuths 250,...,270 --output-dir
   output/<run> --execute`, or the `batch3h-dispatch.sh` wrapper with an
   explicit comma list; estimate in `request.json` before, measured seconds
   into `docs/cloud-smoke.md` after, failures recorded too). Then the §9
   sequencer scope.
2. **Pair flip for the next implementation task: DeepSeek worker / GLM
   reviewer** (3i was GLM/DeepSeek; protocol stands — reviewer gets
   contract + artifact only, ≤3 doubt cycles, architect re-verifies).
3. Known-behavior notes carried (no action): guard TOCTOU window
   (pre-existing, fail-closed); leg-2 encode coupling to local Pillow/zlib
   (fail-closed); `apply_overrides` non-atomic failure path (discarded
   locally); two HEAD-passing tests are deliberate over-narrowing guards.
4. Concurrent webexport workstream files — untracked
   `scripts/*webexport*.py`, `scripts/render_airway_corridor.py`,
   `scripts/section_webexport_corridor.py`, `.codex/`, `.zcodeignore`,
   `docs/agent-tooling.md`, and the modified `AGENTS.md` — are NOT this
   branch's rounds: do not touch or commit them; commit explicit paths only.
5. Review imagery for the accepted look remains under
   `output/preview-studio-floor-3h-{ref,soft,off}-20260924/` and
   `output/batch3h-looksheet*.png` (gitignored evidence; read the run
   record, don't assume reproducibility).

## Standing constraints

Unchanged, `AGENTS.md` and `docs/rl300-parity.md` govern: Modal-only
rendering; USD 30/month ceiling; estimates before and measured seconds
after every dispatch; `cloud_authorized` hardcoded false; no threshold
widened without new numbers; "looks good" is not acceptance; single
upstream `origin`; Python `./.venv/Scripts/python.exe` with
`${PIPESTATUS[0]}` checked from Git Bash; Blender not on PATH; `output/`
is gitignored evidence.

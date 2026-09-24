# Handoff — 2026-09-24 (batch 3k: **all five carried sign-offs ruled by Mark — Rim-only skipped, LDR headroom accepted, half-az bar retired, elevational-edge probe approved as the T-V2 pre-flight, full-orbit claim open until 360**)

Worktree: `C:/Projects/msp-render-pipeline-scene-prep`; branch
`codex/studiomark-scene-prep`. Commits this session, in order: `55774b9`
(batch 3i hardening), `9db7054` (3i handoff), `f1b1071` (pool_soft
acceptance), `e88c94a` (3j handoff, first push), then this round's
records commit and this handoff — both pushed the same day under Mark's
standing "Push". Take live state from `git log --oneline`. This supersedes
`HANDOFF-2026-09-24-batch3j.md`.

## The rulings (verbatim in `docs/rl300-parity.md`, "the five carried items")

Mark, 2026-09-24: *"1. skip it" / "2. Accept it" / "3. Retire it" /
"4. i approve your recommendation" / "5. stays open until 360 run"*

1. **Rim-only attribution run — SKIPPED**, never dispatched. "Sole origin"
   stays unmeasured by owner choice; the record keeps its exact measured
   wording.
2. **v2 env LDR headroom — ACCEPTED** with the approved look (pre-clip max
   1.29997…; 13,541 band px; composed max 1.0). Numbers stay pinned;
   `test_constraint_11_headroom_is_recorded`'s pending-sign-off note updated.
3. **Half-azimuth-step bar — RETIRED.** The ≤0.5 target no longer gates
   anything; the binding metric is the pre-lens 1.8 orbit gate (30/30 with
   the accepted look). Measured ratios stay as history.
4. **Elevational-edge probe — APPROVED as the T-V2 pre-flight head.**
   Recorded with full scope in `docs/video-pipeline-brief.md` §13.5:
   azimuths 250–270 at 1° (21 frames), ~USD 0.16 rate-derived estimate,
   from the job of record (rl300_05 now carries `pool_soft` — no override
   needed), `probe_sequence.py --run-dir <dir> --expect-frames 21
   --no-encode`, unchanged 1.8 gate, estimate-before/measured-after. It
   dispatches when T-V2 starts, BEFORE the ~USD 1.30 full-orbit spend.
5. **Full-orbit claim — OPEN** until a 360-frame run exists.

Suite after the record edits: **`Ran 288 tests … OK`**, exit 0 via
`PIPESTATUS` (wording-only test edits; no numbers moved).

## State of the world for the next session

- **The rig look of record is settled**: `pool_soft`, accepted, pinned,
  pushed. No look decisions are pending anywhere.
- **The next lane is T-V2** (`docs/video-pipeline-brief.md` §9 scope, §13.5
  pre-flight): the elevational-edge probe first (approved, ~USD 0.16 est.),
  then the sequencer work. Pair flip for implementation: **DeepSeek worker /
  GLM reviewer**.
- Batch 3i hardening all in force: typed boolean `--set` (six controls),
  allowlist/absence pins, accepted-asset sha guard.
- Concurrent webexport workstream files remain untouchable (untracked
  `scripts/*webexport*.py`, `scripts/render_airway_corridor.py`,
  `scripts/section_webexport_corridor.py`, `.codex/`, `.zcodeignore`,
  `docs/agent-tooling.md`, modified `AGENTS.md`); commit explicit paths only.

## Standing constraints

Unchanged: `AGENTS.md` and `docs/rl300-parity.md` govern; Modal-only
rendering; USD 30/month ceiling; estimates before and measured seconds after
every dispatch, failures recorded too; `cloud_authorized` hardcoded false;
no threshold widened without new numbers; single upstream `origin`; Python
is `./.venv/Scripts/python.exe` with `${PIPESTATUS[0]}` checked; `output/`
is gitignored evidence.

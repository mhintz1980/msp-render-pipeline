# Handoff — 2026-09-24 (batch 3j: **Mark accepted `pool_soft` as the rig look of record and authorized the push — the 3h look call is CLOSED**)

Worktree: `C:/Projects/msp-render-pipeline-scene-prep`; branch
`codex/studiomark-scene-prep`. Commits this session: `55774b9` (batch 3i
hardening), `9db7054` (3i handoff), **`f1b1071`** (the acceptance), this
handoff's own commit. **The push to `origin` executed 2026-09-24 with Mark's
explicit words** ("Push") — if `git log origin/codex/studiomark-scene-prep..HEAD`
is non-empty, someone committed after it; the push itself is done, not
pending. This supersedes `HANDOFF-2026-09-24-batch3i.md`.

## What Mark decided (verbatim, recorded in `docs/rl300-parity.md`)

> *"1 (pool_soft is approved)"*
>
> *"Push"*

Decision 1 of the 3h four options. **`lighting.rim_profile: pool_soft` is
the owner-accepted rig look of record.** The job of record is
`jobs/rl300_05_studio-floor.json` — it now carries `"rim_profile":
"pool_soft"`; `jobs/rl300_04_studio-white.json` deliberately stays absent
(absent = `pool_v1`, the exact rig its accepted stills parity was measured
with; extending acceptance there would be its own round). The schema's
`rim_profile` description no longer says "not an owner-accepted look". A pin
test holds both facts. Suite measured after the change: **`Ran 288 tests …
OK`**, exit 0 via `PIPESTATUS`.

## Still open, and the architect's recommendations to Mark (this session)

Mark asked for opinions; these are recommendations, NOT decisions — his
words still needed:

1. **Rim-only attribution run (~USD 0.08 est.) — recommend SKIP.** Its only
   consumer was the look decision, which is now made. The record already
   carries the precise measured wording ("the ramp depends on the Rim given
   the other lights and the v2 env; a Rim-only rig was never rendered").
   Operationally, Rim-off removing the ramp is enough for any future tuning.
2. **LDR headroom (pre-clip in-band max 1.29997; 13,541 band px newly
   clipped) — recommend ACCEPT AS PART OF THE APPROVED LOOK.** The clipping
   is baked into the v2 env Mark just approved; 0/30 gates passed with it.
   One word from him closes it.
3. **Half-azimuth-step bar (3g ratios 0.529/0.676 vs the 0.5 target) —
   recommend RETIRE as a formal bar.** It was an amended-spec target the
   measured map missed; the metric that matters now is the orbit gate, which
   pool_soft passes 30/30.
4. **v2 env elevational edge (az~259/el~28.4, 18.96 → 33.19 byte/deg) —
   recommend KEEP OPEN and fold into the T-V2 pre-flight.** This is the one
   item with real teeth: the 3h orbit sampled only every 12°, but production
   video renders 1° steps and azimuth ~259 WILL sample the edge. A small
   paid probe (azimuths 250–270 at 1°, ~USD 0.16 rate-derived estimate —
   21 frames ≈ 272 s warm + 229 s cold at 0.00030992 USD/s) should run
   BEFORE the ~USD 1.30 full-orbit spend. Needs Mark's go since it spends.
5. **Any full-orbit claim** — stays open until a 360-frame run exists.

## What the next agent must know

- The look call is closed; nothing about the acceptance changes the 3i
  hardening (typed boolean `--set`, allowlist pins, sha guard) — all still
  in force, suite 288.
- Pair flip for the next implementation task: **DeepSeek worker / GLM
  reviewer** (3i was GLM/DeepSeek).
- The T-V2 sequencer work (`docs/video-pipeline-brief.md`) is the next lane
  once Mark rules on items 2–4 above; the elevational-edge probe belongs at
  its head.
- Concurrent webexport workstream files — untracked
  `scripts/*webexport*.py`, `scripts/render_airway_corridor.py`,
  `scripts/section_webexport_corridor.py`, `.codex/`, `.zcodeignore`,
  `docs/agent-tooling.md`, and the modified `AGENTS.md` — remain not this
  round's: do not touch or commit them; commit explicit paths only.

## Standing constraints

Unchanged: `AGENTS.md` and `docs/rl300-parity.md` govern; Modal-only
rendering; USD 30/month ceiling; estimates before and measured seconds after
every dispatch, failures recorded too; `cloud_authorized` hardcoded false;
no threshold widened without new numbers; single upstream `origin`; Python
is `./.venv/Scripts/python.exe` with `${PIPESTATUS[0]}` checked; `output/`
is gitignored evidence.

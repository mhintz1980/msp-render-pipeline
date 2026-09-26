# Handoff — 2026-09-24 (batch 3m: **T-V2 lane opened and run end to end — edge probe PASSED, `--resume` and WebM/streaming shipped with cross-family review, and the first 360-frame orbit rendered on Modal with every gate passing and ACCEPTED by Mark; nothing is pending him**)

Worktree `C:/Projects/msp-render-pipeline-scene-prep`, branch
`codex/studiomark-scene-prep`, **in sync with `origin`**. Supersedes
`HANDOFF-2026-09-24-batch3l.md`. Session commits, in order: `1fab813` (edge
probe record), `6cd3429` (T-V2a resume), `f6da1eb` (T-V2b streaming + WebM),
`f54fe0b` (360 orbit record + handoff 3m), `b204ca2` (owner acceptance), and
this handoff's final revision (brief §9.1 status, cloud-smoke acceptance
addendum, handoff refresh) — all pushed under Mark's 2026-09-24 *"i approve.
commit any changes and push"*.

Suite, architect-run on the project venv: **`Ran 321 tests … OK`, exit 0 via
`${PIPESTATUS[0]}`** (288 → 315 → 321). No threshold moved. No local renders.
Zero spend after the orbit.

## 1. What happened

1. **Elevational-edge probe (the approved T-V2 pre-flight)** — az250–270 at 1°,
   21/21, all gates pass, worst pre-lens step 0.8603 (az267), az259 0.803,
   vs the unchanged 1.8. USD 0.15876 rate-derived (512.249 s) vs ~0.16 est.
   Record: `docs/cloud-smoke.md` + brief §13.5 result.
2. **T-V2a `--resume`** (`scripts/cloud_job_render.py`): a frame is complete only
   when the result parses, says rendered, carries GPU evidence, **and** every
   declared artifact sha verifies on disk; plan drift (incl. the worker sha in
   `inputs`) → `RESUME_REQUEST_MISMATCH` with nothing written; `resume-log.json`
   per `--execute` resume; `status.json` covers the whole plan from disk and
   gains `"resumed"`. Pair: **DeepSeek worker** (two seats killed by provider
   429s — seat 1 empty diff, seat 2 wrote code+tests unrun; architect fixed
   three defects: argv[0] in the test harness, `plan["frames"]` vs
   `request["frames"]`, and the fixture's placeholder plate reaching the
   compositor) / **GLM reviewer** FIX-FIRST (MAJOR: complete-looking foreign
   frames were adopted when `request.json` was absent) → fixed → round-2 SHIP.
3. **T-V2b** (`scripts/probe_sequence.py`): streaming neighbour MAE (bounded
   memory at 360 frames; identical numbers) + VP9/WebM encode with its own
   count and decode-PSNR gates against the existing 35 dB floor; `--no-webm`
   opts out. Pair (flipped): **GLM worker** (tests first) / **DeepSeek reviewer**
   SHIP first round. Two MINOR test-robustness notes **carried, not fixed**:
   the MAE fixture writes one mask for all frames (blind to mask mis-pairing,
   the code is correct), and the real-encoder smoke skips on missing `ffmpeg`
   only, not `ffprobe`/libvpx-vp9.
4. **First full orbit, 360 frames @1°** — `output/tv2-orbit360-20260924/`,
   360/360, zero failures, **all gates pass**: worst background step 0.9043
   (az361), none above 1.5; MP4 38.69/38.20/37.69 dB and WebM 40.98/38.59/37.85
   dB, both 360 encoded frames. **USD 1.65429 rate-derived** (5337.8 s) vs
   ~1.58 estimated, wall ~1 h 40 m. First use of `--resume` in production (one
   invocation, 360 pending, `resumed: false` — nothing was re-paid).
5. **Accepted.** Mark reviewed it and answered verbatim *"i approve. commit any
   changes and push"*; recorded in `docs/rl300-parity.md` ("2026-09-24 — owner
   acceptance: the first 360-frame turntable orbit"), which also **closes
   carried item 5** (the full-orbit claim).

## 2. Owner items — none pending

Mark ruled on the loop (accepted) and the push (authorized and executed). The
only thing a next session may bring back to him is a **new** scope choice: a
standalone dark-sector probe if he wants §9 criterion 1 satisfied in its
original shape (see §3.3), or any new spend.

## 3. Next actions

1. **Nothing is blocked.** The T-V2 lane's remaining work is engineering, not
   owner-gated: `docs/video-pipeline-brief.md` **§9.1** is now the single
   status of record for what is built and what is left. Two §9 items are
   unbuilt — the optional manifest `sequence` block (orbits are CLI-declared
   today) and criterion 4's declared sampled-frame set.
2. **Next implementation task flips the pair back to DeepSeek worker / GLM
   reviewer** (`[[pair-delegation-protocol]]`). Budget for a 429: two DeepSeek
   seats died mid-task this session; have the completion spec ready, and
   re-verify on the project venv regardless of what a seat reports.
3. **Cheap follow-up, no ruling needed:** re-base the dispatcher's
   `cost_estimate_usd` on measured warm ~13.6 s/frame + one position-1 frame
   (~240–266 s). It is an estimate, not a gate — but it is ~14× conservative
   today (22.7534 recorded for a run that measured USD 1.65429 rate-derived),
   which makes it useless for go/no-go on spend.
4. **Optional, if the full §9 criterion set matters:** run the 60-frame
   dark-sector probe as originally written rather than relying on the orbit's
   whole-sequence statistics — ~USD 0.33 rate-derived (61 frames: one ~240 s
   position-1 frame + 60 × ~13.6 s ≈ 1056 s). Ask before spending; the orbit
   already answers the pumping question with numbers (brief §9.1).
5. **Dispatch recipe, unchanged:** `scripts/cloud_job_render.py --manifest
   jobs/rl300_05_studio-floor.json --orbit N --output-dir output/<run>
   [--resume] [--execute]`; non-executing preflight first, estimate in
   `request.json`, measured seconds into `docs/cloud-smoke.md`, failures
   recorded too. Sequence gates: `scripts/probe_sequence.py --run-dir <dir>
   --expect-frames N [--no-webm]`, exit 0 means every declared gate passed.

## 4. Traps and known behavior (no action unless they bite)

- **Untracked/unrelated worktree files**: `scripts/edit_webexport_airway.py`,
  `scripts/export_webexport_glb.py`, `scripts/probe_webexport_airway.py`,
  `scripts/render_airway_corridor.py`, `scripts/section_webexport_corridor.py`,
  `.codex/`, `.zcodeignore`, `.cbmignore`, `docs/agent-tooling.md`, and a
  modified `AGENTS.md` (pre-existing drift, not this branch's). **Commit
  explicit paths only** — never `git add -A`.
- **Carried from 3l:** guard TOCTOU window (pre-existing, fail-closed); leg-2
  encode coupling to local Pillow/zlib (fail-closed); `apply_overrides`
  non-atomic failure path (discarded locally); two HEAD-passing tests are
  deliberate over-narrowing guards.
- **Non-bit-determinism:** same-build dispatches differ by ~500 of 2.25 M px at
  ±1 LSB with byte-identical masks. Never write a byte-identical-PNG acceptance
  clause; the A/A control is the precedent (`[[gpu-pipeline-not-bit-deterministic]]`).
- **429s on ocx seats** are now a pattern (three this session across DeepSeek and
  one provider kill in 3i). `ocx logs` proves which model served each seat.
- Evidence is gitignored: `output/tv2-orbit360-20260924/{turntable-loop.mp4,
  turntable-loop.webm,sequence-report.json,status.json,resume-log.json}`,
  `output/tv2-orbit360-sheet.png`, `output/tv2-edgeprobe-*`. Read the run
  records in `docs/cloud-smoke.md`; do not assume the bytes are reproducible.
- Standing constraints unchanged (`AGENTS.md`, `docs/rl300-parity.md`):
  Modal-only rendering, USD 30/month ceiling (month-to-date rate-derived frame
  spend ≈ USD 3.7), estimates before and measured seconds after every dispatch,
  `cloud_authorized` hardcoded false, no threshold widened without new numbers,
  "looks good" is not acceptance, single upstream `origin`, Python
  `./.venv/Scripts/python.exe` with `${PIPESTATUS[0]}` checked from Git Bash,
  Blender not on PATH.

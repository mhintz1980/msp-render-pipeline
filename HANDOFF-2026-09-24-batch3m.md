# Handoff — 2026-09-24 (batch 3m: **T-V2 lane opened and run end to end — edge probe PASSED, `--resume` and WebM/streaming shipped with cross-family review, and the first 360-frame orbit rendered on Modal with every gate passing; the loop is `awaiting_owner_review`**)

Worktree `C:/Projects/msp-render-pipeline-scene-prep`, branch
`codex/studiomark-scene-prep`. Supersedes `HANDOFF-2026-09-24-batch3l.md`.
Session commits: `1fab813` (edge probe record), `6cd3429` (T-V2a resume),
`f6da1eb` (T-V2b streaming + WebM), this handoff (360 orbit record).
Pushed under Mark's 2026-09-24 "commit any changes and push".

Suite, architect-run on the project venv: **`Ran 321 tests … OK`, exit 0 via
`${PIPESTATUS[0]}`** (288 → 315 → 321). No threshold moved. No local renders.

## 1. What happened

1. **Elevational-edge probe (the approved T-V2 pre-flight)** — az250–270 at 1°,
   21/21, all gates pass, worst pre-lens step 0.8603 (az267), az259 0.803,
   vs the unchanged 1.8. USD 0.15876 rate-derived (512.249 s) vs ~0.16 est.
   Record: `docs/cloud-smoke.md` + brief §13.5 result.
2. **T-V2a `--resume`** (`scripts/cloud_job_render.py`): complete = result
   parses + rendered + GPU evidence + every artifact sha verified on disk;
   plan drift (incl. worker sha) → `RESUME_REQUEST_MISMATCH`, nothing written;
   `resume-log.json` per `--execute` resume; status.json covers the whole plan.
   DeepSeek worker (two seats killed by provider 429; architect fixed 3 defects)
   / GLM review FIX-FIRST (MAJOR foreign-frame adoption) → fixed → SHIP.
3. **T-V2b** (`scripts/probe_sequence.py`): streaming neighbour MAE (bounded
   memory at 360 frames) + VP9/WebM encode with its own count and decode-PSNR
   gates against the existing 35 dB floor; `--no-webm`. GLM worker / DeepSeek
   review SHIP first round. Two MINOR test-robustness notes carried (MAE
   fixture uses one mask; smoke skip guard checks ffmpeg only).
4. **First full orbit, 360 frames @1°** — `output/tv2-orbit360-20260924/`,
   360/360, zero failures, **all gates pass**: worst background step 0.9043
   (az361), none above 1.5; MP4 38.69/38.20/37.69 dB, WebM 40.98/38.59/37.85 dB,
   both 360 encoded frames. **USD 1.65429 rate-derived** (5337.8 s), wall ~1 h 40 m.
   Month-to-date rate-derived frame spend ≈ USD 3.7 of 30.

## 2. Owner items (Mark)

- **Watch the loop**: `output/tv2-orbit360-20260924/turntable-loop.mp4`
  (and `.webm`), 12 s at 30 fps. **ACCEPTED by Mark 2026-09-24 ("i approve"), recorded in `docs/rl300-parity.md`; ruling 5 closed.** Was: status `awaiting_owner_review` — ruling 5's
  precondition (a 360-frame run) now exists, but the full-orbit/video
  acceptance is his words, not the gates.
- **Push**: authorized and executed with the acceptance commit.

## 3. Next actions

1. DONE: Mark accepted the loop (recorded verbatim in `docs/rl300-parity.md`).
   Next video work starts from the §9 leftovers below.
2. Remaining §9 items not yet built: an optional manifest `sequence` block
   (the orbit is CLI-driven today) and a declared sampled-frame set for the
   §9 criterion-4 threshold checks. The dispatcher's `cost_estimate_usd`
   is ~14× conservative — re-base it on measured warm ~13.6 s/frame + one
   position-1 frame (tests pin the old formula; change with a ruling-free
   test update, it is an estimate not a gate).
3. Next pair task flips back to **DeepSeek worker / GLM reviewer**.
4. Untracked webexport/corridor files, `.codex/`, `.zcodeignore`,
   `docs/agent-tooling.md`, modified `AGENTS.md` — still not this branch's;
   commit explicit paths only.

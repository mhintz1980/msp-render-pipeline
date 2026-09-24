# Handoff — 2026-09-24 (batch 3i: **the carried 3g/3e hardening is closed — typed boolean `--set` for all six schema lighting controls, the F2/F3 test pins, and a sha-guarded accepted env asset; DeepSeek review loop FIX-FIRST ×2 → SHIP; zero dispatches**)

Worktree: `C:/Projects/msp-render-pipeline-scene-prep`; branch
`codex/studiomark-scene-prep`. The round commit is **`55774b9`**; this
handoff is committed as its own commit after it. The branch is **15 local
commits ahead of `origin/codex/studiomark-scene-prep`** at the handoff
commit — take the live state from `git log --oneline`, never from this
count. **The push still waits for Mark's words.** This supersedes
`HANDOFF-2026-09-24-batch3h.md`.

Suite evidence, exactly as architect-run on the project venv:
`./.venv/Scripts/python.exe -m unittest discover -s tests` →
**`Ran 287 tests in 90.073s ... OK`, exit 0 confirmed via `${PIPESTATUS[0]}`**
(same verdict on the two earlier runs this round at 285/287). This is the
first MEASURED full-suite count since 3e's 239. The 3h handoff's "264" was
arithmetic and under-counted — it added only 3h's 18 tests to 3e's 239 and
never included 3g's test additions; this round added 12 tests plus widened
subTest loops. 287 supersedes 264 as the number to cite.

## Short version

3i was the no-dispatch hardening round the 3h handoff queued: the deferred
3g review findings F1/F2/F3 and 3e's GLM finding 7. Nothing was rendered,
dispatched, encoded, or threshold-changed; no owner gate was crossed. Every
change ships with tests and went through the pair protocol — GLM worker /
DeepSeek reviewer (the flip 3h prescribed), two FIX-FIRST rounds applied and
re-verified, round-3 verdict **SHIP** with per-request model attribution
proven from `ocx logs` (`deepseek/deepseek-flash → deepseek-flash`, provider
deepseek, HTTP 200 in every seat's window).

## What changed (five files, commit `55774b9`)

- `scripts/cloud_job_render.py` — `BOOLEAN_OVERRIDE_PATHS` now holds **all
  six schema-declared boolean lighting controls**: `key_enabled`,
  `fill_enabled`, `rim_enabled` (the 3g three), plus `analytic_lights`,
  `shadow_catcher` (round-2 widening) and the nested `lighting.floor.enabled`
  (round-3). `apply_overrides` rejects any non-exact-JSON-boolean `--set`
  value for them (`BAD_OVERRIDE_VALUE`, before the value is written);
  `validate_lighting_booleans` walks the same single dotted-path list at plan
  time and rejects manifest-carried garbage (`INVALID_LIGHTING_BOOLEAN`),
  nesting included — called in `frame_plan` after `validate_rim_profile`,
  before mounts and before any Modal object. `lighting.rim_profile` is
  deliberately NOT typed: `validate_rim_profile` owns its whole value
  contract and 3h's accepted tests pin the `INVALID_RIM_PROFILE` labels; the
  3g literal recipe (`may_create` implies bool) predates `rim_profile`
  joining the creatable set and would have broken `rim_profile=pool_soft`.
- `scripts/build_studio_softbox_env.py` — `guard_accepted_output` runs in
  `main()` before every write: leg 1 refuses when the existing
  `ACCEPTED_OUTPUT` no longer hashes to the pinned `ACCEPTED_SHA256`
  (bf67d7ea…); leg 2 refuses when the bytes about to be written (encoded via
  BytesIO with `save()`'s own parameters) do not hash to the pin. The gate is
  file identity, not a path string: normcased realpath equality plus
  `os.path.samefile`, so hard links, `\\?\` spellings and case-variant paths
  (asset absent, Windows) cannot slip either leg. Writes to any other output
  pass through untouched.
- `tests/test_cloud_job_render.py` — boolean rejection loop over all six
  paths × five bad literals, exact-boolean acceptance (incl. nested floor),
  and a guard that F1 did not narrow the general override grammar.
- `tests/test_floor_mode.py` — F2 positive pin: `SCHEMA_OPTIONAL_OVERRIDE_PATHS`
  frozen at exactly the four creatable paths, `BOOLEAN_OVERRIDE_PATHS` frozen
  at exactly the six, each creatable path creatable-when-absent with the value
  reaching frames, and schema-declared `lighting.color_temperature_k` still
  `UNKNOWN_OVERRIDE_PATH`; F3: all four optional controls pinned absent →
  never injected; plan-time tests for both `--set` and manifest-carried
  garbage on all six controls.
- `tests/test_studio_softbox_env.py` — guard tests: reproducing write passes
  on the tracked asset (also the encode-determinism tripwire), diverged-file
  refusal, wrong-profile refusal, other-output pass-through, hard-link
  refusal, and case-variant refusal (Windows-only, skipped elsewhere by
  design).

The schema needed no change — all six booleans were already declared in
`docs/job_manifest.schema.json`.

## Review record (all in gitignored `output/`)

Round 1: `batch3i-review-contract.md` + `batch3i-review-artifact.diff` →
`batch3i-hardening-review-deepseek.md` (**FIX-FIRST**: MAJOR — the guard's
resolved-path string comparison let a hard link and an absent-asset
case-variant through; MINOR — analytic_lights/shadow_catcher truthy-string
class; plus notes). Round 2 (fixes applied):
`batch3i-fix-review-contract.md` + `batch3i-fix-review-artifact.diff` →
`batch3i-fix-review2-deepseek.md` (**FIX-FIRST**: MINOR —
`lighting.floor.enabled` was the sixth untyped schema boolean and the comment
overclaimed; NOTE — the key names were duplicated between frozenset and
validate tuple). Round 3 (fix applied):
`batch3i-fix2-review-artifact.diff` → ROUND-3 VERDICT appended to the same
review file: **SHIP**, "finding 1 closed, NOTE 2 duplication removed, no new
hole; nothing outstanding." The round-2 seat was killed by a provider 429
after three 200s (file never written); recovered with a lean completion
spec, no paid redo — the pattern works.

## Record corrections (this round's own, from the reviews)

- The 3i round-1 contract said "four changed files"; the change is **five**
  (listed above). The modified `AGENTS.md` in the tree is the concurrent
  webexport workstream, not this round's.
- The round-2 disposition wording "every `jobs/*.json` carries them as
  proper JSON booleans" was imprecise: `analytic_lights`/`shadow_catcher`
  are booleans in all six jobs; the three `*_enabled` are **absent** from
  all six (they are opt-in `--set` overrides). No live manifest changes
  behavior under the fix — conclusion unchanged, wording corrected.

## Accepted notes, no change (carry as known behavior)

Check-then-write TOCTOU window in the guard (pre-existing, fail-closed in
practice); leg 2 couples to the local Pillow/zlib encode (fail-closed, loud
if it ever diverges); `apply_overrides` is non-atomic on its failure path
(`frame_plan` builds and discards the dict locally); two of the new tests
pass on HEAD by design — they guard against over-narrowing the override
grammar.

## What stays Mark's — unchanged from 3h

The four look decisions (`pool_soft` acceptance / keep shipped rig with
az42+az318 / Rim-off / none), the push (15 ahead now), LDR headroom
(`1.29997` pre-clip; 13,541 newly clipped band px), the half-azimuth-step
bar (3g ratios 0.529/0.676), the v2 env elevational edge (18.96 → 33.19
byte/deg), any full-orbit claim, and the optional Rim-only attribution run
(~USD 0.08 rate-derived, still not dispatched).

## Next round — what a fresh session needs

- Pair flip: this round was GLM worker / DeepSeek reviewer, so the next
  implementation task is **DeepSeek worker / GLM reviewer**.
- No hardening debt remains from 3g/3e. The queue is: Mark's look call
  (blocking the rig decision), the optional Rim-only attribution dispatch
  (only if the stronger claim would change the look decision), then T-V2
  sequencer work per `docs/video-pipeline-brief.md`.
- Dispatch recipe, measurement, and methods: unchanged, see the 3h handoff's
  "Next round" section (`output/batch3h-dispatch.sh`,
  `scripts/probe_sequence.py --run-dir <dir> --expect-frames 30 --no-encode`,
  `output/batch3h-*.py`).
- Concurrent webexport workstream files — untracked
  `scripts/*webexport*.py`, `scripts/render_airway_corridor.py`,
  `scripts/section_webexport_corridor.py`, `.codex/`, `.zcodeignore`,
  `docs/agent-tooling.md`, and the modified `AGENTS.md` — are not this
  round's: do not touch or commit them; commit explicit paths only.

## Standing constraints

Unchanged: `AGENTS.md` and `docs/rl300-parity.md` govern; Modal-only
rendering; USD 30/month ceiling; estimates before and measured seconds after
every dispatch, failures recorded too (this round: zero dispatches, zero
spend); `cloud_authorized` hardcoded false; no threshold widened without new
numbers; "looks good" is not acceptance; single upstream `origin`; Python is
`./.venv/Scripts/python.exe` with `${PIPESTATUS[0]}` checked from Git Bash;
Blender is not on PATH; `output/` is gitignored evidence.

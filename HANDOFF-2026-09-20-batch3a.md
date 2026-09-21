# Handoff — 2026-09-20 (batch 3a)

Worktree: `C:/Projects/msp-render-pipeline-scene-prep`, branch
`codex/studiomark-scene-prep` (single upstream: GitHub `origin`). Supersedes
`HANDOFF-2026-09-20.md`. Suite **158 tests OK, exit 0**
(`./.venv/Scripts/python.exe -m unittest discover -s tests`, absolute
interpreter path; from Git Bash check `${PIPESTATUS[0]}` — a PowerShell `2>&1`
merge corrupts the exit code).

Short version: **Mark accepted the first motion artifact and ruled that no
delivered video may duplicate frames. Batch 3 was replanned into 3a (the
ruling, plus the tripwire the floor needs) and 3b (the floor itself). 3a is
committed at `8e97a6b` and needs pushing. 3b is the next task, and it is a
bigger task than the previous handoff implied.**

---

## Owner acceptance and ruling, 2026-09-20 — verbatim

Both recorded in full in `docs/rl300-parity.md` ("2026-09-20 — owner
acceptance: first motion artifact, and the no-duplicate-frames ruling").

1. *"**We just completed the turntable animation last session … which i
   approve.**"* — `output/preview-turntable-batch2-20260920/batch2-turntable-loop.mp4`
   is **accepted**. First accepted video deliverable in this pipeline. Scope:
   the look (DOF f/3.2, contact shadow 0.35, v2 sweep, vignette 0.45, bloom
   0.3, grain 2.2), the orbit cadence, the encode quality. **Not** an
   acceptance of the file's frame layout, and it converts no
   `awaiting_reference_acceptance` parity artifact.
2. *"**in the future I would prefer not doing 3 identical orbits … We should
   try and never duplicate frames.**"* — **standing ruling.** A delivered file
   is one pass through unique frames; looping is the player's job. A
   quality-check artifact spends its budget on **more unique frames on one
   orbit**, never repeats of a shorter one.

## What 3a fixed, and the lesson worth keeping

`scripts/probe_sequence.py` passed `-stream_loop 4` to ffmpeg, so the accepted
file was `nb_frames=150` — 30 unique frames played five times. (Mark saw three
orbits; the defect was larger than the note claimed.)

**The §7.4 duplicate-frame gate ran and passed correctly.** It digests the
composited PNGs, where all 30 frames are genuinely distinct. The duplication
happened *downstream at encode*, and the §7.5 decode-back check sampled
indices 0/15/29 — all inside the first pass. The gates were pointed at the
wrong artifact, which is precisely what §7.5 exists to prevent. Every new gate
in 3a is therefore anchored to the bytes that ship.

Landed (detail in `docs/video-pipeline-brief.md` §13, run record in
`docs/cloud-smoke.md` "2026-09-20 batch-3a"):

- One-pass encode; `encoded_frame_count()` reads the **encoded file** via
  `ffprobe` and gates `ENCODED_FRAME_COUNT_MISMATCH`. If the count cannot be
  obtained it reports `ENCODED_FRAME_COUNT_UNAVAILABLE` rather than raising, so
  a paid-for encode never discards the report's other measured gates.
- `orbit_azimuths(count, start)` and `reject_duplicate_azimuths()` in
  `frame_plan` preflight — **keyed on `frame_name()`, because the frame label
  is the billing unit** (it names the frame dir, the per-frame `job_id`, and
  the container output dir). The modulo-360 check is kept alongside it.
- `probe_sequence` reads each frame's **true** azimuth from its own manifest
  (`frame_azimuth`), not the rounded directory label.
- `--orbit N` (mutually exclusive with `--azimuths`, recorded in
  `request.json`) and `--expect-frames`.
- `MATTE_COVERAGE_CEILING = 0.90` + `matte_plausibility_pass` in
  `composite_worker.py` — the tripwire for 3b, explained below.

**Zero Modal dispatch; estimated and measured cost USD 0.00**, recorded anyway
per the every-run convention.

## Two measured facts that change what is possible

1. **360 frames per orbit is the current hard ceiling.** `frame_name` rounds to
   whole degrees, so 400 unique azimuths collapse to 360 unique labels.
   `--orbit 400` now fails preflight (`DUPLICATE_AZIMUTH: 46.5 repeats 45.6`)
   instead of paying for 40 frames that overwrite others. 30/100/300/360 all
   pass, so the T-V2 target of 300 frames at 1.2°/frame is unaffected. Going
   past 360 needs a finer frame label — a real change, not a threshold to widen.
2. **A 300-frame shot would have failed its own sequence gate.** At 300 frames
   the true step is 1.200°, but the rounded labels stepped {1, 2}, tripping
   `NON_UNIFORM_AZIMUTH_STEPS`. Fixed by the manifest readback; verified
   against the real batch-2 run dir (`frame-az102` reads back 102.0).

## Batch 3b — the floor, and why it is bigger than it looked

Goal unchanged: a real rendered floor under the machine, killing the
machine-to-backdrop boundary artifact both vision reads flagged and making DOF
believable by putting something behind the machine to blur.

**The thing the previous handoff missed.** The product matte is not a separate
render pass — `write_matte_pass` (`render_worker.py:1069-1107`) loads the
finished `beauty.png` and takes **channel 3 of its alpha** (`:1087`). "Product
pixels" means "pixels where the beauty render is opaque", which holds only
because `scene.render.film_transparent = True` is hardcoded at
`render_worker.py:1331`. An opaque floor is opaque, so **every floor pixel
becomes "product"** — and three gates then pass while measuring nothing:

- the T05 fidelity gate stops isolating the machine (it starts asserting the
  floor is unaltered too);
- `create_contact_shadow` casts from the floor's silhouette, not the machine's;
- the §7.4 coverage scalar pins near 1.0 and can no longer detect a frame that
  lost the machine.

That silent-green failure is why `matte_plausibility_pass` shipped first. It is
grounded on measured coverage near 0.42 (0.4197–0.4442 across a full orbit), so
0.90 cannot fire on a legitimate matte — it fires exactly on this.

**3b must resolve, with numbers not assumptions:**

1. **How the matte excludes the floor.** Alpha cannot separate them. This needs
   a real mechanism — an object-index/cryptomatte pass, or a matte rendered
   film-transparent with the floor hidden — and `write_matte_pass` supports
   neither today. **This is the actual engineering content of 3b.**
2. **A manifest key for `film_transparent`** (floor mode needs it false, every
   existing job needs it true). Additive and defaulted so no accepted hash moves.
3. **Where the floor plane is created** — *after* the ground-keyword hide pass
   (`render_worker.py:1247-1279`, which hides any mesh whose name contains
   `plane`, `plate`, `env`, `surface`, or that is a large flat slab near z=0),
   following the `GroundShadowCatcher` precedent, sized off the same radius
   basis the worker actually used. The hide pass runs **before**
   `setup_lighting` (`:1324`), so a naively-named floor gets hidden by the
   repo's own defenses. §11's discarded-probe lesson applies: scene bounds mean
   different things before and after the scene is dressed.
4. **Whether `compositing.shadow_opacity` becomes redundant** in floor mode —
   test it, do not assume. The kept look uses 0.35.
5. **Cost, measured:** one 2-frame probe dispatch (az 42 + 222, the standing
   preview pair) against the +10–30% estimate, recorded in
   `docs/cloud-smoke.md`.

After 3b: batch 4 (metal imperfections — needs Mark's pick of the imperfection
set plus an acceptance round, per the standing material rule), then the T-V2
sequencer. 3a's orbit generator and frame-count gate are prerequisites for that
sequencer, which is the first thing that will render a 300-frame single orbit.

## Exact next action

```
git push origin codex/studiomark-scene-prep     # 8e97a6b is committed, not pushed
```

Then start 3b at item 1 above — decide the matte mechanism before writing any
Blender code, because everything else depends on it.

## Standing constraints (unchanged)

- **All rendering on Modal, never local** (2026-09-20 ruling). USD 30/month
  ceiling; per-run estimates in each dispatch's `request.json`, measured seconds
  in `docs/cloud-smoke.md`. `cloud_authorized` stays hardcoded false — human
  authorization is a doc record, never a machine gate.
- **No threshold widened without new numbers.** 3a widened none: the
  frame-count check is an equality; 35 dB decode PSNR floor, 3× neighbour-
  outlier factor, IoU 0.98/0.995, MAE 0.01, p99 0.05 all stand.
- Material changes → new source `.blend` version + acceptance round (the latch
  lesson). Never in job manifests.
- "Looks good" ≠ formal acceptance for parity artifacts. Note the contrast:
  the video artifact above **was** explicitly accepted; the excavation-pit
  parity reports remain `awaiting_reference_acceptance`.
- Single upstream `origin`; the `main` worktree at
  `C:/Projects/msp-render-pipeline` has none of this branch.
- Python: always `./.venv/Scripts/python.exe`. Blender is not on PATH and local
  renders are banned. ffmpeg 8.1.1 is on PATH (encoding is local and allowed).
- `output/` is gitignored — read the run record, never assume reproducibility.

## Delegation record (orchestration doctrine)

- Implementation: `zai/glm-5.3-flash` through the ocx proxy, two rounds (initial
  + correction). **Proven** from 48 proxy-log rows resolving to
  `glm-5.3-flash`/provider `zai` in the dispatch window — not from the CLI's
  own echo, which is never proof.
- Adversarial review: `deepseek/deepseek-flash` in fresh context (diff + spec
  only, different vendor family), verdict **FIX-FIRST** with two blockers. Both
  were real: the duplicate gate keying on a different identity than the billable
  frame, and the lossy azimuth readback breaking 100/300-frame orbits.
- Gate: both blockers reproduced by import **before** being accepted and
  re-measured as closed after. The duplicate-azimuth regression test was
  mutation-tested — reverting the keying to the raw float fails exactly the two
  new tests, so they pin behaviour rather than shape.
- Trap worth knowing: `prove-served-model.sh --lane ocx` reports the **latest**
  matching row, so with parent turns interleaved it returned a false MISMATCH
  against `anthropic/claude-opus-5`. Tally the window's rows instead of trusting
  a single-row verdict.

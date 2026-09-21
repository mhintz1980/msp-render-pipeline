# Video pipeline — decision brief (T-V1)

Prepared 2026-09-17 for Mark, against his ruling that *"eventually we should be
getting into the video aspect of the pipeline and if environments will play more
of a factor"* (`docs/rl300-parity.md`, 2026-09-17 rulings).

**This brief contains no production code.** It contains measured numbers from
local probe renders (free), three costed options, the risks that would sink each
one, and one recommended T-V2 scope. **Nothing proceeds without Mark's pick.**
Zero Modal dispatch was performed; the cloud figures below are extrapolations
from the run already recorded in `docs/cloud-smoke.md`, clearly bounded as such.

---

## The short version

1. **Turntable loops are the right first product.** They need the least new
   machinery, they fit the backdrop ruling exactly, and they are what a web page
   or a portfolio actually uses.
2. **Environment walkthroughs over the current plates cannot be made to work**
   without new modelling. A photograph has no parallax. This is a geometry fact,
   not a tuning problem — details in §2.2.
3. **Product cinematics (focus pulls, light moves) are nearly free** and are the
   best value per line of new code, because the camera never moves.
4. **A 10-second shot costs about 8.5 hours locally** and **$9–$24 on Modal L4**.
   The cloud range is wide because the one recorded cloud run cannot be
   decomposed into per-frame cost; §4 says exactly why and what one $0.372 run
   would fix.
5. **Three real defects surfaced while measuring**, all in §6. One blocked T07
   (`render-report.json` written truncated on any real Blender — **since fixed**,
   §6.3, suite now 110 OK). One makes an
   untended 300-frame local render a one-in-a-million bet (an intermittent HIP
   driver crash). And one is the single biggest obstacle to a good-looking
   turntable: **three of the four background plates are not environment maps**,
   and using them as one makes the machine's brightness swing 2–3.6× around a
   single orbit. The repo already contains the fix.
6. **The good news nobody had measured:** sampling is deterministic. Two renders
   of the same camera, one cold and one warm, differ by at most **1/255**. Noise
   will not crawl, so flicker control is a lighting problem, not a sampling one
   (§8.1).

---

## 1. Owner rulings that bind this brief

| Ruling | Effect on video |
|---|---|
| *"the excavation pit is just a backdrop. I'll be using them from time to time and wanted to see how it rendered."* (09-17) | Plates are context, not composite-match deliverables. A video does **not** have to match a plate's camera. It also means no plate-driven camera move is owed to anyone. |
| *"'option A' is closer to the real size"* (09-17) | The excavation-pit job's camera (`distance_multiplier` 5.6, `target_offset_z` 0.85) is the ruled scale. Any video reusing that job inherits it; changing `distance_multiplier` for a dolly move would re-open a settled question. |
| Cloud spend needs a named per-run price and run count, recorded here and in `docs/cloud-smoke.md`, before dispatch | §4 names a price and a run count. It is an **ask**, not an authorization. |

---

## 2. Candidate products

### 2.1 Web / portfolio turntable loop — **recommended**

**What it is.** The machine rotating through 360° on a fixed elevation, seamless
loop, on a neutral sweep or transparent background. 10 s at 30 fps = 300 frames
= 1.2° per frame.

**What it's for.** The thing a product page, a trade-show screen, or a proposal
deck actually embeds. It answers "what does the whole machine look like" in one
asset instead of eight stills (P1–P8 exist precisely because one still cannot).

**Fit with the backdrop ruling.** Perfect. A turntable needs no plate as a
*backdrop* at all. It does need a plate-equivalent as a *light source*, and the
repo already has the right pattern for that — see §6.2.

**Why it's first.** `setup_camera` already takes `azimuth_deg` as a manifest
scalar (`render_worker.py:255`). A turntable is a loop over an input that
already exists. Nothing about the camera rig needs inventing.

### 2.2 Environment walkthrough / dolly over a backdrop plate — **recommend against**

**Why it does not work today, concretely.** The compositor fits the plate to the
render canvas once and holds it still:

```
bg_img = ImageOps.fit(bg_img, canvas_size, Image.Resampling.LANCZOS)
```
`composite_worker.py:203`

There is no path from camera state to plate transform, and there cannot be a
useful one, because **a single photograph carries no parallax**. Move the
rendered camera and the machine's perspective changes while the ground it stands
on does not. The machine reads as a sticker sliding across a photo — and it gets
worse the more the camera moves, which is the whole point of a dolly shot.

**And there is no room to pan.** The plates are *smaller* than the render canvas:

| Plate | Size | vs 1800×1250 canvas |
|---|---|---|
| `env_excavationPit-sunlit.png` | 1515 × 1038 | upscaled to fit |
| `env_studio-dark.png` | 1496 × 1051 | upscaled to fit |
| `env_studio-white.png` | 1800 × 1250 | exact, no margin |

A pan needs plate area outside the frame to move into. There is none; every
plate is already being enlarged to cover the canvas.

**What it would actually take.** Either (a) model the ground and mid-ground in
3D and use the photo only as a far backdrop, or (b) camera-project the plate
onto proxy geometry. Both are CAD/set-dressing work per environment, not
pipeline work, and both would have to be redone for every new plate. Against a
ruling that says plates are occasional backdrops, this is the worst
effort-to-value ratio of the three.

**The honest middle path,** if Mark wants environment video: keep the camera
locked and move something else — light, focus, or the machine. §2.3.

### 2.3 Short product cinematic (focus pull / light move) — **recommended as a stretch**

**What it is.** A locked camera; a 4–6 second move in *depth of field* or in
*environment rotation*. A focus pull racking from the camlock fittings back to
the pump end. A light sweep where the studio environment rotates 30° and the
highlight travels across the barrel.

**Why it is nearly free.** Both levers are already manifest scalars consumed
per-render:

- `camera.depth_of_field.f_stop` → `apply_depth_of_field` (`render_worker.py:956`),
  which also computes focus distance from the camera-to-target distance, so a
  static camera keeps focus coherent automatically.
- `lighting.hdri_rotation_deg` → the world mapping node's Z rotation
  (`render_worker.py:384`).

Animating either is interpolating one number per frame. No new camera maths, no
new lighting rig.

**Fit with the backdrop ruling.** Excellent — the camera never moves, so a
static plate stays legitimate. This is the *only* one of the three options that
can use the excavation-pit plate honestly as video.

---

## 3. Measured frame budget — local

All figures measured this session on the workstation GPU, **AMD Radeon 780M via
HIP**, Blender 5.1.1, from `jobs/rl300_02_studio-dark.json` at its production
settings (1800 × 1250, 96 samples, Cycles, OpenImageDenoise, AgX). Method and
reproduction in §8.

### 3.1 Per-frame cost around a turntable orbit

| Azimuth | Render | Scene prepare |
|---|---|---|
| 42° (the job's own) | **113.20 s** | 0.38 s |
| 132° | **92.19 s** | 0.33 s |
| 222° | **101.58 s** | 0.34 s |
| 312° | **99.63 s** | 0.32 s |

**Mean 101.65 s/frame. Range 92.19 – 113.20 s. Spread 1.23×. Stdev 8.70 s.**

This answers risk 4.3 directly: **render time varies by 23% around a single
orbit**, because different azimuths present different amounts of glossy metal and
different environment content to sample. Any per-frame timeout — especially a
cloud one — must be sized for the slowest azimuth, not the mean.

**Scene prepare is 0.38 s.** Loading the `.blend`, hiding isolators, applying
powder coat and metal finish, and building the world costs under half a second.
The render is >99% of the job. This has a design consequence in §5.

### 3.2 How cost scales with samples

| Samples | Render (az 42°) | s / sample |
|---|---|---|
| 32 | 55.25 s | 1.727 |
| 48 | 68.95 s | 1.436 |
| 96 | 113.20 s | 1.179 |

Least-squares fit over the three points:

> **render ≈ 25.8 s + 0.909 s × samples**

**About 25.8 s per frame is fixed** — BVH build, scene sync, and the
OpenImageDenoise pass — and is paid no matter how few samples you take. So
halving quality from 96 to 48 samples saves **39%, not 50%**, and dropping to 32
saves 51% for a visibly noisier image. There is no cheap win hiding in the
sample count.

### 3.3 What frame sequencing in one Blender session actually buys: 10.8%

Four frames rendered in a single Blender session, moving only the existing
camera object between them (`use_persistent_data` already `True`):

| Frame | Azimuth | Kind | Render |
|---|---|---|---|
| f000 | 42.0° | cold | 119.37 s |
| f001 | 42.0° | warm | 113.01 s |
| f002 | 43.2° | warm | 98.49 s |
| f003 | 44.4° | warm | 108.09 s |

**Warm mean 106.53 s vs cold 119.37 s — a 10.8% saving.** That is the whole
prize for keeping a session alive, and §6.1 explains why it is not worth
collecting. It is consistent with §3.1: prepare is 0.38 s, so there was never
much per-process cost to recover; the 25.8 s fixed term in §3.2 is BVH build and
the denoise pass, which are paid per *frame*, not per *process*.

### 3.4 Shot budgets, local

At the measured 101.65 s/frame mean:

| Shot | Frames | 96 spp | 48 spp |
|---|---|---|---|
| 10 s @ 30 fps | 300 | **8 h 28 m** | 5 h 45 m |
| 10 s @ 24 fps | 240 | 6 h 47 m | 4 h 36 m |
| 3 × 10 s @ 30 fps | 900 | **25 h 25 m** | 17 h 14 m |

### 3.5 Where local stops being practical

Two independent limits, and the second is the hard one:

1. **Wall clock.** A single 10-second shot occupies the only workstation for a
   full working day. Three shots is a working week. Preview work, review renders,
   and any other job queue behind it.
2. **Stability.** One render in twenty-two crashed this session with a HIP driver
   access violation (§6.1). At that rate a 300-frame sequence is expected to
   crash **about 14 times**, and the probability of all 300 frames completing
   untended is about one in a million.

**Practical local ceiling: roughly 100 frames** (about 2 h 50 m at 96 spp) — a
3-second loop, or a 100-frame test turntable, both of which run overnight and
survive a handful of retries. Beyond about 300 frames, local is the wrong tool
regardless of how patient anyone is.

---

## 4. Modal L4 extrapolation — bounded, not dispatched

**No cloud call was made.** Rates are the ones already recorded in
`docs/cloud-smoke.md:45-46`, checked against Modal's pricing page:
**L4 $0.000222/s, CPU $0.0000131/core/s, memory $0.00000222/GiB/s.** At the
execution bounds recorded in the same file (`cloud-smoke.md:38` — one L4, four
CPU cores, 16 GiB):

> all-in = 0.000222 + (4 × 0.0000131) + (16 × 0.00000222) = **$0.00030992 per second**

### 4.1 Why a single per-frame number cannot honestly be given

The only recorded L4 timing is run `cloud-v12-l4-20260914-05`: **render phase
259.1 s** (`docs/cloud-smoke.md:150-156`). That figure is the *whole Blender
subprocess* — `cloud_parity.py:110-114` times a `subprocess.run` covering
Blender startup, OptiX kernel compilation, loading `prepared.blend`, and
rendering one 900 × 625 / 48-sample frame.

I rendered **that same profile** locally this session for comparison:

| 900 × 625, 48 samples | Time |
|---|---|
| Local HIP (render phase only) | **29.53 s** |
| Modal L4 (whole cold process, recorded) | **259.1 s** |

The L4 is not 8.8× slower than a laptop GPU. **About 229 s of that 259 s is
fixed cold-container cost**, not sampling. Nothing in the record separates the
two, so any "L4 seconds per frame" figure quoted from existing evidence would be
invented. What follows are therefore explicit bounds.

### 4.2 Cost bounds for a 10-second shot (300 frames, 1800 × 1250, 96 spp)

| | Assumption | Per shot | 3 shots |
|---|---|---|---|
| **Floor** | L4 marginal render time equals the measured local 101.65 s/frame, all fixed cost amortized away | **$9.45** | $28.35 |
| **Ceiling** | every frame pays the full recorded 259.1 s cold-process time | **$24.09** | $72.27 |

Build/startup and provider infrastructure retries are additional, exactly as
`docs/cloud-smoke.md:42-44` notes for the single-run estimate.

The floor is deliberately conservative: it assumes an L4 is no faster at
sampling than an integrated Radeon 780M, which it almost certainly is not. The
true cost is likely near the floor — but "likely" is not a number I will put in
front of a spend decision.

### 4.3 The single biggest cost lever is batching, and it is worth ~$20 a shot

If each frame gets its own container, the ~229 s of fixed cost is paid 300 times:

> 300 × 229 s × $0.00030992 = **$21.29 of pure overhead per shot**

Batch 30 frames per container and it is paid 10 times: **$0.71**. Frame batching
is not an optimization to add later; it is the difference between the floor and
the ceiling above.

### 4.4 What the cloud actually buys: wall clock, not money

Ten parallel containers × 30 frames each ≈ 229 s startup + 30 × render. Even at
the pessimistic local render rate, that is **under an hour of wall clock for a
300-frame shot**, against 8 h 28 m locally. Money is roughly a wash against a
day of workstation time; **elapsed time is the whole argument.**

### 4.5 The measurement ask — named price, one run

To convert the $9–$24 range into a measured number, one run is needed: **a
single container rendering 10 consecutive frames at production settings**,
bounded by the existing 1,200 s function timeout.

> **Ask: one (1) Modal run, ceiling USD 0.372.**

That ceiling is the figure already recorded in `docs/cloud-smoke.md:42` for a
full-timeout allocation, and it is an estimate, not a billing cap. It yields the
L4's real marginal per-frame cost and its real cold-start cost, separately.

**This is a request. It is not authorization, and nothing dispatches until Mark
names the price and the run count in `docs/cloud-smoke.md` the way the 09-13 and
09-15 quotes are recorded.** `cloud_authorized` stays hardcoded false.

---

## 5. What the current code gives for free

| Already there | Why it matters for video |
|---|---|
| **Parametric camera.** `azimuth_deg`, `elevation_deg`, `focal_length_mm`, `distance_multiplier`, `target_offset` are manifest scalars solved by `setup_camera` (`render_worker.py:253-286`). | A turntable is a loop over an existing input. The camera rig needs no new maths. |
| **Plate-as-HDRI lighting.** The world is built once in `setup_lighting` and costs nothing per frame. | Lighting carries to every frame at zero marginal cost. |
| **Fixed sampling seed.** `cycles.seed = 0`, `use_animated_seed = False` — verified in a live Blender session. `render_worker.py` never touches either. | The *correct* default for flicker, and **measured to hold**: two renders of the identical camera — one in a cold process, one warm in a later session — differ by a maximum of **1/255** across the whole product interior, MAE 0.000 (§8.1). Sampling noise does not crawl. Currently undeclared and unpinned, which §6.4 addresses. |
| **Scene prepare is 0.38 s.** | Frames are effectively independent. No persistent-session renderer is needed — which matters, because §6.1 says a persistent session is actively dangerous here. |
| **DOF and environment rotation are per-frame scalars.** | Product cinematics (§2.3) need interpolation, not new features. |
| **`use_persistent_data = True`** already set (`render_worker.py:928`). | Whatever warm-frame saving exists is already switched on. |
| **The compositor is a pure function** of (beauty, mask, plate). | Per-frame compositing is a loop, not a redesign. |
| **ffmpeg 8.1.1 is on PATH.** | The encoder is an install away from being a pipeline step. |
| **`scripts/build_studio_softbox_env.py`** already generates a true 2048×1024 equirectangular light map. | The fix for §6.2 is already written; it just is not used by the turntable-relevant jobs. |

---

## 6. What is missing, and three defects found while measuring

### 6.1 An intermittent HIP driver crash — found live, changes the design

One of the twenty-two real renders this session died with:

```
Exception Code: 0xC0000005
... amdhip64_6.dll ... hipHccModuleLaunchKernel()
```

No output was written; the process segfaulted mid-render. It used the same code
path as the twenty-one that succeeded, so this is the GPU driver, not the
pipeline.

**Observed rate: 1 in 22 renders (≈4.5%).** Over 300 frames that is ~14 expected
crashes; the chance of an untended clean run is about one in a million.

**Design consequence, and it is the important one:** every frame must be its own
process, with its own retry, and the sequence must be **resumable** — a crash at
frame 250 must not cost frames 0–249. Because prepare is only 0.38 s (§3.1),
per-frame process isolation costs almost nothing.

**Do not build a persistent in-session frame renderer.** §3.3 measures what one
would buy: **10.8%**. Against that, a persistent session loses every completed
frame in it on each crash, at a 4.5% crash rate. The trade is not close. Write
each frame to disk as it finishes and let the next frame start from a clean
process.

### 6.2 The plates are not environment maps, and a moving camera exposes it

`setup_lighting` loads the plate into a `ShaderNodeTexEnvironment`
(`render_worker.py:374-376`) and never sets `projection`, so Blender's default
applies — verified in a live session: **`EQUIRECTANGULAR`**, which expects a
2:1 image covering 360° × 180°.

| Plate | Aspect | True equirectangular? |
|---|---|---|
| `env_studio-dark.png` | 1.423 : 1 | **no** |
| `env_excavationPit-sunlit.png` | 1.460 : 1 | **no** |
| `env_studio-white.png` | 1.440 : 1 | **no** |
| `env_studio-softbox.png` | **2.000 : 1** | **yes** |

Three of the four are ordinary photographs being wrapped around a sphere as if
they were 360° panoramas. **At one fixed camera angle this is invisible and
frankly it is good art direction** — it is why the stills look photographed.
Rotate the camera and it stops being invisible: the reflections sweep through a
stretched projection, the machine at the back of the orbit is lit by a different
region of the same photo, and the photo's left/right edge seam passes through
the reflections once per revolution.

**Measured on the four orbit renders.** Product-interior luminance (8-bit, over
pixels with alpha > 250), from the same `studio-dark` job at four azimuths:

| Azimuth | Mean luma | Median luma | p95 | Product coverage |
|---|---|---|---|---|
| 42° | 104.73 | 129.47 | 165.77 | 0.4197 |
| 132° | 78.04 | 75.25 | 160.54 | 0.4417 |
| 222° | **51.95** | **36.00** | 118.46 | 0.4271 |
| 312° | 77.11 | 82.17 | 153.76 | 0.4326 |

**Mean brightness swings 2.0× around the orbit; the median swings 3.6×** (129.5
at the front, 36.0 at the back). Coverage barely moves (0.420–0.442), so this is
not a framing effect — **it is the machine itself going dark**. Some of that is
legitimate (a machine lit from one side *is* darker from behind), but a swing
this large on a plate that is not a real 360° environment means a `studio-dark`
turntable would visibly pulse bright-to-nearly-black once per revolution.

**The fix already exists in this repo.** `jobs/rl300_04_studio-white.json`
demonstrates the correct pattern: a purpose-built equirectangular map for
*lighting* (`env_studio-softbox.png`, built by
`scripts/build_studio_softbox_env.py`, whose own docstring explains why a
featureless backdrop makes metal read as flat plastic) and a *separate* plate for
the backdrop. That is exactly what a turntable requires, and the builder is
parametric over azimuth and elevation already.

**A turntable must use the two-map pattern.** Reusing `studio-dark`'s single
photo as both light and backdrop would produce lighting that visibly breathes
around the orbit.

### 6.3 `render-report.json` is written truncated on any real Blender — blocks T07

Found by setting `require_gpu` on a local render to obtain T04's timing report.
`render_worker.py:1126`:

```python
"build": getattr(bpy.app, "build_hash", None) or "unknown",
```

`bpy.app.build_hash` is **`bytes`** in Blender 5.1.1 (verified directly:
`b'b70da489d7f4'`). `json.dump` raises `TypeError` partway through writing, so
`render-report.json` lands **truncated at 158 bytes**, ending mid-key at
`"build": `, and `execute_render_job` aborts before its success line. The render
itself completes; only the report is destroyed.

Every other caller in the repo already handles this —
`scripts/cloud_blender_probe.py:77`, `scripts/prepare_scene.py:212`,
`scripts/verify_scene.py:327`, `:329`, `:603` all use `.decode()`.
`render_worker.py` is the only one that does not.

**Why 106 green tests missed it:** `tests/test_remote_job.py:378` stubs
`bpy.app` with `build_hash="stub-build"` — a `str`. The stub is the only thing
that has ever exercised this path, so it cannot catch a bytes value.

This gated T07 independently of video: a billable Modal dispatch would have
returned an unreadable result contract.

**Fixed 2026-09-17, after this brief was drafted** (so §11's probe record
describes the broken behaviour as encountered). `_build_hash_text()` decodes
bytes, passes a `str` through unchanged, and keeps the `"unknown"` fallback; the
report is now serialised with `json.dumps` **before** the file is opened, so a
serialisation failure raises without leaving a partial report on disk — which
matters because `_collect_artifacts` deliberately excludes
`render-report.json` from artifact hashing, so nothing downstream would catch a
truncation. The test stub is now `bytes`, and four regression tests cover it;
both fixes were mutation-tested. Suite 106 → **110 OK**, and the fix was verified
against real Blender 5.1.1: a 298-byte valid report carrying
`"build": "b70da489d7f4"`, with the success line printing for the first time.

### 6.4 Genuinely absent machinery

| Missing | Detail |
|---|---|
| **Frame sequencing** | Nothing in `docs/job_manifest.schema.json` expresses a shot. `output` carries `width`/`height`/`samples`/`engine`/`denoiser`/`passes`/`output_dir` and nothing else — no fps, no frame count, no per-frame parameter curves. `render_worker.py` contains no occurrence of `frame`, `fps`, or `animation`. |
| **Encoder** | No codec or container anywhere in the repo. **And Blender's built-in FFmpeg writer cannot be used**: the composite happens *outside* Blender, in `composite_worker.py`. Frames must land as PNGs, be composited in Python, and *then* be encoded. An external ffmpeg step is structurally required, not a preference. ffmpeg 8.1.1 is already on PATH. |
| **Flicker control** | The seed is constant by default (good) but undeclared, unpinned, and untested — nothing stops a future change from enabling `use_animated_seed` and introducing crawling noise. OpenImageDenoise runs **per frame, independently**, with no temporal input; this is the principal flicker risk and §7.1 is the probe for it. AgX with fixed exposure is a deterministic per-frame transform and is safe **provided `color.exposure` is not animated** — animating it would re-grade every frame independently and is the one colour change that must be forbidden. |
| **Parity gating that scales** | §7. |

---

## 7. Replacing per-frame parity gates

Full per-frame reference digests do not scale: 300 frames would need 300
reference renders, 300 stored references, and a comparison pass per frame — more
expensive than the shot itself, and it would gate on GPU nondeterminism that
`docs/rl300-parity.md` already established is the wrong comparator.

Proposed five-layer replacement, cheapest first. Current thresholds
(`scripts/verify_scene.py:24-26`, `composite_worker.py:281-291`) are reused
unchanged wherever they still apply.

**1. Per frame, always — the product integrity gate.** Keep T05's fidelity gate
on every single frame: every fully-opaque machine pixel in the composite must
match the render exactly, checked on the **reloaded saved file**. It is a numpy
compare on arrays already in memory, it is the gate that guarantees marketing
never altered the machine, and it must not be sampled. The mask-consistency gate
(IoU ≥ 0.98, bbox within 2 px) likewise runs per frame and keeps reporting
`None` rather than an unmeasured pass when no mask file is supplied.

**2. Once per shot — structural parity.** Materials, geometry, resolution,
samples, and colour management are identical across frames by construction.
Verify the full structural comparison once at frame 0 and assert the manifest
hash is unchanged for the rest. Per-frame structural checks would measure the
same thing 300 times.

**3. Sampled — full image metrics.** Run the complete reference comparison (mask
IoU ≥ 0.995, coverage delta ≤ 0.005, linear RGB MAE ≤ 0.01, p99 ≤ 0.05) on a
declared sample: first frame, last frame, and every 30th — 11 of 300. The sample
set must be **declared in the manifest and fixed**, never chosen after the fact,
or it becomes a way to miss failures on purpose.

**4. Whole-sequence statistics — cheap per frame, and it catches what stills
never could.** Record four scalars per frame (product coverage from the alpha,
mean and p95 interior luminance, and MAE against the previous frame), then gate
the **sequence**, not the frame:

- *Coverage and luminance must vary smoothly.* Gate on the maximum absolute
  second difference across the sequence. A spike means a frame lost geometry,
  the camera jumped, or the lighting popped.
- *Frame-to-frame MAE must stay under a ceiling scaled to the angular step,* and
  no single frame may exceed its neighbours' median by a declared factor. That
  outlier is the flicker signature.
- *No duplicate consecutive pixel digests* (a stalled sequencer silently
  emitting the same frame) and *no missing frame indices*.

These four numbers are what a video can be wrong about and a still cannot. They
are the real reason per-frame digests are the wrong tool, not just an expensive
one.

**5. After encoding — decode-back integrity.** Decode the sampled frames from
the finished file and compare against the composited PNGs. The codec is lossy,
so this gates on a declared PSNR/MAE floor, **not** byte equality. This carries
forward T05's established principle — *gate the bytes the client will actually
open* — to the one artifact the client actually receives.

---

## 8. Risks, and what the probes already settled

| # | Risk | Status |
|---|---|---|
| 8.1 | **Temporal denoise flicker.** OIDN runs per frame with no temporal input. | **Largely settled — good news, detail below.** |
| 8.2 | **HDRI-plate reflections under camera motion.** | **Settled — it is a real defect, and it is the big one, §6.2.** Three of four plates are not equirectangular; product brightness swings 2.0× (mean) and 3.6× (median) around the orbit. Mitigation already exists (`build_studio_softbox_env.py`, the two-map pattern from `studio-white`). |
| 8.3 | **Render-time variance across an orbit.** | **Measured: 1.23× (92.19–113.20 s), stdev 8.70 s.** Size cloud per-frame timeouts on the slowest azimuth, not the mean. |
| 8.4 | **GPU stability over long sequences.** | **Measured: 4.5% crash rate, §6.1.** Forces per-frame process isolation and resumability. Not on the original risk list; it is now the one that most shapes the sequencer's design. |
| 8.5 | **Cloud per-frame cost is unknown.** | **Bounded, not resolved, §4.** One $0.372 run closes it. |

### 8.1 in full — the denoiser is not the problem, the lighting is

Two controls were rendered in one session: the same azimuth twice (determinism),
then two steps at the true 300-frame turntable cadence of 1.2°.

| Pair | Δ azimuth | MAE | p99 | max | interior pixels changed >1/255 |
|---|---|---|---|---|---|
| f000 → f001 (**determinism control**) | 0.00° | **0.000** | 0 | **1** | **0.0%** |
| f001 → f002 | 1.20° | 6.353 | 111 | 237 | 46.9% |
| f002 → f003 | 1.20° | 6.303 | 110 | 234 | 46.0% |

*(8-bit levels, over pixels whose alpha exceeds 250 in both frames. f000 was
rendered by a cold process, f001 warm in a later session.)*

**The determinism control passes.** A maximum difference of one 8-bit level
across the entire product, at MAE 0.000, is last-place rounding — not resampling
noise. With `seed = 0` and `use_animated_seed = False`, Cycles reproduces a
frame across processes. **So no flicker in a turntable can come from random
sampling**, and the fixed-seed policy just needs pinning (§6.4) rather than
inventing.

**The two motion steps are near-identical to each other** (MAE 6.353 vs 6.303,
p99 111 vs 110). That consistency is the useful result: frame-to-frame change is
dominated by smooth geometric motion with no outlier, which is exactly the
baseline a sequence-level gate should be tuned against.

**But the magnitude is large** — p99 of ~110/255, with ~46% of the product
changing per frame. That is specular metal sweeping 1.2°, and it means an
*absolute* per-frame difference threshold would be useless. The gate must key on
a frame being an **outlier relative to its neighbours** (§7.4), not on crossing
a fixed number.

**What remains open** is the interaction of OIDN with the §6.2 lighting swing:
these three frames span 2.4° of a 360° orbit, in the bright front sector. The
back sector, where median luminance falls to 36/255, is where a per-frame
denoiser has the least signal and is most likely to produce visible pumping.
That is a 60-frame probe in the dark sector, not a full shot — folded into T-V2.

---

## 9. Recommended scope — T-V2

> **A 100-frame local turntable proof, on the two-map lighting pattern, with a
> sampled-and-statistical gate and an ffmpeg encode step. No cloud spend.**

Deliberately **not** 300 frames, **not** cloud, **not** a manifest schema
redesign. It is the smallest thing that renders a real loop, exercises every
piece of new machinery once, and produces an artifact Mark can watch and judge —
inside the §3.5 local ceiling, at about 2 h 50 m of unattended render time.

**Scope**

1. A turntable job built on the `studio-white` two-map pattern (§6.2): the
   existing equirectangular softbox map for lighting, a neutral sweep for
   backdrop. 100 frames, 3.6° apart, 1800 × 1250 at 96 samples.
2. A frame sequencer that renders **one frame per Blender process**, records the
   four per-frame scalars from §7.4, and is **resumable** — re-running skips
   frames already on disk with a valid digest (§6.1 makes this mandatory, not
   optional).
3. Per-frame composite through the existing T05 gates, unchanged.
4. Encode with ffmpeg to H.264 MP4 and a VP9/WebM for web, plus decode-back
   integrity on the sampled frames (§7.5).
5. A **60-frame dark-sector probe run first** and reported before the full loop:
   frames through the azimuths where §6.2 measured product median luminance
   falling to 36/255. That is where a per-frame denoiser has least signal and
   where pumping, if it exists, will appear. If it does, the lighting map changes
   before the sequencer is finished.
6. Manifest additions confined to a new optional `sequence` block. **The `output`
   block is not touched**, so every existing job and every accepted hash is
   unaffected.

**Acceptance criteria** — in the style of `docs/rl300-parity.md` §"Run and
acceptance":

Prerequisites: the worktree `.venv` with `requirements-test.txt` installed, and
the interpreter named by absolute path (`./.venv/Scripts/python.exe`) — the
system Python reports phantom pre-existing failures. Run from **PowerShell**,
not Git Bash.

1. **The dark-sector probe is rendered, measured and reported before the full
   loop is run.** Sequence statistics through the low-luminance azimuths show no
   frame that is an outlier against its neighbours by more than the declared
   factor. If one appears, the run stops and the lighting map is revised — a
   pumping turntable is not fixed by a threshold.
2. **All 100 frames present,** contiguous indices, no duplicate consecutive
   pixel digests.
3. **Every frame passes the T05 product integrity gate** — max difference 0 on
   fully-opaque product pixels, measured on the reloaded saved file. A vacuous
   comparison (zero opaque pixels) is a failure, not a pass.
4. **The declared sampled frames pass the unchanged thresholds:** mask IoU
   ≥ 0.995, coverage delta ≤ 0.005, linear RGB MAE ≤ 0.01, p99 ≤ 0.05. The
   sample set is fixed in the manifest before the run.
5. **Sequence statistics within declared limits** (§7.4), with the limits
   recorded in this document at the time they are set — **no threshold is
   widened because a run missed it; bring numbers.**
6. **Decode-back integrity** on sampled frames meets the declared floor.
7. **Resume works, proven adversarially:** kill the sequencer mid-run, re-run,
   and the completed frames are not re-rendered and the finished sequence is
   identical to an uninterrupted one.
8. **The suite stays green** (`./.venv/Scripts/python.exe -m unittest discover -s tests`),
   with new tests covering the sequencer and the sequence gates.
9. **Exit 0 means an `awaiting_owner_review` artifact was produced.** As
   everywhere else in this pipeline, **there is no automatic approval path**:
   Mark watches the loop and accepts or rejects it. A passing gate is not an
   acceptance, and this brief's recommendation is not one either.
10. **Zero Modal dispatch.** `cloud_authorized` stays hardcoded false.

**What T-V2 explicitly does not do:** no cloud, no 300-frame shot, no
environment walkthrough, no change to the `output` manifest block, and no change
to any accepted hash. (§6.3 was carved out as its own task and has since landed;
it is no longer a T-V2 concern.)

---

## 10. Decision requested

| | Option | Cost | Recommendation |
|---|---|---|---|
| **A** | T-V2 as scoped above — 100-frame local turntable proof | ~3 h render, no spend | **Recommended** |
| **B** | A + the §4.5 metered cloud run to price a real shot | A + **one run, USD 0.372 ceiling** | Recommended only if a full 300-frame shot is wanted soon |
| **C** | Product cinematic (§2.3) instead of a turntable | Comparable; fewer unknowns, less reusable | Reasonable if a plate-based video matters more than a loop |
| **D** | Environment walkthrough (§2.2) | New modelling per plate | **Recommend against** — a photograph has no parallax |

**Nothing proceeds until Mark picks.** Option B additionally requires his named
price and run count recorded in `docs/cloud-smoke.md`, per the standing rule.

---

## 11. Probe record

All probes local and free. Evidence under `output/probe-tv1/` (gitignored, as
all `output/` is). Source job `jobs/rl300_02_studio-dark.json`, unmodified in the
repo; probe manifests were generated copies varying only azimuth and samples,
with compositing disabled.

| Probe | Settings | Result |
|---|---|---|
| Orbit × 4 | 1800×1250, 96 spp, az 42/132/222/312 | 113.20 / 92.19 / 101.58 / 99.63 s (§3.1) |
| Sample scaling × 2 | 1800×1250, az 42, 48 and 32 spp | 68.95 s / 55.25 s (§3.2) |
| Cloud-parity profile | 900×625, 48 spp (matches `verify_scene.py:144`) | 29.53 s (§4.1) |
| Warm sequence, 1st attempt | 1800×1250, 96 spp, 4 frames one session | **crashed** — HIP `0xC0000005` (§6.1) |
| Warm sequence, 2nd attempt | as above | **discarded — probe defect, see below** |
| Warm sequence, corrected | as above | 119.37 cold / 113.01 / 98.49 / 108.09 warm (§3.3, §8.1) |
| Orbit luminance | the four orbit beauties | mean luma 104.73 / 78.04 / 51.95 / 77.11 (§6.2) |
| `build_hash` type | `blender -b --python-expr` | `bytes`, `b'b70da489d7f4'` (§6.3) |
| Env projection default | `ShaderNodeTexEnvironment.projection` | `EQUIRECTANGULAR` (§6.2) |
| Plate aspects | Pillow | 1.423 / 1.460 / 1.440 / **2.000** (§6.2) |

**Totals: 22 render invocations, 1 hard crash (§6.1). No Modal dispatch.**

**Timing method.** Render time was isolated from scene preparation by wrapping
`bpy.ops.render.render` in the probe driver. **`render_worker.py` was not
modified**; the driver swapped the module's `bpy` reference for a transparent
proxy whose only behavioural difference is a stopwatch. `require_gpu` was
deliberately omitted from the timing probes after §6.3 made its report path
unusable; HIP device selection was confirmed from the worker's own log line
(`GPU backend HIP: ['AMD Radeon 780M Graphics']`) on every run.

**A discarded probe, recorded because the trap is reusable.** The second warm
run produced a *spectacular* apparent result — warm frames at 34 s against 123 s
cold, an apparent 3.6× speedup. It was wrong. The driver re-derived the orbit
centre by calling `get_scene_bounds()` *after* the render, and by then
`setup_lighting` has added a `GroundShadowCatcher` plane sized `radius * 14`
(`render_worker.py:343`). The returned radius was the plane's, so the camera
flew out and the "warm" frames rendered the product at **0.8% coverage instead
of 42%** — a nearly-empty frame, rendered fast. The corrected driver captures
the real basis by intercepting the worker's own `setup_camera` call, and
reproduces `radius = 1.6463`, matching `docs/rl300-parity.md:1025` exactly.
Coverage then holds at 0.4197 / 0.4197 / 0.4229 / 0.4258 across the sequence,
and the real saving is 10.8%.

The general lesson, which is the same one `hide_misplaced_isolators` taught:
**scene bounds mean different things before and after the scene is dressed.**
Measure against the basis the worker actually used, not one re-derived later.

---

## 12. Decision record, 2026-09-20

Mark decided, and it supersedes the local-first framing above:

> *"no videos locally. Always in Modal. There is $30 per month free usage
> and it's way faster. This laptop can't handle it well."*

- The pick is **A, on Modal**: the turntable proof proceeds, with every frame
  rendered in the cloud. Sections 3.4-3.5 (local shot budgets and the local
  ceiling) are now historical measurement, not the plan; section 6.1's
  per-frame process isolation carries over unchanged, and section 4.3's
  batching analysis is promoted from optimization to core sequencer
  constraint: batch ~30 frames per container or pay ~$21/shot in cold starts
  against the $30/month ceiling.
- The standing spend rule is satisfied at policy level by the $30/month
  ceiling recorded in `docs/cloud-smoke.md` ("2026-09-20 authorization"),
  with per-run estimates and measured seconds recorded per dispatch.
- First dispatch under the ruling: a 2-frame environment preview
  (`scripts/cloud_job_render.py`, azimuths 42 and 222 of the two-map
  `studio-white` pattern) so Mark can judge photorealism before any
  sequencer exists. The 222 frame doubles as the first evidence that the
  two-map pattern holds the back-of-orbit lighting that section 6.2 measured
  collapsing to 36/255 under a single plate.

---

## 13. Batch 3 replanned, 2026-09-20 — split into 3a and 3b

The 2026-09-20 handoff scoped batch 3 as a single task: "replace the flat
composite backdrop with a real rendered floor." Reading the code before
writing it found three collisions that make the floor a *second* task, not a
first one, plus an owner ruling that outranks both. Batch 3 is therefore
split. **3a is pure local Python with zero cloud spend; 3b is the floor and
needs a measured dispatch.**

### 13.1 Why the floor could not go first — the matte carries the floor

The product matte is not a separate render pass. `write_matte_pass`
(`render_worker.py:1069-1107`) loads the finished `beauty.png` and takes
**channel 3 of its alpha** (`:1087`); `_assert_matte_matches` then proves the
saved matte equals that alpha. The whole pipeline's notion of "product pixels"
is "pixels where the beauty render is opaque", which works only because
`scene.render.film_transparent = True` is hardcoded at `render_worker.py:1331`
and nothing behind the machine is ever opaque.

Put an opaque floor in the scene and the floor is opaque, so every floor pixel
becomes "product". Three consequences, none of which fail loudly:

1. **The T05 fidelity gate stops meaning what it says.** It compares
   fully-opaque mask pixels against the reloaded save
   (`composite_worker.py:294-307`). With a floor in the mask it still passes —
   it is now also asserting the floor is unaltered, and no longer isolating
   the machine. The gate that exists to guarantee marketing never retouched
   the pump would be measuring the backdrop.
2. **`create_contact_shadow` casts a shadow from the floor's silhouette**, not
   the machine's — it takes the alpha mask as its only geometry input
   (`composite_worker.py:52-60`).
3. **The §7.4 coverage scalar goes blind.** Coverage is `mask.mean()`; a
   floor-bearing matte pins it near 1.0, and the smooth-variation gate on
   coverage then cannot detect a frame that lost the machine.

All three *pass*. That is the danger: the failure mode is a green suite
measuring the wrong thing, which is the same class of defect as the encoder
bug described in §13.2 — a gate pointed at the wrong artifact.

There is a fourth trap for whoever implements 3b: the ground-keyword hide pass
(`render_worker.py:1247-1279`) runs **before** `setup_lighting` (`:1324`) and
hides any mesh whose name contains `plane`, `plate`, `env`, `surface`, or that
is a large flat slab near z=0. A floor plane must therefore be created after
that pass (as `GroundShadowCatcher` already is) or it will be hidden by the
repo's own defenses. And `film_transparent` is currently controlled by no
manifest key at all.

### 13.2 What 3a fixes — the ruling, and the gate that missed it

Mark's 2026-09-20 ruling (recorded verbatim in `docs/rl300-parity.md`):
**no delivered video contains duplicated frames.** One orbit is one pass
through unique frames; looping is the player's job. A quality-check video
spends its budget on more unique frames, never on repeats.

The accepted artifact violated it because `scripts/probe_sequence.py:183`
passed `-stream_loop 4` to ffmpeg — `ffprobe` measures `nb_frames=150`, 12 fps,
12.5 s: 30 unique frames played five times.

The §7.4 duplicate-frame gate ran and passed **correctly** — it digests the
composited PNGs, which are genuinely all distinct. The duplication happened
downstream at encode, and the §7.5 decode-back check sampled 0/mid/last, all
inside the first pass. Deleting the flag fixes the instance; what makes it
unrepeatable is asserting, **on the encoded file**, that its frame count
equals the number of unique composited frames.

3a scope (local, free, no Blender, no Modal):

- `probe_sequence.py`: drop `-stream_loop`; add `encoded_frame_count()` via
  `ffprobe` with an `nb_read_frames` fallback; gate
  `ENCODED_FRAME_COUNT_MISMATCH`; add `--expect-frames` so a caller declares
  the intended count up front.
- `cloud_job_render.py`: add `orbit_azimuths(count, start)` generating one
  orbit with no repeat of the start frame, and `reject_duplicate_azimuths()`
  in preflight — a duplicate azimuth is a **billable** frame carrying no
  information against the USD 30/month ceiling, so it must cost nothing.
  Record `orbit` in `request.json`.
- `composite_worker.py`: add `MATTE_COVERAGE_CEILING = 0.90` and a
  `matte_plausibility_pass` gate folded into `gates_ok`. Grounding: every
  measured product coverage in this pipeline sits near 0.42 (0.4197–0.4442
  across a full orbit, §6.2 and §11), so 0.90 is more than double any
  legitimate value and cannot fire on a real product matte — it fires exactly
  when a matte has stopped describing the product, which is the in-scene-floor
  signature. **This is the tripwire that makes 3b's central risk loud instead
  of silent**, and it is why it ships before the floor rather than with it.

No threshold is widened: the new frame-count check is an equality, and the
35 dB decode floor, the 3× neighbour-outlier factor, IoU 0.98/0.995, MAE 0.01
and p99 0.05 all stand unchanged.

### 13.3 3b — the floor, still owner-relevant and now properly bounded

Unchanged in goal: a real rendered floor under the machine, killing the
machine-to-backdrop boundary artifact both vision reads flagged and making DOF
believable by putting something behind the machine to blur. What 3a changes is
that 3b can no longer do it silently wrong.

3b must resolve, with numbers rather than assumption:

1. **How the matte excludes the floor.** The floor is opaque, so alpha cannot
   separate it. This needs a real mechanism — a dedicated object-index /
   cryptomatte pass, or rendering the matte from a film-transparent pass with
   the floor hidden — and `write_matte_pass` currently supports neither. This
   is the actual engineering content of 3b and it was invisible in the
   handoff's framing.
2. **A manifest key for `film_transparent`**, since floor mode needs it false
   and every existing job needs it true. Additive and defaulted so no accepted
   hash moves.
3. **Where the floor plane is created** — after the ground-keyword hide pass,
   following the `GroundShadowCatcher` precedent, sized off the same radius
   basis the worker actually used (§11's discarded-probe lesson: bounds mean
   different things before and after the scene is dressed).
4. **Whether `compositing.shadow_opacity` becomes redundant** in floor mode —
   test, do not assume; the kept look uses 0.35.
5. **Cost**, measured: one 2-frame probe dispatch (az 42 + 222, the standing
   preview pair) against the +10–30% estimate, recorded in
   `docs/cloud-smoke.md` per convention.

Sequencing note: 3a's frame-count gate and orbit generator are also
prerequisites for the T-V2 sequencer, which is the first thing that will
render a 300-frame single orbit. Doing them now costs nothing and removes the
chance that the first expensive shot duplicates frames.

### 13.4 Batch 3b FINAL, 2026-09-21 — floor renders, 2-frame probe technically approved, owner look pending

The 3b mechanism landed and is measured in `docs/cloud-smoke.md`
("2026-09-21 batch-3b FINAL"): opt-in in-scene floor
(`lighting.floor.enabled` with `output.film_transparent=false`),
product-only matte from a second floor-hidden transparent render, byte-exact
floor-preservation gate, matte-plausibility tripwire, synthetic shadow
suppressed in floor mode. Three dispatch attempts: run1 passed, run2 failed
after 3.417 container-s (stale `camera.matrix_world` — projection ran before
the depsgraph update; fixed by updating the depsgraph before projection),
run3 passed. Run3 measured: warm az222 RENDER phase 11.27 s vs the 10.2 s
batch-1 warm baseline = **+10.5%, inside the declared +10-30% band**
(render phase vs render baseline only; frame totals are not compared against
it). All-attempt cost total 516.655 container-s ≈ USD 0.160 rate-derived,
**NOT billed**. Run3 passed `probe_sequence --expect-frames 2 --no-encode`
in `rendered_floor` mode; suite 211 tests OK
(`output/batch3b-tests-transform.log`).

**No encode was run and no full-orbit behavior is guaranteed from a 2-frame
probe.** The parent visually inspected both run3 `composite-lens.png` frames:
the run1 diagonal finite-floor edge is eliminated, the background is smooth,
shadows are grounded. That is **technical approval for the TWOFRAME probe
only** — owner look acceptance is pending.

Mask IoU correction: the 0.966/0.800 numbers are raw-mask vs raw batch-2 mask
measurements (not shifted composites, as earlier text wrongly said), and they
are incomparable by definition — batch-2 masks include the catcher contact
shadow, floor-mode masks are product-only (see
`output/batch3b-evidence-review-deepseek.txt`). Run record and next actions:
`HANDOFF-2026-09-21-batch3b.md`.

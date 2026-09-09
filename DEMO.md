# RL300-SAFE walkthrough

Three commands, about a minute each, on this laptop. No cloud, no internet.

---

## Before they arrive

```powershell
cd C:\Projects\msp-render-pipeline
.\demo\0-preflight.ps1
```

This renders nothing. It runs the test suite and checks that Blender, the CAD file
and both background plates are exactly where the manifests say. It ends with
**ALL CHECKS PASSED** or tells you what moved.

If you want the images already on screen as a fallback, run all three steps once
beforehand — the outputs stay in `output\` and the live run just overwrites them.

---

## Step 1 — The machine, no background

```powershell
.\demo\1-render-no-background.ps1
```

**Roughly 50 seconds.** Opens `RL300-SAFE-photoreal.blend` in headless Blender and
renders it with Cycles on a transparent film.

> "This is the CAD assembly our engineers already built, rendered straight out of
> the model. No background at all — just the machine and a matte. That transparent
> master is what everything else is built from, and it's the version marketing wants
> for a spec sheet or a web page."

Opens: `output\rl300_01_no-background\beauty.png`

Worth pointing out: it's a cut-out, and it's honest — a product shot, but it doesn't
look like it was taken anywhere.

---

## Step 2 — Same machine, lit by the environment

```powershell
.\demo\2-render-studio-background.ps1
```

**Roughly 60 seconds.**

> "Same model, same camera. The only thing I changed is one line of the job file:
> which photograph to use. That photograph gets loaded twice — once as the backdrop,
> and once as the *light source*. Cycles lights the machine using the photo itself,
> so those two warm pools of light in the studio are what's putting the highlight on
> the paint and the reflection on the floor. That's HDRI lighting, and it's the
> reason it stops looking like a render."

Opens: `output\rl300_02_studio-dark\final_rl300_02_studio-dark.png`

Point at:
- The warm rim down the left-hand flank — that comes from the light pool in the plate.
- The reflection under the skid on the wet floor.
- The contact shadow: dark and tight where the rails touch, feathering outward.

If they ask how you know the machine itself wasn't touched up: the console prints
**Product Fidelity Gate: PASS (100% exact machine pixels)**. Every fully opaque pixel
of the machine in the final image is byte-for-byte identical to the render. The
environment is composited around the machine, never over it.

---

## Step 3 — Different job site, same command

```powershell
.\demo\3-render-pit-background.ps1
```

**Roughly 50 seconds.**

> "Now the customer wants to see it on site instead of in a studio. I don't re-model
> anything and I don't book a photographer — I point the job file at a different
> photograph. The sunlight direction, the warm bounce off the sand, the colour
> temperature: all of that comes out of the plate automatically."

Opens: `output\rl300_03_excavation-pit\final_rl300_03_excavation-pit.png`

Point at:
- Sun direction on the machine matching the shadows already in the photo.
- Warm sand bounce filling the undercarriage instead of a black void.
- The scale reading correctly against the excavator buckets behind it.

---

## Optional step 4 — a completely different product

```powershell
.\demo\4-render-jgun.ps1
```

**Roughly 70 seconds.** `jgun-full.glb` is a ~250 mm pneumatic torque wrench —
a hundred times smaller than the RL300 package, a different file format, and
36 raw CAD materials that had never been shaded.

> "Nothing in the pipeline was written for this tool. It's another job file."

This one has no background plate yet, so it stops at the transparent master.
Once a plate exists it becomes exactly the same three steps as the RL300.

**To add an environment for it,** you need a photograph with:
- a clear, unobstructed foreground surface in the lower third to stand the tool
  on — a workbench, a tool crib shelf, a pipeline flange, a rig deck;
- visible light sources or an obvious light direction, since the same image also
  becomes the light rig;
- roughly a 3:2 frame, at least 1800 px wide.

Save it as `backgrounds\env_jgun-<name>.png`, copy
`jobs\jgun_01_no-background.json`, and change three things: `lighting.hdri_path`,
`compositing.background_plate`, and `compositing.enabled` → `true`. Then tune
where it sits with `compositing.product_offset_pct`.

---

## The point to land

Every image is a JSON file plus a photograph. Nothing is hand-painted, so nothing
drifts: re-run the same job in six months and you get the identical image. New
colour, new angle, new job site, new product — that is a text edit and a minute of
compute, not a studio day.

The same three commands run unchanged on a cloud GPU (`dispatch-modal`) when a whole
product line needs doing at once.

---

## If something goes wrong

| Symptom | Fix |
|---|---|
| `WARNING CUEW initialization failed` scrolls past | Harmless and always present. Blender probes for an NVIDIA driver, doesn't find one on this AMD laptop, and uses HIP instead. Ignore it. |
| The previous image is still open in Photos | Handled. The compositor renames over the open file; if Windows refuses, it writes `..._01.png` and says so. |
| `Blender was not found` | `--blender-bin "C:\Program Files\Blender Foundation\Blender 5.1\blender.exe"` |
| `CAD source NOT FOUND` | The `.blend` moved. `cad\RL300-SAFE-photoreal.blend` in this repo is an identical copy — point `cad_source.file_path` at it. |
| A render is slow | The console prints its GPU backend. If it says *no GPU device enabled*, it is on CPU; drop `output.samples` to 48 for the demo. |
| Anything else | Show `output\` from the pre-run. The finished images are already there. |

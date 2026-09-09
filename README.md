# MSP Render Pipeline

Turns Myers-Seth Pumps CAD assemblies into finished marketing photography — without a
photo shoot, a studio booking, or a truck.

A job is one JSON file. It names the CAD model, the camera, the lighting, and the
background. Run it and you get a print-resolution image. Change the background line
and run it again, and you get the same machine on a different job site, correctly lit,
in under a minute.

```bash
python -m msp_render_cli run jobs/rl300_03_excavation-pit.json
```

---

## How it works

Three stages, each independently inspectable.

**1. Render.** Headless Blender opens the `.blend`, applies the shading and lighting
described by the manifest, and renders with Cycles onto a *transparent film*. The
output is a cut-out of the machine — no floor, no backdrop — plus its alpha matte.
Because the background is transparent, one render is reusable against any plate.

**2. Light from the plate.** When a job sets `lighting.hdri_path`, the background
photograph is loaded as the world environment texture. Every reflection on the
paint, every bounce of light into the undercarriage, and the colour temperature of
the whole machine then come from the photograph it is about to be placed into. This
is the single biggest contributor to an image reading as *photographed* rather than
*rendered*, and it is why steps 2 and 3 of the demo look real while step 1 looks like
a product cut-out.

**3. Composite.** `composite_worker.py` seats the render on the plate and synthesizes
a two-tier ground shadow — a tight dark contact line under the skid rails, and a
softer directional penumbra cast along the ground. It then runs a **Product Pixel
Integrity Gate**: every fully opaque machine pixel in the output is compared against
the render, and the job fails if a single one drifted. Marketing can retouch the
environment; it can never accidentally alter the machine.

---

## Layout

```
jobs/          the three demo manifests - this is what you edit
backgrounds/   background plates, used as both HDRI and backdrop
cad/           in-repo copy of the RL300-SAFE photoreal .blend
demo/          numbered PowerShell scripts for the live walkthrough
output/        renders land here (git-ignored, always re-creatable)
docs/          manifest JSON schema + photoreal calibration notes
archive/       superseded files, kept for reference only
render_worker.py      runs inside Blender: geometry, shading, lighting, camera
composite_worker.py   plate compositing + the pixel integrity gate
msp_render_cli/       the CLI
```

## Requirements

- **Blender 5.x** — found automatically in `C:\Program Files\Blender Foundation\`;
  override with `--blender-bin` or the `MSP_BLENDER_BIN` environment variable.
- **Python 3.11+** with `numpy` and `Pillow`.
- A GPU is optional. Cycles uses OPTIX, CUDA, HIP or oneAPI if present and falls back
  to CPU otherwise; the worker prints which one it chose.

## Commands

| Command | What it does |
|---|---|
| `presets` | List the camera, livery, and lighting presets |
| `validate <job>` | Pre-flight: schema, plus every file the manifest references, plus Blender |
| `render <job>` | Blender Cycles render → transparent `beauty.png` + `mask.png` |
| `composite <job>` | Seat an existing render on the manifest's background plate |
| `run <job>` | `render` then `composite` |
| `new-job` | Scaffold a fresh manifest |
| `dispatch-modal <job>` | Same render on a cloud L4 GPU instead of locally |

Always start with `validate` — it catches a moved CAD file or a renamed plate in two
seconds, instead of two minutes into a render.

## Running the demo

```powershell
.\demo\0-preflight.ps1              # verify everything, renders nothing
.\demo\1-render-no-background.ps1   # transparent cut-out
.\demo\2-render-studio-background.ps1
.\demo\3-render-pit-background.ps1
```

See **[DEMO.md](DEMO.md)** for the walkthrough script and what to say at each step.

## Adding a new environment

1. Drop the plate into `backgrounds/`.
2. Copy the closest job in `jobs/`, then point both `lighting.hdri_path` and
   `compositing.background_plate` at the new file.
3. `validate`, then `run`.

Seat the machine on the plate with `compositing.product_offset_pct` — a fraction of
the canvas, so placement tuned on a fast low-resolution preview lands identically on
the full-resolution final. Resize it with `camera.distance_multiplier` rather than
`product_scale`, so the render is never resampled.

## Tests

```bash
python -m unittest discover -s tests -v
```

Covers the colour-space conversion, camera solving, manifest validation, and the
compositor: shadow anchoring, placement, plate fitting, and the pixel integrity gate.

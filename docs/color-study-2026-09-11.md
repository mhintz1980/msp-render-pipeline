# RL300 colour study — 2026-09-11

## Decision and limits

Keep AgX / Medium High Contrast and change the studio-dark job exposure from
-0.15 to -1.5 for the next owner-review candidate. Do not change the source
`.blend`, paint base colour, lighting, or powder-coat parameters. This is a
display-exposure correction supported by a controlled experiment, not a
calibrated paint-colour match or visual acceptance.

Mark selected studio-dark as the sole formal parity reference. Sunlit output is
additional visual evidence only. The parity schema and owner-acceptance meaning
are unchanged; no cloud spending is authorized.

## Controlled experiment

Local artifacts: `output/color-study-20260911/`. `driver.py` renders the current
v5 material and lighting at 900x625, 16 samples, CPU, seed 0, Blender 5.1.1
build `b70da489d7f4`, then saves the same Render Result through AgX, Standard,
and Filmic. `exposure.py` repeats that render and also exports AgX and Standard
at -1.5. `experiment.json` records the resolved manifest, source/worker hashes,
runtime, and initial view exports; `exposures.json` records the lower exposures.
`compare.py` produces composites and measurements in `comparison.json`.
These local diagnostic scripts and images are ignored evidence, not product code.

The experiment's saved manifest is authoritative for reproduction: it retains
the original -0.15 exposure even though the production job now uses -1.5.
The driver now reuses that saved manifest when it exists, rather than loading
the edited job. Every view in a given render shares the same
radiance, camera, material, lighting, alpha, and samples.

Measurements use the same fixed opaque rear-panel crop `(185,360)-(330,440)`,
11,600 pixels, in uncomposited PNGs. Saturation is `(max-min)/max` per pixel,
then averaged; clipping is the fraction of RGB channel samples equal to 255.

| View / exposure | Mean RGB | Mean saturation | Clipped channels |
|---|---|---|---|
| AgX / -0.15 | 205.69, 163.61, 67.42 | 0.6851 | 0% |
| Standard / -0.15 | 231.99, 185.88, 20.69 | 0.9032 | 18.29% |
| Filmic / -0.15 | 203.78, 178.52, 15.06 | 0.9207 | 0% |
| Standard / -1.5 | 159.04, 121.35, 9.75 | 0.9306 | 0% |
| AgX / -1.5 | 156.12, 114.70, 1.40 | 0.9827 | 0% |

The bright AgX transform contributes to the pale yellow, but replacing AgX is
unnecessary: lower exposure restores saturation without the Standard clipping
seen here. These numbers describe this crop, not the whole product or a physical
reflectance measurement. No claim of full-image highlight preservation follows
from the crop's zero clipping.

## Photographic comparison

Inspected the supplied white-sweep photograph and dark-studio image:

- `C:/Projects/work-assets/photograph-studio/rl-200-safe-back-iso-older-whtbkgrd.jpg`
- `C:/Projects/work-assets/Renderings/rl200-safe-iso-back-render-older-std-bkgrd.png`

Both show stronger yellow chroma than v5 and no clearly resolved orange-peel
texture at full-machine framing. Their illumination and colour treatment differ;
neither is a calibrated paint sample. The handoff's RGB samples are not a colour
target to fit exactly. The machine revisions also differ from this RL300 model.

## Sunlit evidence

`output/color-study-20260911/sunlit.py` builds an evidence-only manifest from the
revised studio job's source, material, colour and quality settings, plus the
existing sunlit job's camera, lighting and compositing settings. It enables the
shadow catcher explicitly and uses 900x625 / 48 samples. The derived manifest
is saved beside the output. The original sunlit job remains unchanged.

This checks the same finish in another environment; camera distance and placement
follow the sunlit composition, so it is not a pixel-matched environment A/B.
It is a local Windows render, not the isolated Linux parity proof.

The first `sunlit/` output used the studio exposure -1.5 and was too dark for
useful bright-environment review. The selected `sunlit-bright/` comparison uses
the sunlit job's original -0.3 exposure; AgX/look and the finish remain the same.
Run `sunlit.py` with `MSP_SUNLIT_VARIANT=sunlit-bright` and
`MSP_SUNLIT_EXPOSURE=-0.3` to reproduce into a fresh directory. Existing output
directories are deliberately refused. Both iterations are retained.

`saved-image-checks-bright.json` independently reloads the saved PNGs: both
studio and sunlit masks equal beauty alpha, all placed opaque product RGB pixels
match the saved composite exactly, and neither placement clips opaque product.
This does not assert that the compositor's general T05 contract is complete.

Selected sunlit composite SHA-256:
`e259060f2b6dc3e5ffdc00b1c908c2f38b0924d7973f84c16d7513cbafc4e640`.
Owner visual acceptance remains pending for both images.

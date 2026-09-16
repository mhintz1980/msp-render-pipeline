# RL300 white soft studio reference

The white studio is for appearance review: roughness, highlights, bevels and
colour against the standing professional photograph. The accepted studio-dark
v12 is the accepted T04 reference as of 2026-09-13; v6 is historical. These environments produce independent
reports; the white studio does not replace or revoke the dark acceptance.

## Job and plate

- Job: `jobs/rl300_04_studio-white.json`.
- Backdrop: `backgrounds/env_studio-white.png`, 1800x1250 RGB, a seamless neutral
  sweep ranging from byte 236 to 252 with no baked object or shadow.
  Regenerate: `./.venv/Scripts/python.exe scripts/build_studio_white_plate.py`.
- Lighting environment: `backgrounds/env_studio-softbox.png`, 2048x1024
  equirectangular, at strength 2.0 and rotation 0 degrees, alongside the existing
  `studio_white` analytic rig at intensity 0.7.
  Regenerate: `./.venv/Scripts/python.exe scripts/build_studio_softbox_env.py`.
- **The backdrop and the lighting environment are deliberately different files.**
  A backdrop wants to be featureless. Bare metal has no colour of its own - what
  you see is its surroundings - so lit by a featureless gradient the cast
  aluminium fittings reflected the same near-white in every direction and
  collapsed into flat pale grey. The softbox map gives them two bright sources, a
  top strip and a dark band to reflect; the dark band is what puts a shoulder on
  the highlight across a curved barrel.
- Both PNGs are authored LDR environments, not calibrated HDR panoramas. The
  renderer multiplies by `hdri_strength`, so the ratio between the sources and
  the walls is what carries the look, not the absolute values.
- Camera, source CAD, geometry settings and colour management match the accepted
  dark v6. AgX / Medium High Contrast / exposure -1.5 stays.
- The Cycles shadow catcher supplies the ground shadow. `shadow_opacity: 0`
  disables the compositor's additional synthetic shadow for this white job.

## Run the independent proof

Run in PowerShell from the repository root. Use a new output directory each time.
The preparation is reused because only the manifest and environment change; the
verifier checks the original and prepared scene hashes before rendering.

```powershell
./.venv/Scripts/python.exe scripts/verify_scene.py `
  --job jobs/rl300_04_studio-white.json `
  --preparation-report output/verification/rl300-prepared-v1/grounded-preparation-20260911-v6/preparation-report.json `
  --linux-runtime /home/markimus/.cache/studiomark/blender-5.1.1-20260910/blender-5.1.1-linux-x64 `
  --output-dir output/verification/rl300-prepared-v1/parity-20260913-studio-white-metal `
  --timeout 600
```

Omitting `--job` retains the studio-dark default. The proof still uses 900x625,
48 samples, Cycles CPU and the pinned Linux Blender 5.1.1 build. The job's normal
render remains 1800x1250 / 96 samples. No threshold or report schema is widened.

Relative job and asset paths resolve from the repository root; absolute paths
are also accepted. This verifier requires the job's CAD source to match the
preparation report, enabled compositing, unit product scale and zero pixel
offsets. Percentage offsets remain supported. Unsupported combinations fail
explicitly instead of substituting another input.

The lighting environment and the backdrop may name different files. When they
do, both are copied into the sealed payload — as `/input/environment_light.png`
and `/input/environment.png` — and both are hashed into `inputs.json`, so
neither can be swapped inside the probe. When they name the same file, exactly
one image is staged as before, which is why the studio-dark anchor's payload and
hashes did not move.

## Full-resolution render for appearance review

The verifier's proof is 900x625 at 48 samples. That is the right size for a
parity gate and the wrong size for judging a finish — it gives roughly 4 mm per
pixel. Judge appearance on the production render instead:

```powershell
./.venv/Scripts/python.exe -m msp_render_cli run jobs/rl300_04_studio-white.json
```

Rendered 2026-09-13 on the host Blender 5.1.1 (`b70da489d7f4`), HIP / AMD Radeon
780M, 1800x1250 at 96 samples. The compositor's product fidelity gate passed at
100% exact machine pixels, maximum pixel drift 0.

| Full-resolution artifact | Decoded-pixel SHA-256 |
|---|---|
| `output/rl300_04_studio-white/beauty.png` | `caa82b377651529a322dad630389328231e8e8139096979f234436bea9d83afe` |
| `output/rl300_04_studio-white/mask.png` | `f18f9720b59c18a9a63117cf3bfe4eec55caff6ad881eb6ca40b42ad798e7f71` |
| `output/rl300_04_studio-white/final_rl300_04_studio-white.png` | `756ea9333c5d9115175c89856318109e2ccbeb90358ed5d4f8d660ff882832b8` |

These are pixel digests, not file hashes — see the note on render metadata in
[the parity record](rl300-parity.md#png-file-hashes-are-not-a-parity-comparator).
This render is host-side and GPU-accelerated, so it is **not** parity evidence;
the gating proof remains the isolated Linux CPU run above.

`[MSP Render] Bevel shading injected into 0 materials` in that log is expected,
not a regression: every material in `RL300-SAFE-photoreal.blend` already carries
a BEVEL node, and `inject_bevel_shading` skips those. The practical consequence
is that `photoreal.bevel.radius_m` is inert for this CAD source — edge rounding
comes from the .blend and from `photoreal.powder_coat.bevel_radius_m`.

## Visual review

Compare the resulting `reference/composite.png` against:

`C:/Projects/work-assets/photograph-studio/rl-200-safe-back-iso-older-whtbkgrd.jpg`

Keep the photograph unchanged. It is an earlier machine revision and a different
camera/lighting setup, so it is a visual benchmark, not a pixel-error target.
At this full-machine framing, neither image resolves physical orange peel.
Any owner acceptance of this white reference must be recorded separately.

## Bare metal: what was wrong and what changed

Recorded 2026-09-13, from Mark's review of the first full-resolution white
render against two pump photographs of the same coupling family:
`DD4-BACK-ISO-MSP.jpg` and `dd-6-side.jpg`.

The fittings are four `Aluminum Cam and Groove Hose Coupling` meshes on
`MSP_ALUMINUM_CAST`. Against the photographs they read as pale plastic. Four
causes, in the order they mattered:

1. **Nothing to reflect.** Covered above; this was most of the gap, and it is a
   lighting fix rather than a material one.
2. **One roughness across the whole part.** A real coupling puts a turned band
   directly against a sandcast rim - semi-gloss beside visibly rough, inches
   apart. That juxtaposition is most of what says "machined metal", and a single
   value cannot produce it.
3. **Bolts indistinguishable from the casting.** `MSP_STAINLESS_FASTENER` sat at
   base 0.620 against the casting's 0.615, so the bright plated bolt heads that
   carry the "real hardware" read in the photograph simply vanished.
4. **Hardware shaded as a dielectric.** The CAD export put 27 zinc bolts and
   washers, and all six Allegis latch paddles, on `MSP_PLASTIC` - metallic 0.0.
   A plated bolt shaded as plastic is why fasteners looked like grey pips.

`photoreal.metal_finish` in the job answers all four. It rebuilds named metals
with a base colour, a two-value roughness split driven by a large-scale noise
mask, and an optional fine grain bump; and it carries `reassign` rules that move
objects onto the material their hardware actually is, matched by name.

Reassignment is per object and not per material on purpose: `MSP_PLASTIC` also
covers 79 genuinely plastic parts, so the material is not what is wrong - the
assignment is. A rule that matches nothing raises, because a silently dead rule
is what a CAD re-export with renamed part numbers would produce. Counts in the
log are objects, not slot writes; linked duplicates share mesh data, so one
write can cover 27 objects.

Tuning note for anyone revisiting the numbers: the split wants to be narrow.
A wide split (0.20 against 0.52) mottles the barrel into something that reads as
grime rather than casting, and at a fine `cast_scale` it reads as corrosion.
`0.22` against `0.32` at scale 25 gives variety without dirt.

Anisotropy is set: `MSP_ALUMINUM_CAST_TURNED` carries `anisotropy: 0.4` with
`anisotropy_axis: "Y"`. These couplings are lathe-turned and the real highlight
stretches around the barrel rather than sitting as a round spot; `metal_finish`
accepts `anisotropy` and `anisotropy_axis` and wires a radial Tangent node for
it. The axis is measured, not guessed - these couplings revolve about local Y -
and a wrong axis streaks the highlight the wrong way, so a new part's actual
orientation still needs checking before an axis is chosen for it.

## September 13 proof

Evidence: `output/verification/rl300-prepared-v1/parity-20260913-studio-white-metal/`.
Zero failures, `awaiting_reference_acceptance`, `repeat` pixel-identical, both
negative controls failing on their own codes, missing-texture blocked before
rendering. The payload carries seven inputs rather than six, the extra being
`environment_light.png`.

| White reference artifact | Decoded-pixel SHA-256 |
|---|---|
| `reference/beauty.png` | `5ceb4ff186526162763adc329841c2c63b45851c6755f483f6d3f49b386debce` |
| `reference/mask.png` | `0cb44b562ba185d2065e54ae9db8abc59b40e70b9fb6c453c29af9ba068afb03` |
| `reference/composite.png` | `b09df19daa75927b5cb549dd625878f753a44ff69ceacb8e5874002bafe3f61c` |

| Authored environment | File SHA-256 |
|---|---|
| `backgrounds/env_studio-white.png` | `2c91e7c9bcae779945c8f08f2179710fb865c5f969630c382c410a26f79dad1c` |
| `backgrounds/env_studio-softbox.png` | `bf67d7ea04884ae229ccb42f7dc62e0f98e79ade2bc52bd9954d24d5ec1b2b4f` |

**The accepted dark v6 anchor is unaffected.** A default-job regression at
`parity-20260913-dark-regression-metal/` passed all five modes, staged the same
six payload inputs as before, and is pixel-identical to the accepted v6
reference in beauty, mask and composite. The studio-dark job carries no
`metal_finish` block, so none of this reaches it.

The white image is not owner accepted; `owner_accepted`, `g0_passed` and
`cloud_authorized` remain false.

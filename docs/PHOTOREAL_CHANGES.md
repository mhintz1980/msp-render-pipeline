# Photoreal pipeline variant

Nothing in the original pipeline was modified. These are additive copies:

| new file | copy of | purpose |
|---|---|---|
| `render_worker_photoreal.py` | `render_worker.py` | bug fixes + photorealism pass |
| `msp_render_cli/materials_photoreal.py` | `msp_render_cli/materials.py` | re-exports the originals, adds calibrated metal/hardware table |
| `msp_render_cli/cameras_photoreal.py` | `msp_render_cli/cameras.py` | re-exports the originals, adds long-lens hero + detail presets |
| `examples/rl300_blend_render_ready_photoreal.json` | `examples/rl300_blend_render_ready.json` | hero manifest with the `photoreal` block |
| `examples/rl300_flange_detail_photoreal.json` | — | close-up of the bolted discharge flange |

Run it exactly as before, pointing at the new worker:

```bash
python -X utf8 -m msp_render_cli validate examples/rl300_blend_render_ready_photoreal.json
```

---

## 1. Three confirmed bugs in the current pipeline

### 1.1 The physical sky has never rendered (Blender 5.x)

`render_worker.py:329`

```python
sky_tex.sky_type = 'NISHITA'
```

In Blender 5.1 the `sky_type` enum is `SINGLE_SCATTERING | MULTIPLE_SCATTERING |
PREETHAM | HOSEK_WILKIE`. `NISHITA` was renamed when the model was split, so this
assignment raises `TypeError` immediately. `render_worker.py:335` then compounds it:

```python
sky_tex.dust_density = 1.3      # renamed to aerosol_density in 4.x
```

Both are inside the `try:` at line 326, whose `except` silently falls back to:

```python
bg_node.inputs["Color"].default_value = (0.75, 0.85, 1.0, 1.0)
bg_node.inputs["Strength"].default_value = 0.60 * intensity
```

So every `excavation_pit_sunlit` render so far has been lit by a **flat pale-blue
constant**, not a physical sky — no sky gradient, no sun disc, no horizon
falloff, and a wrong ambient colour for every metal surface in the scene. This is
almost certainly the largest single contributor to renders not looking real.

Verified directly against the connected Blender 5.1.1:

```
sky_type enum : ['SINGLE_SCATTERING', 'MULTIPLE_SCATTERING', 'PREETHAM', 'HOSEK_WILKIE']
dust_density  : absent      aerosol_density : present
```

Fixed in the copy by probing the enum and by feature-detecting the density
attribute. The `except` branch now prints a loud warning instead of failing quietly.

### 1.2 GPU devices are selected but never enabled

`render_worker.py:601-603` sets `cycles.device = 'GPU'` and
`prefs.compute_device_type = 'OPTIX'`, but never iterates
`prefs.devices` setting `device.use = True`. Choosing a backend does not switch
the devices on — Cycles falls back to CPU on the Modal L4 without saying so.
The copy calls `prefs.get_devices()`, enables the matching devices, falls back
`OPTIX -> CUDA`, and prints which GPU it actually got (or warns that it is on CPU).

### 1.3 `validate` reports valid manifests as failures on Windows

`cli.py:56` prints `"✓ Manifest ... is VALID."`. On a cp1252 console this raises
`UnicodeEncodeError`, which the bare `except Exception` at line 66 catches and
reports as `"✗ Error reading manifest: 'charmap' codec can't encode..."`, then
`sys.exit(1)`. A perfectly valid manifest looks like a hard failure.

Not fixed here (it is in `cli.py`, which you asked me to leave alone). Workaround:

```bash
python -X utf8 -m msp_render_cli validate <manifest>
```

The real fix is one line — wrap stdout, or use ASCII markers.

---

## 2. Two latent bugs, guarded in the copy

- **`apply_livery_materials()` references an undefined `smooth_latches`**
  (`render_worker.py:216`). It only survives because the RL300 manifest uses
  `livery.preset = "preserve_existing"`, which skips the call entirely. Switch to
  any real livery preset and it raises `NameError`. The copy adds it as a
  parameter. Note the function also never binds `MSP_Body_PowderCoat` or
  `MSP_Frame_SatinBlack` to any object despite the `--- Bind materials ---`
  comment — the loop under it only touches latch/handle meshes. Left as-is,
  flagged here.

- **`SUBSURF` on CAD meshes destroys custom split normals.** The latch-smoothing
  block at `render_worker.py:480-490` calls `shade_smooth()` and adds a
  Subdivision Surface. The RL300 CAD meshes carry baked `custom_normal` and
  `sharp_edge` attributes; overwriting them makes machined faces look melted.
  Currently dormant because the manifest sets `smooth_hardware: false`. The copy
  skips any mesh where `has_custom_normals` is true and says so in the log.

- **The ground-hiding heuristic is too aggressive.**
  `is_flat_ground_dim = (dim.x > 5.0 or dim.y > 5.0) and (dim.z < 1.0)` will hide
  any skid rail, long side panel or roof sheet over 5 m. The keyword list also
  contains `"plane"`, `"surface"`, `"plate"` and `"env"`, which match real CAD
  part names. The copy requires the object to be slab-like in *both* horizontal
  axes (>8 m), under 0.25 m thick, and centred near z=0.

---

## 3. What the photoreal pass adds

`apply_photoreal_pass()` runs immediately before the compositor setup and is
driven by a new `photoreal` block in the manifest. Everything it does costs zero
geometry and zero file size.

### 3.1 Bevel shading — the single biggest win

CAD edges are mathematically sharp, so no edge ever catches a specular
highlight. That is the strongest "this is a CAD render" tell there is. A Bevel
node feeding the Normal input rounds every edge in the scene at shading time.

`inject_bevel_shading()` is careful about one thing: where a material already
drives its Normal (the cast-aluminium noise bump, say), the bevel is chained
into *that* node's Normal input rather than replacing it, so surface texture and
edge rounding both survive.

Default radius 0.4 mm for hero shots, 0.25 mm for detail. Cycles only.

### 3.2 Light transport tuned for plated metal

`max_bounces` 12, `glossy_bounces` 8, light tree on, adaptive sampling at 0.01,
`blur_glossy` 0.5, reflective caustics on. Chrome and stainless hardware needs
more glossy bounces than the Blender default of 4 or the fasteners go flat and
dark in crevices.

### 3.3 Colour management

`output.color` now controls `view_transform`, `look`, `exposure` and `gamma`.
The stock scene runs AgX with `look = "None"`, which is deliberately flat. The
manifest sets `AgX - Medium High Contrast` at exposure `-0.35`.

Verified valid look names on this build: `AgX - Base Contrast`,
`AgX - Medium High Contrast`, `AgX - High Contrast`. Bare names like
`"Medium High Contrast"` are rejected — they must carry the `AgX - ` prefix.

### 3.4 Depth of field

`camera.depth_of_field` gives `enabled`, `f_stop`, `blades`, and either
`focus_distance` or `focus_object` (a mesh name — focus then tracks the feature
instead of a hard-coded distance). A render that is uniformly sharp from front
flange to rear hitch is the other instant tell.

### 3.5 Named scene cameras

`camera.scene_camera_name` selects a camera that already lives in the .blend.
Aiming a close-up by tuning azimuth / elevation / `target_offset` ratios against
scene bounds is painful; placing a camera in the file is not. The detail manifest
uses `DETAIL_DISCHARGE_FLANGE`, which now exists in the .blend copy.

### 3.6 HDRI rotation and strength

`lighting.hdri_rotation_deg` and `lighting.hdri_strength` are now honoured
(previously the mapping node was created and wired but never given a rotation,
and strength was hard-coded to `1.0 * intensity`).

---

## 4. Camera and material tables

`cameras_photoreal.py` adds `PR1-PR7` — the same framings as `P1-P8` shot at
100-135 mm from 4.8-6.4x radius instead of 35-50 mm at 2.1-2.8x. At 50 mm and
2.4x radius, vertical panel edges visibly diverge; real equipment photography is
shot long. It also adds `D1-D4` detail presets, and
`hyperfocal_focus_distance()` for placing focus one third into the subject.

`materials_photoreal.py` carries `METAL_REFERENCE`, measured linear base-colour
reflectance for the metals in this package, and `HARDWARE_MATERIALS`, which maps
each `MSP_*` material to base colour, metallic, and a **roughness range**. The
range drives a per-object `Object Info -> Random -> Map Range` jitter.

That jitter matters more than it sounds: the fasteners are linked duplicates.
All 16 bolts share one mesh datablock, all 16 nuts share another, all 32 washers
share a third. Without per-object variation every bolt in a flange ring shades
identically and the joint reads as one extruded part rather than eight separate
fasteners — which was the original complaint.

`apply_hardware_calibration(bpy)` applies that table to an open scene. It is
**not** called from the worker, because `msp_render_cli` is not guaranteed to be
importable inside the Modal Blender image. The RL300 .blend already carries these
values baked in. Use it for other .blends, or wire it in once you are confident
the package ships to Modal.

---

## 5. Companion .blend

`C:/Projects/CAD/RL300-SAFE/RL300-SAFE-render_ready_photoreal.blend` (9.4 MB,
saved as a copy — the original is untouched). Both new manifests point at it.

Contains: the 0.125" flange gaskets, seated washers and nuts, grade-marked and
individually clocked bolts with full-length threaded shanks, stainless fastener
and cast-aluminium materials with per-object roughness jitter, crease-preserving
subdivision on the hose couplings, weld fillets at the flange-to-pipe joints, the
`DETAIL_DISCHARGE_FLANGE` camera, and Bevel nodes already present in 10
materials. `inject_bevel_shading()` skips materials that already have one, so
running the worker against this file is idempotent.

---

## 6. The one thing still not solved

Metals are still blowing out to near-white under `excavation_pit_sunlit`, even
with the sky bug fixed and exposure at -0.35.

This is not an exposure problem. `metallic = 1.0` makes a surface a mirror, and a
clear procedural sky has no structure in it to mirror — so every metal part
returns roughly uniform bright sky and reads as white plastic. Real metal looks
like metal because it reflects a *cluttered* environment: horizon line, ground,
equipment, sheds, sky gradient.

The fix is an HDRI, which the pipeline already supports:

```json
"lighting": {
  "hdri_path": "work-assets/HDRI/excavation_pit_4k.exr",
  "hdri_strength": 1.0,
  "hdri_rotation_deg": -35.0
}
```

Rotate it to match the shadow direction in `env_excavationPit-sunlit.png` and
keep the key sun as-is for crisp shadows. Any outdoor industrial-yard HDRI will
do more for metal realism than every other item in this document combined.

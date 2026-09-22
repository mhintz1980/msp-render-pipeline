from __future__ import annotations

"""
Headless Blender Render Worker for Myers-Seth Pumps (MSP) Pipeline.

Photorealistic Cycles renderer. Supports GLB, OBJ, and native .blend scenes,
with both local execution and remote serverless dispatch via Modal.
Renders on a transparent film so the product can be composited onto any
background plate afterwards by composite_worker.py.

The pre-photoreal version of this file is kept at archive/render_worker_legacy.py
for reference only; see docs/PHOTOREAL_CHANGES.md for the delta.
"""

import sys
import os
import json
import math
import glob
import time
from typing import Dict, Any, Tuple, Optional

# Detect if running inside Blender
IN_BLENDER = False
try:
    import bpy
    import mathutils
    IN_BLENDER = True
except ImportError:
    bpy = None
    mathutils = None

# ==============================================================================
# BLENDER HEADLESS ENGINE SCRIPT (Executed inside Blender)
# ==============================================================================

def hex_to_linear_rgb(hex_code: str):
    hex_code = hex_code.lstrip('#')
    r = int(hex_code[0:2], 16) / 255.0
    g = int(hex_code[2:4], 16) / 255.0
    b = int(hex_code[4:6], 16) / 255.0
    to_linear = lambda c: c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    return (to_linear(r), to_linear(g), to_linear(b), 1.0)

def clean_scene():
    """Removes all default objects, lights, and cameras."""
    bpy.ops.wm.read_factory_settings(use_empty=True)

def import_cad_model(file_path: str, format_type: str = "glb"):
    """Imports GLB, OBJ, or opens native .blend files."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"CAD source file not found: {file_path}")
    
    if format_type in ["glb", "gltf"]:
        bpy.ops.import_scene.gltf(filepath=file_path)
    elif format_type == "obj":
        bpy.ops.wm.obj_import(filepath=file_path)
    elif format_type == "blend":
        bpy.ops.wm.open_mainfile(filepath=file_path)
    else:
        raise ValueError(f"Unsupported CAD format: {format_type}")

def get_scene_bounds() -> Tuple[Any, float]:
    """Calculates center and radius without moving objects."""
    all_objs = [obj for obj in bpy.context.scene.objects if obj.type == 'MESH']
    if not all_objs:
        return mathutils.Vector((0, 0, 0.5)), 1.5

    min_corner = mathutils.Vector((float('inf'), float('inf'), float('inf')))
    max_corner = mathutils.Vector((float('-inf'), float('-inf'), float('-inf')))

    for obj in all_objs:
        for corner in obj.bound_box:
            world_pt = obj.matrix_world @ mathutils.Vector(corner)
            min_corner.x = min(min_corner.x, world_pt.x)
            min_corner.y = min(min_corner.y, world_pt.y)
            min_corner.z = min(min_corner.z, world_pt.z)
            max_corner.x = max(max_corner.x, world_pt.x)
            max_corner.y = max(max_corner.y, world_pt.y)
            max_corner.z = max(max_corner.z, world_pt.z)

    center = (min_corner + max_corner) / 2.0
    dim = max_corner - min_corner
    radius = max(dim.x, dim.y, dim.z) / 2.0
    return center, radius

def normalize_model_bounds() -> Tuple[Any, float]:
    """
    Centers the imported model horizontally at (0, 0) and rests the lowest
    point at Z=0. Returns center vector and bounding box radius.
    """
    all_objs = [obj for obj in bpy.context.scene.objects if obj.type == 'MESH']
    if not all_objs:
        return mathutils.Vector((0, 0, 0)), 1.0

    min_corner = mathutils.Vector((float('inf'), float('inf'), float('inf')))
    max_corner = mathutils.Vector((float('-inf'), float('-inf'), float('-inf')))

    for obj in all_objs:
        for corner in obj.bound_box:
            world_pt = obj.matrix_world @ mathutils.Vector(corner)
            min_corner.x = min(min_corner.x, world_pt.x)
            min_corner.y = min(min_corner.y, world_pt.y)
            min_corner.z = min(min_corner.z, world_pt.z)
            max_corner.x = max(max_corner.x, world_pt.x)
            max_corner.y = max(max_corner.y, world_pt.y)
            max_corner.z = max(max_corner.z, world_pt.z)

    center = (min_corner + max_corner) / 2.0
    dim = max_corner - min_corner
    radius = max(dim.x, dim.y, dim.z) / 2.0

    offset = mathutils.Vector((-center.x, -center.y, -min_corner.z))

    # Move the top-most ancestor of every mesh, not just meshes that happen to
    # be unparented. glTF/GLB exports nest their geometry under node empties, so
    # the old `if obj.parent is None` test matched nothing at all: the model
    # stayed where it was while the camera aimed at the origin, and the product
    # rendered cropped and off-centre.
    roots = []
    for obj in all_objs:
        root = obj
        while root.parent is not None:
            root = root.parent
        if root not in roots:
            roots.append(root)
    for root in roots:
        root.location += offset

    bpy.context.view_layer.update()

    new_center = mathutils.Vector((0, 0, dim.z / 2.0))
    return new_center, radius

def apply_livery_materials(livery_spec: Dict[str, Any], smooth_latches: bool = False):
    """Applies calibrated PBR Principled BSDF powder coat with procedural orange-peel and micro-roughness."""
    body_hex = livery_spec.get("body_color_hex", "#F7B500")
    body_rough = livery_spec.get("body_roughness", 0.35)
    body_clearcoat = livery_spec.get("body_clearcoat", 0.28)
    
    frame_hex = livery_spec.get("frame_color_hex", "#1B1B1B")
    frame_rough = livery_spec.get("frame_roughness", 0.55)

    # --- Body Material: Calibrated Industrial Powder Coat with Orange Peel ---
    body_mat = bpy.data.materials.new(name="MSP_Body_PowderCoat")
    body_mat.use_nodes = True
    nodes = body_mat.node_tree.nodes
    links = body_mat.node_tree.links
    nodes.clear()

    output_node = nodes.new(type="ShaderNodeOutputMaterial")
    output_node.location = (400, 0)

    bsdf = nodes.new(type="ShaderNodeBsdfPrincipled")
    bsdf.location = (0, 0)
    bsdf.inputs["Base Color"].default_value = hex_to_linear_rgb(body_hex)
    bsdf.inputs["Roughness"].default_value = body_rough

    # Blender 5.x Coat inputs
    if "Coat Weight" in bsdf.inputs:
        bsdf.inputs["Coat Weight"].default_value = body_clearcoat
        if "Coat Roughness" in bsdf.inputs:
            bsdf.inputs["Coat Roughness"].default_value = 0.08
    elif "Clearcoat" in bsdf.inputs:
        bsdf.inputs["Clearcoat"].default_value = body_clearcoat

    # Procedural Orange-Peel Normal Map
    tex_coord = nodes.new(type="ShaderNodeTexCoord")
    tex_coord.location = (-600, -200)

    noise = nodes.new(type="ShaderNodeTexNoise")
    noise.location = (-400, -200)
    noise.inputs["Scale"].default_value = 220.0
    noise.inputs["Detail"].default_value = 4.0
    noise.inputs["Roughness"].default_value = 0.65

    bump = nodes.new(type="ShaderNodeBump")
    bump.location = (-200, -200)
    bump.inputs["Strength"].default_value = 0.035
    bump.inputs["Distance"].default_value = 0.002

    links.new(tex_coord.outputs["Object"], noise.inputs["Vector"])
    links.new(noise.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    links.new(bsdf.outputs["BSDF"], output_node.inputs["Surface"])

    # --- Frame Material: Satin Black Chassis & Hardware ---
    frame_mat = bpy.data.materials.new(name="MSP_Frame_SatinBlack")
    frame_mat.use_nodes = True
    f_nodes = frame_mat.node_tree.nodes
    f_links = frame_mat.node_tree.links
    f_nodes.clear()

    f_output = f_nodes.new(type="ShaderNodeOutputMaterial")
    f_output.location = (400, 0)

    f_bsdf = f_nodes.new(type="ShaderNodeBsdfPrincipled")
    f_bsdf.location = (0, 0)
    f_bsdf.inputs["Base Color"].default_value = hex_to_linear_rgb(frame_hex)
    f_bsdf.inputs["Roughness"].default_value = frame_rough

    # Micro-roughness variation for structural steel
    f_tex_coord = f_nodes.new(type="ShaderNodeTexCoord")
    f_tex_coord.location = (-600, 0)
    f_noise = f_nodes.new(type="ShaderNodeTexNoise")
    f_noise.location = (-400, 0)
    f_noise.inputs["Scale"].default_value = 45.0
    f_noise.inputs["Detail"].default_value = 3.0
    f_ramp = f_nodes.new(type="ShaderNodeMapRange")
    f_ramp.location = (-200, 0)
    f_ramp.inputs["From Min"].default_value = 0.0
    f_ramp.inputs["From Max"].default_value = 1.0
    f_ramp.inputs["To Min"].default_value = max(0.0, frame_rough - 0.08)
    f_ramp.inputs["To Max"].default_value = min(1.0, frame_rough + 0.08)

    f_links.new(f_tex_coord.outputs["Object"], f_noise.inputs["Vector"])
    f_links.new(f_noise.outputs["Fac"], f_ramp.inputs["Value"])
    f_links.new(f_ramp.outputs["Result"], f_bsdf.inputs["Roughness"])
    f_links.new(f_bsdf.outputs["BSDF"], f_output.inputs["Surface"])

    # --- Bind materials ---
 # In render_worker.py — replace lines 212-224 with:
    for obj in bpy.context.scene.objects:
        if obj.type == "MESH":
            name_lower = obj.name.lower()
            if any(k in name_lower for k in ["latch", "handle", "lock", "hinge", "catch", "recess"]):
                try:
                    obj.select_set(True)
                    bpy.context.view_layer.objects.active = obj

                    # 1. Strip any destructive Subsurf modifiers
                    for mod in list(obj.modifiers):
                        if mod.type == "SUBSURF" or mod.name == "Hardware_Subdiv":
                            obj.modifiers.remove(mod)

                    # 2. Apply non-destructive CAD angle smoothing
                    if smooth_latches:
                        try:
                            # Blender 4.1+ / 5.x
                            bpy.ops.object.shade_smooth_by_angle(angle=math.radians(30.0))
                        except Exception:
                            obj.data.use_auto_smooth = True
                            obj.data.auto_smooth_angle = math.radians(30.0)
                            bpy.ops.object.shade_smooth()

                        # 3. Add Weighted Normal to keep planar faces flat and edges crisp
                        if not any(m.type == "WEIGHTED_NORMAL" for m in obj.modifiers):
                            wn = obj.modifiers.new(name="Hardware_WeightedNormal", type="WEIGHTED_NORMAL")
                            wn.keep_sharp = True
                except Exception:
                    pass

def setup_camera(camera_spec: Dict[str, Any], center: Any, radius: float):
    """Configures camera placement and target tracking."""
    azimuth = math.radians(camera_spec.get("azimuth_deg", 45.0))
    elevation = math.radians(camera_spec.get("elevation_deg", 14.0))
    focal_length = camera_spec.get("focal_length_mm", 50.0)
    
    dist_mult = camera_spec.get("distance_multiplier", 3.2)
    distance = radius * dist_mult
    target = center.copy()
    target_offset = camera_spec.get("target_offset", [0.05, -0.05, 0.80])
    if isinstance(target_offset, (list, tuple)) and len(target_offset) >= 3:
        target.x = center.x + radius * target_offset[0]
        target.y = center.y + radius * target_offset[1]
        target.z = center.z * target_offset[2]
    elif isinstance(target_offset, (list, tuple)) and len(target_offset) == 1:
        target.z = center.z * target_offset[0]

    cam_x = target.x + distance * math.cos(elevation) * math.sin(azimuth)
    cam_y = target.y - distance * math.cos(elevation) * math.cos(azimuth)
    cam_z = target.z + distance * math.sin(elevation)

    cam_data = bpy.data.cameras.new(name="RenderCamera")
    cam_data.lens = focal_length
    cam_data.clip_start = 0.1
    cam_data.clip_end = 200.0

    cam_obj = bpy.data.objects.new(name="RenderCamera", object_data=cam_data)
    bpy.context.scene.collection.objects.link(cam_obj)
    bpy.context.scene.camera = cam_obj

    cam_obj.location = (cam_x, cam_y, cam_z)
    direction = target - cam_obj.location
    rot_quat = direction.to_track_quat('-Z', 'Y')
    cam_obj.rotation_euler = rot_quat.to_euler()

def mute_catcher_bounce(catcher_obj):
    """Stop the shadow catcher from lighting the product it sits under.

    A shadow catcher still participates in indirect light. The plane is built
    at size = radius * 14 with a cleared material slot, which leaves Blender's
    default ~0.8 grey diffuse - a bounce card larger than the machine, aimed
    straight up at it. Measured on RL300 studio-dark: enabling the catcher
    raised machine luminance on 87% of product pixels (mean +19, p95 +52),
    washing the yellow pale and lifting the black chassis frame to grey.

    Clearing the diffuse/glossy/transmission ray visibility keeps the shadow -
    which is a camera-ray effect on the catcher itself - while removing the
    plane from every indirect bounce path.
    """
    for attr in ("visible_diffuse", "visible_glossy", "visible_transmission",
                 "visible_volume_scatter"):
        try:
            setattr(catcher_obj, attr, False)
        except AttributeError:
            pass
    # Blender < 3.0 kept these on a cycles_visibility sub-struct.
    legacy = getattr(catcher_obj, "cycles_visibility", None)
    if legacy is not None:
        for attr in ("diffuse", "glossy", "transmission", "scatter"):
            try:
                setattr(legacy, attr, False)
            except AttributeError:
                pass


def setup_lighting(lighting_spec: Dict[str, Any], center: Any, radius: float,
                   suppress_shadow_catcher: bool = False):
    """Sets up calibrated studio softbox lights or physical outdoor sun/sky environment."""
    preset = lighting_spec.get("preset", "studio_dark")
    intensity = lighting_spec.get("intensity_multiplier", 1.0)
    hdri_path = lighting_spec.get("hdri_path")
    # A manifest that names an HDRI but whose file is missing must be loud about
    # it: the render still succeeds, it just quietly loses all image-based
    # lighting, which is exactly the difference the demo is meant to show.
    if hdri_path and not os.path.exists(hdri_path):
        raise FileNotFoundError(
            f"lighting.hdri_path does not exist: {hdri_path}\n"
            f"  (cwd={os.getcwd()}) - use an absolute path or a path relative to "
            f"the project root.")

    # Remove existing lights if replacing with fresh rig
    if preset != "preserve_existing":
        for obj in list(bpy.context.scene.objects):
            if obj.type == 'LIGHT':
                bpy.data.objects.remove(obj, do_unlink=True)

    # Ground plane shadow catcher
    # In floor mode the studio floor IS the ground: a shadow catcher would
    # fight the floor's own material, so the caller suppresses it.
    want_shadow = (lighting_spec.get("shadow_catcher", False)
                   and not suppress_shadow_catcher)
    catcher_obj = bpy.data.objects.get("GroundShadowCatcher")
    if want_shadow:
        if not catcher_obj:
            bpy.ops.mesh.primitive_plane_add(size=radius * 14.0, location=(0, 0, 0))
            catcher_obj = bpy.context.active_object
            catcher_obj.name = "GroundShadowCatcher"
        catcher_obj.is_shadow_catcher = True
        try:
            catcher_obj.cycles.is_shadow_catcher = True
        except Exception:
            pass
        catcher_obj.data.materials.clear()
        mute_catcher_bounce(catcher_obj)
    else:
        if catcher_obj:
            bpy.data.objects.remove(catcher_obj, do_unlink=True)

    # Setup World Environment Shader
    world = bpy.context.scene.world
    if not world:
        world = bpy.data.worlds.new("MSP_World")
        bpy.context.scene.world = world
    world.use_nodes = True
    w_nodes = world.node_tree.nodes
    w_links = world.node_tree.links
    w_nodes.clear()

    w_output = w_nodes.new(type="ShaderNodeOutputWorld")
    w_output.location = (400, 0)
    bg_node = w_nodes.new(type="ShaderNodeBackground")
    bg_node.location = (150, 0)
    w_links.new(bg_node.outputs["Background"], w_output.inputs["Surface"])

    if hdri_path and os.path.exists(hdri_path):
        env_tex = w_nodes.new(type="ShaderNodeTexEnvironment")
        env_tex.location = (-200, 0)
        env_tex.image = bpy.data.images.load(hdri_path)
        tex_coord = w_nodes.new(type="ShaderNodeTexCoord")
        tex_coord.location = (-600, 0)
        mapping = w_nodes.new(type="ShaderNodeMapping")
        mapping.location = (-400, 0)
        w_links.new(tex_coord.outputs["Generated"], mapping.inputs["Vector"])
        w_links.new(mapping.outputs["Vector"], env_tex.inputs["Vector"])
        w_links.new(env_tex.outputs["Color"], bg_node.inputs["Color"])
        mapping.inputs["Rotation"].default_value[2] = math.radians(
            lighting_spec.get("hdri_rotation_deg", 0.0))
        # hdri_strength is deliberately NOT scaled by intensity_multiplier:
        # intensity_multiplier trims the analytic key/fill/sun rig, and the two
        # need to be balanced against each other independently.
        bg_node.inputs["Strength"].default_value = lighting_spec.get("hdri_strength", 1.0)
        print(f"[MSP Render] Image-based lighting active: "
              f"{os.path.basename(hdri_path)} @ strength "
              f"{bg_node.inputs['Strength'].default_value}")
    elif preset == "excavation_pit_sunlit":
        try:
            sky_tex = w_nodes.new(type="ShaderNodeTexSky")
            sky_tex.location = (-200, 0)
            # Blender 5.x renamed the Nishita model; 'NISHITA' is no longer a valid
            # enum item and assigning it raises, which silently dropped the whole sky.
            _sky_enum = sky_tex.bl_rna.properties['sky_type'].enum_items.keys()
            for _cand in ('MULTIPLE_SCATTERING', 'NISHITA', 'SINGLE_SCATTERING', 'HOSEK_WILKIE'):
                if _cand in _sky_enum:
                    sky_tex.sky_type = _cand
                    break
            sky_tex.sun_disc = True
            sky_tex.sun_elevation = math.radians(38.0)
            sky_tex.sun_rotation = math.radians(-35.0)
            sky_tex.altitude = 15.0
            sky_tex.air_density = 1.0
            # 'dust_density' was renamed to 'aerosol_density' in Blender 4.x/5.x.
            if hasattr(sky_tex, 'aerosol_density'):
                sky_tex.aerosol_density = 1.3
            elif hasattr(sky_tex, 'dust_density'):
                sky_tex.dust_density = 1.3
            sky_tex.ozone_density = 1.0
            w_links.new(sky_tex.outputs["Color"], bg_node.inputs["Color"])
            bg_node.inputs["Strength"].default_value = 0.85 * intensity
        except Exception as _sky_err:
            # Do not fail silently: a flat blue background is a very different render.
            print(f"[MSP Render] WARNING: physical sky setup failed ({_sky_err}). "
                  f"Falling back to FLAT ambient - metals will look washed out.")
            bg_node.inputs["Color"].default_value = (0.75, 0.85, 1.0, 1.0)
            bg_node.inputs["Strength"].default_value = 0.60 * intensity
    else:
        bg_node.inputs["Color"].default_value = (0.05, 0.05, 0.05, 1.0)
        bg_node.inputs["Strength"].default_value = 1.0

    # When an HDRI is doing the lighting, the analytic rig is a balance knob, not
    # the light source. Set lighting.analytic_lights=false for pure IBL.
    if not lighting_spec.get("analytic_lights", True):
        print("[MSP Render] Analytic light rig disabled (pure image-based lighting).")
        return

    if preset in ["studio_dark", "studio_white"]:
        key_data = bpy.data.lights.new(name="Key_Softbox", type='AREA')
        key_data.energy = 800.0 * intensity * (radius ** 1.5)
        key_data.size = radius * 1.8
        key_data.color = (1.0, 0.98, 0.95)
        key_obj = bpy.data.objects.new("Key_Softbox", key_data)
        key_obj.location = (radius * 2.2, -radius * 2.2, radius * 2.8)
        bpy.context.scene.collection.objects.link(key_obj)
        key_obj.rotation_euler = (math.radians(45), 0, math.radians(45))

        fill_data = bpy.data.lights.new(name="Fill_Softbox", type='AREA')
        fill_data.energy = 350.0 * intensity * (radius ** 1.5)
        fill_data.size = radius * 2.2
        fill_data.color = (0.95, 0.97, 1.0)
        fill_obj = bpy.data.objects.new("Fill_Softbox", fill_data)
        fill_obj.location = (-radius * 2.5, -radius * 1.8, radius * 1.8)
        bpy.context.scene.collection.objects.link(fill_obj)

        rim_data = bpy.data.lights.new(name="Rim_Light", type='SPOT')
        rim_data.energy = 600.0 * intensity * (radius ** 1.5)
        rim_data.spot_size = math.radians(60)
        rim_data.color = (1.0, 1.0, 1.0)
        rim_obj = bpy.data.objects.new("Rim_Light", rim_data)
        rim_obj.location = (0, radius * 2.8, radius * 3.2)
        bpy.context.scene.collection.objects.link(rim_obj)

    elif preset == "excavation_pit_sunlit":
        # Direct High-Contrast 5400K Key Sun (matched to plate shadow angles)
        sun_data = bpy.data.lights.new(name="Outdoor_Sun", type='SUN')
        sun_data.energy = 5.2 * intensity
        sun_data.angle = math.radians(0.54)
        sun_data.color = (1.0, 0.96, 0.90)
        sun_obj = bpy.data.objects.new("Outdoor_Sun", sun_data)
        sun_obj.rotation_euler = (math.radians(52), math.radians(15), math.radians(-35))
        bpy.context.scene.collection.objects.link(sun_obj)

        # Diffuse Upward Ground/Gravel Bounce Light (fill undercarriage voids)
        bounce_data = bpy.data.lights.new(name="Ground_Soil_Bounce", type='SUN')
        bounce_data.energy = 0.75 * intensity
        bounce_data.angle = math.radians(45.0)
        bounce_data.color = (0.85, 0.74, 0.58)
        bounce_obj = bpy.data.objects.new("Ground_Soil_Bounce", bounce_data)
        bounce_obj.rotation_euler = (math.radians(-65), math.radians(10), math.radians(145))
        bpy.context.scene.collection.objects.link(bounce_obj)


# ==============================================================================
# PHOTOREALISM PASS  (added in render_worker_photoreal.py)
# ==============================================================================

def _principled_nodes(mat):
    if not getattr(mat, "use_nodes", False) or mat.node_tree is None:
        return []
    return [n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED"]


def polish_cad_materials(spec: Dict[str, Any]):
    """
    Gives untouched CAD materials a believable surface response.

    A GLB straight out of SolidWorks carries one auto-named material per face
    colour, with roughness and metallic both left at 0. Cycles renders that as
    wet plastic. This keeps every authored base colour exactly as-is and only
    sets the surface properties: dark parts read as machined/anodised metal,
    light parts as brushed alloy, and anything already given a non-default
    roughness by an artist is left alone.
    """
    if not spec.get("enabled", False):
        return

    default_rough = spec.get("default_roughness", 0.42)
    dark_metallic = spec.get("dark_metallic", 0.85)
    light_metallic = spec.get("light_metallic", 0.55)
    dark_threshold = spec.get("dark_threshold", 0.16)

    touched = 0
    for mat in bpy.data.materials:
        for bsdf in _principled_nodes(mat):
            rough_in = bsdf.inputs.get("Roughness")
            metal_in = bsdf.inputs.get("Metallic")
            base_in = bsdf.inputs.get("Base Color")
            if rough_in is None or metal_in is None:
                continue
            # Only rescue materials still sitting at the importer's defaults -
            # glTF hands every untextured CAD colour roughness 1.0 / metallic 0,
            # which Cycles renders as chalk. Never overwrite a deliberate look.
            if rough_in.is_linked or metal_in.is_linked:
                continue
            is_gltf_default = (rough_in.default_value >= 0.999
                               and metal_in.default_value <= 0.001)
            is_zero_default = rough_in.default_value <= 0.01
            if not (is_gltf_default or is_zero_default):
                continue

            luminance = 0.5
            if base_in is not None and not base_in.is_linked:
                r, g, b = base_in.default_value[:3]
                luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b

            if luminance < dark_threshold:
                rough_in.default_value = min(0.95, default_rough + 0.10)
                metal_in.default_value = dark_metallic
            else:
                rough_in.default_value = default_rough
                metal_in.default_value = light_metallic

            coat = bsdf.inputs.get("Coat Weight")
            if coat is not None and not coat.is_linked and coat.default_value == 0.0:
                coat.default_value = 0.05
            touched += 1

    print(f"[MSP Render] Material polish applied to {touched} CAD material(s).")


def inject_bevel_shading(radius: float = 0.0004, samples: int = 4,
                         skip_keywords=("glass", "airway", "volume", "shadow")):
    """Round every mathematically-sharp CAD edge at shading time.

    CAD geometry has zero-radius edges, so no edge ever catches a specular
    highlight - the single strongest 'this is a CAD render' tell. A Bevel node
    fixes it for the whole scene at zero geometry and zero file-size cost.
    Cycles only; the node is a no-op under EEVEE/Workbench.
    """
    touched = 0
    for mat in bpy.data.materials:
        if any(k in mat.name.lower() for k in skip_keywords):
            continue
        bsdfs = _principled_nodes(mat)
        if not bsdfs:
            continue
        nt = mat.node_tree
        if any(n.type == "BEVEL" for n in nt.nodes):
            continue
        bevel = nt.nodes.new("ShaderNodeBevel")
        bevel.samples = samples
        bevel.inputs["Radius"].default_value = radius
        bevel.location = (-1000, 400)
        wired = False
        for bsdf in bsdfs:
            nin = bsdf.inputs.get("Normal")
            if nin is None:
                continue
            if nin.is_linked:
                # Feed the existing bump/normal-map node instead of replacing it,
                # so procedural surface texture and edge rounding both survive.
                upstream = nin.links[0].from_node
                slot = upstream.inputs.get("Normal")
                if slot is not None and not slot.is_linked:
                    nt.links.new(bevel.outputs["Normal"], slot)
                    wired = True
            else:
                nt.links.new(bevel.outputs["Normal"], nin)
                wired = True
        if wired:
            touched += 1
        else:
            nt.nodes.remove(bevel)
    print(f"[MSP Render] Bevel shading injected into {touched} materials "
          f"(radius {radius * 1000:.2f} mm).")
    return touched


def _reassign_materials(rules) -> int:
    """Move objects onto the material their hardware actually is.

    The CAD export drops a lot of bought-in hardware onto MSP_PLASTIC: the
    Allegis latch paddle, and 36 zinc bolts and washers. Shading a plated bolt
    as a dielectric is why fasteners read as grey pips instead of metal. The
    material itself cannot be fixed, because MSP_PLASTIC also covers genuine
    plastic on 79 other parts - the assignment is what is wrong, so the rules
    are per object name and live in the manifest where they are reviewable.
    """
    import re

    moved = 0
    for rule in rules:
        pattern, target = rule.get("match"), rule.get("material")
        if not pattern or not target:
            raise ValueError(f"metal_finish.reassign needs 'match' and 'material': {rule}")
        material = bpy.data.materials.get(target)
        if material is None:
            raise ValueError(f"metal_finish.reassign target material not found: {target}")
        expr = re.compile(pattern)
        matched, writes = 0, 0
        for obj in bpy.data.objects:
            if obj.type != "MESH" or not expr.search(obj.name):
                continue
            matched += 1
            for slot in obj.material_slots:
                if slot.material is not None and slot.material.name != target:
                    slot.material = material
                    writes += 1
        if not matched:
            # A rule that matches nothing is a silent regression the next time
            # the CAD is re-exported and a part number changes.
            raise ValueError(f"metal_finish.reassign rule matched no object: {pattern}")
        moved += matched
        # Linked duplicates share one mesh, so a handful of writes can cover
        # every instance. Report the objects, which is what the count means.
        print(f"[MSP Render] Reassigned {matched} object(s) matching '{pattern}' -> {target} "
              f"({writes} slot write(s); linked duplicates share mesh data).")
    return moved


def apply_metal_finish(spec: Dict[str, Any]):
    """Give bare metal the two things a single roughness value cannot give it.

    A metal has no colour of its own; what you see is its surroundings, shaped
    by how the surface scatters them. The CAD materials carry one roughness
    across a whole part, so a cast coupling returns the same soft grey wash
    everywhere and reads as painted plastic. Two things are missing:

    1. **A machined/cast split.** On the real coupling a turned band sits
       directly against a sandcast rim - semi-gloss beside visibly rough, on one
       part, inches apart. That juxtaposition is most of what says "machined
       metal". One noise field cannot produce it, so this builds a mask from a
       large-scale noise and maps the two roughness values through it.
    2. **Anisotropy.** These couplings are turned on a lathe, so the highlight
       stretches around the barrel rather than sitting as a round spot. Cycles
       needs a tangent to know which way to stretch it, so a radial Tangent node
       is wired in when an axis is given.

    Sand grain rides underneath as a bump. It never resolves at full-machine
    framing, but it breaks up the highlight edge, which does.
    """
    if not spec.get("enabled", False):
        return 0

    moved = _reassign_materials(spec.get("reassign", []))
    touched = 0
    for name, finish in (spec.get("materials") or {}).items():
        mat = bpy.data.materials.get(name)
        if mat is None or not mat.use_nodes:
            raise ValueError(f"metal_finish: material {name} not found in the scene")
        bsdfs = _principled_nodes(mat)
        if not bsdfs:
            raise ValueError(f"metal_finish: {name} has no Principled BSDF")
        nodes, links = mat.node_tree.nodes, mat.node_tree.links

        base = finish.get("base_color")
        rough_machined = finish.get("roughness_machined")
        rough_cast = finish.get("roughness_cast")
        cast_scale = finish.get("cast_scale", 14.0)
        anisotropy = finish.get("anisotropy")
        axis = finish.get("anisotropy_axis")
        grain_scale = finish.get("grain_scale")
        grain_strength = finish.get("grain_strength", 0.15)
        grain_distance = finish.get("grain_distance", 0.00015)

        split = None
        if rough_machined is not None and rough_cast is not None:
            noise = nodes.new("ShaderNodeTexNoise")
            noise.location = (-1400, 500)
            noise.inputs["Scale"].default_value = cast_scale
            noise.inputs["Detail"].default_value = 2.0
            noise.inputs["Roughness"].default_value = 0.55
            geo = nodes.new("ShaderNodeNewGeometry")
            geo.location = (-1600, 500)
            links.new(geo.outputs["Position"], noise.inputs["Vector"])
            split = nodes.new("ShaderNodeMapRange")
            split.location = (-1180, 500)
            # Noise clusters around the middle; remap the band it actually
            # occupies so both surfaces reach their stated roughness.
            split.inputs["From Min"].default_value = 0.36
            split.inputs["From Max"].default_value = 0.64
            split.inputs["To Min"].default_value = rough_machined
            split.inputs["To Max"].default_value = rough_cast
            split.clamp = True
            links.new(noise.outputs["Fac"], split.inputs["Value"])

        bump = None
        if grain_scale:
            grain = nodes.new("ShaderNodeTexNoise")
            grain.location = (-1400, 220)
            grain.inputs["Scale"].default_value = grain_scale
            grain.inputs["Detail"].default_value = 3.0
            grain.inputs["Roughness"].default_value = 0.65
            grain_geo = nodes.new("ShaderNodeNewGeometry")
            grain_geo.location = (-1600, 220)
            links.new(grain_geo.outputs["Position"], grain.inputs["Vector"])
            bump = nodes.new("ShaderNodeBump")
            bump.location = (-1180, 220)
            bump.inputs["Strength"].default_value = grain_strength
            bump.inputs["Distance"].default_value = grain_distance
            links.new(grain.outputs["Fac"], bump.inputs["Height"])

        tangent = None
        if axis:
            tangent = nodes.new("ShaderNodeTangent")
            tangent.location = (-1180, -60)
            tangent.direction_type = "RADIAL"
            tangent.axis = axis

        for bsdf in bsdfs:
            if base is not None:
                bsdf.inputs["Base Color"].default_value = (base[0], base[1], base[2], 1.0)
            if "metallic" in finish:
                bsdf.inputs["Metallic"].default_value = finish["metallic"]
            rough_in = bsdf.inputs["Roughness"]
            if split is not None:
                for link in list(rough_in.links):
                    links.remove(link)
                links.new(split.outputs["Result"], rough_in)
            elif "roughness" in finish:
                for link in list(rough_in.links):
                    links.remove(link)
                rough_in.default_value = finish["roughness"]
            if anisotropy is not None:
                aniso_in = bsdf.inputs.get("Anisotropic")
                if aniso_in is not None:
                    aniso_in.default_value = anisotropy
                if tangent is not None:
                    tangent_in = bsdf.inputs.get("Tangent")
                    if tangent_in is not None:
                        links.new(tangent.outputs["Tangent"], tangent_in)
            if bump is not None:
                normal_in = bsdf.inputs.get("Normal")
                if normal_in is not None:
                    # Feed any existing bevel/bump chain through the grain so
                    # edge rounding survives; inject_bevel_shading runs later.
                    if normal_in.is_linked:
                        links.new(normal_in.links[0].from_socket, bump.inputs["Normal"])
                    links.new(bump.outputs["Normal"], normal_in)
        touched += 1

    print(f"[MSP Render] Metal finish applied to {touched} material(s); "
          f"{moved} material slot(s) reassigned.")
    return touched


def apply_powder_coat(spec: Dict[str, Any]):
    """Turn a flat painted CAD material into something that reads as powder coat.

    A single Principled lobe cannot look like powder coat no matter how the
    roughness is tuned - the finish is a broad body colour under a tighter clear
    sheen, and its surface carries orange peel: fine irregular dimpling left by
    the powder flowing out during cure. The CAD materials arrive as one lobe with
    a constant roughness, so every panel returns an identical, mathematically
    smooth highlight. That uniform specular gradient is the thing that reads as
    computer generated.

    Three additions, in the order they matter visually:

    1. A coat layer, for the dual-lobe sheen.
    2. Noise-driven *roughness*, which mottles the highlight. This carries the
       look at render resolution: roughness variation changes the shape of the
       highlight over many pixels, so the denoiser preserves it. High-frequency
       normal detail is exactly what OIDN is built to remove.
    3. A bump for the peel itself, underneath, for close inspection.

    Texture coordinates come from world position, not object coordinates: this
    assembly is hundreds of separate CAD parts, and per-object coordinates would
    restart the pattern at every panel seam and rescale it per part.
    """
    if not spec.get("enabled", False):
        return 0

    names = spec.get("materials", [])
    coat_weight = spec.get("coat_weight", 0.7)
    coat_rough = spec.get("coat_roughness", 0.10)
    rough_min = spec.get("roughness_min", 0.38)
    rough_max = spec.get("roughness_max", 0.48)
    rough_scale = spec.get("roughness_noise_scale", 18.0)
    peel_scale = spec.get("peel_scale", 550.0)
    peel_strength = spec.get("peel_strength", 0.15)
    peel_distance = spec.get("peel_distance", 0.0006)
    flow_scale = spec.get("flow_scale", 130.0)
    flow_weight = spec.get("flow_weight", 0.6)
    bevel_radius = spec.get("bevel_radius_m")

    touched = 0
    for name in names:
        mat = bpy.data.materials.get(name)
        if mat is None or not mat.use_nodes:
            print(f"[MSP Render] Powder coat: material {name} not found; skipped.")
            continue
        bsdfs = _principled_nodes(mat)
        if not bsdfs:
            print(f"[MSP Render] Powder coat: {name} has no Principled BSDF; skipped.")
            continue
        nt = mat.node_tree
        nodes, links = nt.nodes, nt.links

        geo = nodes.new("ShaderNodeNewGeometry")
        geo.location = (-1400, -400)

        rough_noise = nodes.new("ShaderNodeTexNoise")
        rough_noise.location = (-1150, -250)
        rough_noise.inputs["Scale"].default_value = rough_scale
        rough_noise.inputs["Detail"].default_value = 2.0
        rough_noise.inputs["Roughness"].default_value = 0.5

        rough_range = nodes.new("ShaderNodeMapRange")
        rough_range.location = (-900, -250)
        # Noise rarely reaches 0 or 1; remapping from the band it actually
        # occupies keeps the full roughness spread instead of a washed middle.
        rough_range.inputs["From Min"].default_value = 0.30
        rough_range.inputs["From Max"].default_value = 0.70
        rough_range.inputs["To Min"].default_value = rough_min
        rough_range.inputs["To Max"].default_value = rough_max

        # Two scales, because one cannot cover both viewing distances. True orange
        # peel is around 1-2 mm; framed full-width at this resolution the machine
        # gets roughly 2 mm per pixel, so that layer is sub-pixel and contributes
        # nothing here - it only appears in close crops and higher-res output.
        # The coarser layer is the coating's flow-out undulation, several
        # millimetres across, which is what actually reads as a coated surface at
        # full-machine framing. Both are physical; they just resolve at different
        # distances.
        peel_noise = nodes.new("ShaderNodeTexNoise")
        peel_noise.location = (-1150, -600)
        peel_noise.inputs["Scale"].default_value = peel_scale
        peel_noise.inputs["Detail"].default_value = 3.0
        peel_noise.inputs["Roughness"].default_value = 0.6

        flow_noise = nodes.new("ShaderNodeTexNoise")
        flow_noise.location = (-1150, -800)
        flow_noise.inputs["Scale"].default_value = flow_scale
        flow_noise.inputs["Detail"].default_value = 2.0
        flow_noise.inputs["Roughness"].default_value = 0.5

        peel_mix = nodes.new("ShaderNodeMix")
        peel_mix.data_type = "FLOAT"
        peel_mix.location = (-1020, -700)
        peel_mix.inputs["Factor"].default_value = flow_weight

        bump = nodes.new("ShaderNodeBump")
        bump.location = (-900, -600)
        bump.inputs["Strength"].default_value = peel_strength
        bump.inputs["Distance"].default_value = peel_distance

        links.new(geo.outputs["Position"], rough_noise.inputs["Vector"])
        links.new(geo.outputs["Position"], peel_noise.inputs["Vector"])
        links.new(geo.outputs["Position"], flow_noise.inputs["Vector"])
        links.new(rough_noise.outputs["Fac"], rough_range.inputs["Value"])
        _mix_a, _mix_b = [s for s in peel_mix.inputs if s.name == "A"][0],                          [s for s in peel_mix.inputs if s.name == "B"][0]
        links.new(peel_noise.outputs["Fac"], _mix_a)
        links.new(flow_noise.outputs["Fac"], _mix_b)
        links.new([s for s in peel_mix.outputs if s.name == "Result"][0], bump.inputs["Height"])

        for bsdf in bsdfs:
            rough_in = bsdf.inputs.get("Roughness")
            if rough_in is not None and not rough_in.is_linked:
                links.new(rough_range.outputs["Result"], rough_in)
            for key, value in (("Coat Weight", coat_weight), ("Coat Roughness", coat_rough)):
                slot = bsdf.inputs.get(key)
                if slot is not None and not slot.is_linked:
                    slot.default_value = value
            nin = bsdf.inputs.get("Normal")
            if nin is None:
                continue
            if nin.is_linked:
                # Keep whatever already rounds the edges (the CAD bevel node) and
                # put the peel on top of it, rather than replacing it.
                upstream = nin.links[0].from_socket
                links.new(upstream, bump.inputs["Normal"])
            links.new(bump.outputs["Normal"], nin)

        if bevel_radius is not None:
            for node in nodes:
                if node.type == "BEVEL":
                    node.inputs["Radius"].default_value = bevel_radius
        touched += 1
        print(f"[MSP Render] Powder coat applied to {name}: coat {coat_weight:.2f} "
              f"@ {coat_rough:.2f}, roughness {rough_min:.2f}-{rough_max:.2f}, "
              f"peel {1000.0 / peel_scale:.2f} mm + flow "
              f"{1000.0 / flow_scale:.2f} mm @ {flow_weight:.2f}.")
    return touched


def apply_cycles_quality(scene, quality: Dict[str, Any]):
    """Light-transport settings that matter for brushed/plated metal hardware."""
    if scene.render.engine != "CYCLES":
        return
    c = scene.cycles
    c.max_bounces = quality.get("max_bounces", 12)
    c.diffuse_bounces = quality.get("diffuse_bounces", 4)
    c.glossy_bounces = quality.get("glossy_bounces", 8)
    c.transmission_bounces = quality.get("transmission_bounces", 8)
    c.transparent_max_bounces = quality.get("transparent_bounces", 8)
    c.sample_clamp_indirect = quality.get("clamp_indirect", 10.0)
    c.blur_glossy = quality.get("blur_glossy", 0.5)
    for attr, key, default in (("use_light_tree", "light_tree", True),
                               ("use_adaptive_sampling", "adaptive_sampling", True),
                               ("caustics_reflective", "caustics_reflective", True),
                               ("caustics_refractive", "caustics_refractive", False)):
        try:
            setattr(c, attr, quality.get(key, default))
        except Exception:
            pass
    try:
        c.adaptive_threshold = quality.get("adaptive_threshold", 0.01)
    except Exception:
        pass
    try:
        scene.render.use_persistent_data = True
    except Exception:
        pass
    print(f"[MSP Render] Cycles quality: {c.samples} samples, "
          f"{c.max_bounces} bounces, glossy {c.glossy_bounces}.")


FLOOR_OBJECT_NAME = "MSP_StudioFloor"
FLOOR_MATERIAL_NAME = "MSP_StudioFloor_Neutral"
FLOOR_COLOR_HEX = "#B8B8B8"
CYC_ROUGHNESS = 0.7  # 2026-09-21 owner look review: softens the softbox pool.


def film_transparent_for(out_spec: Dict[str, Any]) -> bool:
    """output.film_transparent, defaulting to the legacy transparent cut-out.

    Accepts either the output block itself or a whole manifest; an explicit
    boolean (true or false) is always honoured, never coerced to the default.
    """
    block = out_spec.get("output", out_spec) if isinstance(out_spec, dict) else {}
    return bool(block.get("film_transparent", True))


def floor_requested(manifest: Dict[str, Any]) -> bool:
    """lighting.floor.enabled is the only authority for floor mode.

    A missing block, a non-dict block, or a non-boolean enabled value is a
    configuration error, not a silent false - but a block that is absent
    entirely stays the permissive legacy default (no floor).
    """
    lighting = manifest.get("lighting", {})
    floor = lighting.get("floor")
    if floor is None:
        return False
    if not isinstance(floor, dict) or not isinstance(floor.get("enabled"), bool):
        raise ValueError(
            "INVALID_FLOOR_CONFIG: lighting.floor.enabled must be a boolean "
            f"(got: {floor!r})")
    return floor["enabled"]


def validate_output_config(manifest: Dict[str, Any]) -> bool:
    """Reject unsupported film/floor combinations before any expensive work.

    Returns the floor flag. Raises ValueError on:
    - floor with transparent film (the floor must be baked into the beauty);
    - opaque film without the floor (no independent matte mechanism exists
      yet, so the mask would silently measure the opaque floor);
    - floor with product rescale/offset (a full-scene render cannot be
      repositioned the way a cut-out can).
    - floor with the alpha mask pass disabled (full-scene finishing is
      impossible without the independent product matte).
    """
    out = manifest.get("output", {})
    film = out.get("film_transparent", True)
    if not isinstance(film, bool):
        raise ValueError(
            "INVALID_OUTPUT_CONFIG: output.film_transparent must be a boolean "
            f"(got: {film!r})")
    floor = floor_requested(manifest)
    if floor and film:
        raise ValueError(
            "FLOOR_REQUIRES_OPAQUE_FILM: lighting.floor.enabled=true needs "
            "output.film_transparent=false - the floor must be baked into the "
            "beauty pass.")
    if not floor and not film:
        raise ValueError(
            "OPAQUE_NON_FLOOR_UNSUPPORTED: output.film_transparent=false "
            "without lighting.floor.enabled=true has no independent matte "
            "mechanism; enable the floor or keep film_transparent=true.")
    if floor:
        comp = manifest.get("compositing", {})
        scale = comp.get("product_scale", 1.0)
        if isinstance(scale, bool) or not isinstance(scale, (int, float)) \
                or scale != 1.0:
            raise ValueError(
                "FLOOR_REQUIRES_UNIT_PRODUCT_SCALE: a full-scene render cannot "
                f"be repositioned like a cut-out (product_scale={scale!r}).")
        off_px = comp.get("product_offset_px", (0, 0))
        off_pct = comp.get("product_offset_pct", (0, 0))

        def _zero(seq):
            return (isinstance(seq, (list, tuple)) and len(seq) == 2
                    and all(v == 0 for v in seq))

        if not _zero(off_px) or not _zero(off_pct):
            raise ValueError(
                "FLOOR_REQUIRES_ZERO_PRODUCT_OFFSET: a full-scene render "
                f"cannot be repositioned (offset_px={off_px!r}, "
                f"offset_pct={off_pct!r}).")
        passes = out.get("passes") or {}
        if passes.get("alpha_mask", True) is False:
            raise ValueError(
                "FLOOR_REQUIRES_ALPHA_MASK: floor mode finishes from the "
                "independently rendered product matte; "
                "output.passes.alpha_mask=false cannot produce it and the "
                "job could never finish. Keep alpha_mask enabled or disable "
                "the floor.")
    return floor


def _visible_product_ground():
    """World-space min-z and x/y centre of the visible product meshes.

    The studio floor seats at the machine's actual ground contact. A native
    .blend is opened with get_scene_bounds() - nothing re-normalises it to
    z=0 the way a GLB import is - so a floor hardcoded at z=0 could float
    above or slice through the product. Ground slabs the hide pass removed
    (hide_render=True) are excluded: the floor must meet the PRODUCT, not the
    CAD file's own scenery. Outside Blender (unit-test doubles) the transform
    degrades to a translation-only approximation; inside Blender the full
    matrix is used.
    """
    min_x = min_y = min_z = math.inf
    max_x = max_y = -math.inf
    found = False
    for obj in bpy.context.scene.objects:
        if getattr(obj, "type", None) != "MESH" or obj.hide_render \
                or obj.name in (FLOOR_OBJECT_NAME, "GroundShadowCatcher"):
            continue
        for corner in obj.bound_box:
            try:
                if mathutils is not None:
                    v = obj.matrix_world @ mathutils.Vector(corner)
                    wx, wy, wz = v.x, v.y, v.z
                else:
                    t = obj.matrix_world.translation
                    wx, wy, wz = (corner[0] + t.x, corner[1] + t.y,
                                  corner[2] + t.z)
            except Exception:
                continue
            found = True
            min_x, max_x = min(min_x, wx), max(max_x, wx)
            min_y, max_y = min(min_y, wy), max(max_y, wy)
            min_z = min(min_z, wz)
    if not found:
        return None
    return ((min_x + max_x) / 2.0, (min_y + max_y) / 2.0, min_z)


FLOOR_EDGE_MARGIN_RATIO = 0.05


def _camera_corner_rays(scene):
    """(corner rays, camera origin, normalized forward) for the frame.

    Uses the ACTUAL camera: view_frame(scene=scene) honours the final render
    resolution and sensor fit, and camera.matrix_world the final transform -
    so the bound covers what the sensor really sees, not a reconstructed
    approximation. Perspective rays originate at the camera location;
    orthographic rays originate at the transformed frame corners and run
    along the camera forward (-Z) axis. Anything else is rejected clearly
    instead of guessed at.

    Returns (rays, camera_origin, camera_forward) where rays are
    (origin_xyz, direction_xyz) tuples and camera_forward is the NORMALIZED
    world -Z axis of the actual matrix, so downstream axial-depth checks are
    immune to scale baked into the camera matrix. The camera origin is the
    object's translation (the camera centre) for BOTH projection types:
    orthographic clipping is measured from the camera centre, not from the
    corner-ray starting points.
    """
    camera = getattr(scene, "camera", None)
    if camera is None:
        raise RuntimeError(
            "FLOOR_CAMERA_MISSING: floor mode needs a scene camera to derive "
            "the plane extent; none was set.")
    cam_data = camera.data
    cam_type = getattr(cam_data, "type", "PERSP")
    # setup_camera assigns location/rotation_euler, but matrix_world only
    # reflects the last depsgraph evaluation - identity for a freshly created
    # camera object. Any operator between setup_camera and here can evaluate
    # the depsgraph implicitly, which hid this on earlier successful renders;
    # run2 az42 hit the floor gate first, read the stale identity (camera at
    # the origin, below floor z), and failed FLOOR_BEHIND_CAMERA. Force the
    # update BEFORE reading the matrix so the bound always comes from the
    # actual placed transform. bpy is None in unit-test fakes without Blender.
    if bpy is not None:
        try:
            bpy.context.view_layer.update()
        except AttributeError:
            pass
    matrix = camera.matrix_world
    origin_v = matrix.translation
    camera_origin = (origin_v.x, origin_v.y, origin_v.z)
    z_col = matrix.col[2]
    raw_forward = (-z_col.x, -z_col.y, -z_col.z)
    forward_len = math.sqrt(raw_forward[0] ** 2 + raw_forward[1] ** 2
                            + raw_forward[2] ** 2)
    if forward_len <= 0.0:
        raise RuntimeError(
            "FLOOR_CAMERA_DEGENERATE: camera forward axis is zero-length; "
            "cannot derive axial depth for the floor bound.")
    camera_forward = (raw_forward[0] / forward_len,
                      raw_forward[1] / forward_len,
                      raw_forward[2] / forward_len)
    try:
        corners = cam_data.view_frame(scene=scene)
    except Exception as exc:
        raise RuntimeError(
 f"FLOOR_VIEW_FRAME_FAILED: could not read the camera view frame: {exc}") from exc
    if cam_type == 'PERSP':
        rays = []
        for corner in corners:
            world = matrix @ corner
            rays.append((camera_origin,
                         (world.x - camera_origin[0],
                          world.y - camera_origin[1],
                          world.z - camera_origin[2])))
        return rays, camera_origin, camera_forward
    if cam_type == 'ORTHO':
        rays = []
        for corner in corners:
            world = matrix @ corner
            rays.append(((world.x, world.y, world.z), camera_forward))
        return rays, camera_origin, camera_forward
    raise RuntimeError(
        f"FLOOR_CAMERA_UNSUPPORTED: camera type {cam_type!r} cannot be bounded "
        f"analytically; only PERSP and ORTHO cameras are supported in floor "
        f"mode.")


def _cyc_dof_blur(axial_depth, aperture_radius_m, focus_distance_m):
    """Defocus blur disc radius at a hit's axial depth (0 when DOF is off)."""
    if aperture_radius_m > 0.0 and focus_distance_m > 0.0:
        return (aperture_radius_m * abs(axial_depth - focus_distance_m)
                / focus_distance_m)
    return 0.0


def required_floor_radius(corner_rays, cyc_center,
                          camera_origin, camera_forward,
                          clip_end=200.0, aperture_radius_m=0.0,
                          focus_distance_m=0.0):
    """Disc radius needed so the cyc disc covers every below-horizon corner.

    Pure geometry: corner_rays is an iterable of (origin_xyz, direction_xyz)
    float tuples in world space, cyc_center the (cx, cy, seat_z) of the
    revolved surface. For each ray with direction_z < 0 the intersection
    with the ground plane z=seat_z is solved analytically
    (t = (seat_z - origin_z) / direction_z). The requirement is EUCLIDEAN
    radial distance of the hit from the cyc axis - the coverage surface is
    now a rotationally symmetric disc, not a square plane, so the old
    Chebyshev max(|dx|, |dy|) metric would under-cover the diagonals it
    used to round off. Rays with direction_z >= 0 are ignored here: the
    concave fillet/wall owns them, and their coverage is derived separately
    in required_wall_height against the FINISHED wall radius (order is
    load-bearing - raising R afterwards would move the cylinder out from
    under a wall height derived against the smaller one).

    The parameter t is scale-bearing and never used directly as a distance:
    the clip and DOF metrics use the hit's AXIAL DEPTH, the projection of
    (hit - camera_origin) onto the normalized camera_forward - exactly what
    Blender's clip_end measures. Directions may carry any positive scale:
    direction*0.1 and direction*10 give identical results. A below-horizon
    ray that hits behind the camera (t <= 0) or lands at/beyond clip_end
    axially fails loudly - no silent guess can cover those frames.

    The returned radius is the max per-ray requirement: radial distance
    grown by a small conservative margin (5%) plus, when depth of field is
    on, the defocus blur disc radius at the hit's axial depth
    (aperture_radius_m * |depth - focus| / focus) so the blurred far edge
    still lands on geometry.
    """
    center_x, center_y, seat_z = cyc_center
    required = 0.0
    fwd_x, fwd_y, fwd_z = camera_forward
    for index, (origin, direction) in enumerate(corner_rays):
        dz = direction[2]
        if dz >= 0.0:
            continue
        t = (seat_z - origin[2]) / dz
        if t <= 0.0:
            raise RuntimeError(
                f"FLOOR_BEHIND_CAMERA: frame corner {index} ground "
                f"intersection is behind the camera (t={t:.3f} <= 0; camera "
                f"at/below the floor plane?).")
        hit_x = origin[0] + t * direction[0]
        hit_y = origin[1] + t * direction[1]
        hit_z = origin[2] + t * direction[2]
        axial_depth = ((hit_x - camera_origin[0]) * fwd_x
                       + (hit_y - camera_origin[1]) * fwd_y
                       + (hit_z - camera_origin[2]) * fwd_z)
        if axial_depth >= clip_end:
            raise RuntimeError(
                f"FLOOR_EDGE_BEYOND_CLIP_END: frame corner {index} ground hit "
                f"is at axial depth {axial_depth:.2f} m (measured along the "
                f"normalized camera forward axis), at/beyond the camera "
                f"clip_end of {clip_end:.2f} m; the far floor edge would be "
                f"clipped. Raise clip_end or steepen the camera.")
        radial = math.hypot(hit_x - center_x, hit_y - center_y)
        need = (radial * (1.0 + FLOOR_EDGE_MARGIN_RATIO)
                + _cyc_dof_blur(axial_depth, aperture_radius_m,
                                focus_distance_m))
        required = max(required, need)
    return required


def required_wall_height(corner_rays, cyc_center,
                         camera_origin, camera_forward, wall_radius,
                         clip_end=200.0, aperture_radius_m=0.0,
                         focus_distance_m=0.0):
    """Wall height (above the seat) so the cyc wall covers above-horizon rays.

    Pure geometry, the companion of required_floor_radius and derived AGAINST
    the finished wall radius (see the ordering note there). For each ray with
    direction_z >= 0 the intersection with the wall cylinder
    |P_xy - c_xy|^2 = wall_radius^2 is solved as a quadratic in t; the
    smallest positive root is the crossing. A vertical ray (zero horizontal
    velocity) never meets the cylinder and fails CYC_WALL_UNREACHABLE - the
    wall is finite, so no height can cover a ray that escapes through the
    open top without ever crossing the cylinder. From inside the cylinder
    there is always exactly one positive root; the no-root branch is
    defensive.

    The requirement is (z_hit - seat_z) grown by the 5% margin plus DOF
    blur at the hit's axial depth. The fillet lies strictly inside the
    cylinder, so the true concave hit happens no later than this
    cylinder-crossing height - using the crossing is conservative and
    correct. Rays with direction_z < 0 are ignored here (the disc owns
    them). Directions may carry any positive scale; results depend only on
    hit points and axial depths.
    """
    center_x, center_y, seat_z = cyc_center
    required = 0.0
    fwd_x, fwd_y, fwd_z = camera_forward
    for index, (origin, direction) in enumerate(corner_rays):
        dz = direction[2]
        if dz < 0.0:
            continue
        dx, dy = direction[0], direction[1]
        ox, oy = origin[0] - center_x, origin[1] - center_y
        a = dx * dx + dy * dy
        if a <= 0.0:
            raise RuntimeError(
                f"CYC_WALL_UNREACHABLE: frame corner {index} ray is vertical "
                f"and never meets the wall cylinder; no finite wall covers "
                f"the frame.")
        b = 2.0 * (ox * dx + oy * dy)
        c = ox * ox + oy * oy - wall_radius * wall_radius
        disc = b * b - 4.0 * a * c
        if disc < 0.0:
            raise RuntimeError(
                f"CYC_WALL_UNREACHABLE: frame corner {index} ray never "
                f"meets the wall cylinder; no finite wall covers the frame.")
        root = math.sqrt(disc)
        t_hit = None
        for t in ((-b - root) / (2.0 * a), (-b + root) / (2.0 * a)):
            if t > 0.0:
                t_hit = t
                break
        if t_hit is None:
            raise RuntimeError(
                f"CYC_WALL_UNREACHABLE: frame corner {index} ray meets the "
                f"wall cylinder only behind its origin; no finite wall "
                f"covers the frame.")
        hit_x = origin[0] + t_hit * dx
        hit_y = origin[1] + t_hit * dy
        hit_z = origin[2] + t_hit * dz
        axial_depth = ((hit_x - camera_origin[0]) * fwd_x
                       + (hit_y - camera_origin[1]) * fwd_y
                       + (hit_z - camera_origin[2]) * fwd_z)
        if axial_depth >= clip_end:
            raise RuntimeError(
                f"FLOOR_EDGE_BEYOND_CLIP_END: frame corner {index} wall-top "
                f"hit is at axial depth {axial_depth:.2f} m (measured along "
                f"the normalized camera forward axis), at/beyond the camera "
                f"clip_end of {clip_end:.2f} m; the wall top would be "
                f"clipped. Raise clip_end or steepen the camera.")
        need = ((hit_z - seat_z) * (1.0 + FLOOR_EDGE_MARGIN_RATIO)
                + _cyc_dof_blur(axial_depth, aperture_radius_m,
                                focus_distance_m))
        required = max(required, need)
    return required


CYC_ANGULAR_SEGMENTS = 128  # Revolve resolution of the cyc surface.
FILLET_ARC_SEGMENTS = 12    # Quarter-arc samples between disc and wall.


def cyc_mesh_data(floor_radius, wall_height, fillet_radius, center,
                  angular_segments=CYC_ANGULAR_SEGMENTS):
    """Return (verts, faces) for the revolved cyc profile, world space.

    The 2D r-z profile - flat disc out to floor_radius, tangent quarter-arc
    fillet of fillet_radius (tangent to the disc at its outer edge, tangent
    to the vertical wall at its top), then - only when wall_height is
    strictly above fillet_radius - the wall up to wall_height above the
    seat - is revolved 360 degrees around the vertical axis through
    center (cx, cy, seat z). Shared profile endpoints are not duplicated.
    A nominal wall of exactly fillet_radius is skipped: appending its
    wall-top point would duplicate the arc's final sample and collapse the
    last quad ring to zero height (degenerate faces).
    Disc-fan triangles are wound so their normals point UP (+z); ring quads
    are wound so their normals point INWARD toward the axis - the camera
    always sees the concave side of the cove.
    """
    cx, cy, seat_z = center
    big_r = floor_radius
    rc = fillet_radius
    # Profile (r, z) relative to the seat: disc edge, arc samples, wall top.
    profile = [(big_r, 0.0)]
    for k in range(1, FILLET_ARC_SEGMENTS + 1):
        phi = -math.pi / 2.0 + (math.pi / 2.0) * k / FILLET_ARC_SEGMENTS
        profile.append((big_r + rc * math.cos(phi),
                        rc + rc * math.sin(phi)))
    if wall_height > rc:
        profile.append((big_r + rc, wall_height))
    verts = [(cx, cy, seat_z)]
    for r, z in profile:
        for j in range(angular_segments):
            theta = 2.0 * math.pi * j / angular_segments
            verts.append((cx + r * math.cos(theta),
                          cy + r * math.sin(theta),
                          seat_z + z))

    def ring(i, j):
        return 1 + i * angular_segments + (j % angular_segments)

    faces = []
    # Disc fan, wound for +z normals.
    for j in range(angular_segments):
        faces.append((0, ring(0, j), ring(0, j + 1)))
    # Quad rings, wound for inward normals (camera sees the concave side).
    for i in range(len(profile) - 1):
        for j in range(angular_segments):
            faces.append((ring(i, j), ring(i + 1, j),
                          ring(i + 1, j + 1), ring(i, j + 1)))
    return verts, faces


def build_studio_floor(radius: float, scene=None):
    """Create the studio cyclorama and hold its direct reference.

    Called AFTER the ground-keyword hide pass (so the repo's own ground
    defences cannot eat it) and AFTER the photorealism pass (so no generic
    material pass - CAD polish, bevel injection - can touch its fixed neutral
    material). The surface is a rotationally symmetric infinity cove: flat
    disc under the product, tangent quarter-arc fillet, vertical wall. The
    disc radius and wall height are derived per frame from the actual
    camera's frame-corner rays (see required_floor_radius and
    required_wall_height, in that order - the wall is sized against the
    finished wall radius), so no plane edge or wall top can show inside the
    frame against the HDRI backdrop. The PLACEMENT comes from the product's
    measured ground bounds, never from an assumed z=0. The material is fixed
    and neutral by design - the only floor knob is on/off, and product
    materials are never touched.
    """
    if scene is None:
        scene = bpy.context.scene
    placement = _visible_product_ground() or (0.0, 0.0, 0.0)
    # No silent legacy fallback: without a scene camera the plane cannot be
    # sized to the visible frame, and a quietly small plane is exactly the
    # far-edge artifact floor mode exists to prevent. _camera_corner_rays
    # raises FLOOR_CAMERA_MISSING loudly in that case.
    corner_rays, camera_origin, camera_forward = _camera_corner_rays(scene)
    if camera_origin[2] <= placement[2]:
        raise RuntimeError(
            "FLOOR_BEHIND_CAMERA: camera sits at/below the floor plane; a "
            "cyclorama cannot be seated around a camera standing under it.")
    cam_data = scene.camera.data
    clip_end = float(getattr(cam_data, "clip_end", 200.0) or 200.0)
    aperture_radius_m = focus_distance_m = 0.0
    dof = getattr(cam_data, "dof", None)
    if dof is not None and getattr(dof, "use_dof", False):
        f_stop = float(getattr(dof, "aperture_fstop", 0.0) or 0.0)
        lens_mm = float(getattr(cam_data, "lens", 0.0) or 0.0)
        if f_stop > 0.0 and lens_mm > 0.0:
            aperture_radius_m = (lens_mm / (2.0 * f_stop)) / 1000.0
        focus_distance_m = float(getattr(dof, "focus_distance", 0.0) or 0.0)
    derived_radius = required_floor_radius(
        corner_rays, placement, camera_origin, camera_forward,
        clip_end=clip_end, aperture_radius_m=aperture_radius_m,
        focus_distance_m=focus_distance_m)
    legacy_min = max(radius * 14.0, 2.0)
    disc_radius = max(derived_radius, legacy_min)
    # SHAPE constant, not a safety margin: the fillet scales with the
    # product so a 0.5 m floor for a tiny product still gets a usable cove.
    fillet_radius = max(2.0 * radius, 0.5)
    wall_radius = disc_radius + fillet_radius
    cam_radial = math.hypot(camera_origin[0] - placement[0],
                            camera_origin[1] - placement[1])
    if cam_radial >= wall_radius:
        raise RuntimeError(
            f"CYC_CAMERA_OUTSIDE: camera stands at/outside the cyclorama "
            f"wall cylinder (radial {cam_radial:.2f} m >= wall radius "
            f"{wall_radius:.2f} m); the coverage argument requires the "
            f"camera inside the wall.")
    # The r_c floor gives a nominal wall when every corner ray stays below
    # the horizon; H is the profile height above the seat.
    wall_height = max(required_wall_height(
        corner_rays, placement, camera_origin, camera_forward, wall_radius,
        clip_end=clip_end, aperture_radius_m=aperture_radius_m,
        focus_distance_m=focus_distance_m), fillet_radius)
    verts, faces = cyc_mesh_data(disc_radius, wall_height, fillet_radius,
                                 placement)
    mesh = bpy.data.meshes.new(FLOOR_OBJECT_NAME)
    mesh.from_pydata(verts, [], faces)
    if mesh.validate() is True:
        raise RuntimeError(
            "CYC_MESH_INVALID: mesh.validate() rejected the cyclorama "
            "geometry; a silently 'fixed' mesh would differ from the "
            "derived profile.")
    for poly in mesh.polygons:
        poly.use_smooth = True
    floor = bpy.data.objects.new(FLOOR_OBJECT_NAME, mesh)
    floor.name = FLOOR_OBJECT_NAME
    bpy.context.scene.collection.objects.link(floor)
    mat = bpy.data.materials.new(name=FLOOR_MATERIAL_NAME)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = hex_to_linear_rgb(
            FLOOR_COLOR_HEX)
        bsdf.inputs["Roughness"].default_value = CYC_ROUGHNESS
    floor.data.materials.clear()
    floor.data.materials.append(mat)
    print(f"[MSP Render] Studio cyclorama created: {FLOOR_OBJECT_NAME} "
          f"(disc r={disc_radius:.2f} m [derived {derived_radius:.2f} m vs "
          f"legacy minimum {legacy_min:.2f} m], fillet r={fillet_radius:.2f} m, "
          f"wall to z={placement[2] + wall_height:.2f} m, seated at product "
          f"ground z={placement[2]:.3f} m, neutral matte finish).")
    return floor


def apply_color_management(scene, color_spec: Dict[str, Any]):
    vs = scene.view_settings
    try:
        scene.display_settings.display_device = color_spec.get("display_device", "sRGB")
    except Exception:
        pass
    for attr, key, default in (("view_transform", "view_transform", "AgX"),
                               ("look", "look", "AgX - Medium High Contrast")):
        want = color_spec.get(key, default)
        try:
            setattr(vs, attr, want)
        except Exception:
            print(f"[MSP Render] Color management: '{want}' unavailable for {attr}.")
    try:
        vs.exposure = color_spec.get("exposure", 0.0)
        vs.gamma = color_spec.get("gamma", 1.0)
    except Exception:
        pass
    print(f"[MSP Render] Color: {vs.view_transform} / {vs.look} / exposure {vs.exposure}.")


def apply_depth_of_field(scene, camera_spec: Dict[str, Any], target):
    """Real product photography is never uniformly sharp front to back."""
    dof_spec = camera_spec.get("depth_of_field") or {}
    cam_obj = scene.camera
    if not cam_obj or not dof_spec.get("enabled", False):
        return
    cam = cam_obj.data
    cam.dof.use_dof = True
    cam.dof.aperture_fstop = dof_spec.get("f_stop", 8.0)
    cam.dof.aperture_blades = dof_spec.get("blades", 8)
    focus_name = dof_spec.get("focus_object")
    focus_obj = bpy.data.objects.get(focus_name) if focus_name else None
    if focus_obj:
        cam.dof.focus_object = focus_obj
    else:
        cam.dof.focus_distance = dof_spec.get(
            "focus_distance", (target - cam_obj.location).length)
    print(f"[MSP Render] DOF on: f/{cam.dof.aperture_fstop} at "
          f"{cam.dof.focus_distance:.2f} m.")


def apply_photoreal_pass(scene, manifest: Dict[str, Any], target=None):
    """Every photorealism upgrade that costs no geometry and no file size."""
    photo = manifest.get("photoreal", {})
    if not photo.get("enabled", True):
        print("[MSP Render] Photoreal pass disabled by manifest.")
        return
    # Surface response first, then bevel - inject_bevel_shading rewires the
    # Normal input and must see the final node graph.
    polish_cad_materials(manifest.get("material_polish", {}))
    apply_powder_coat(photo.get("powder_coat", {}))
    apply_metal_finish(photo.get("metal_finish", {}))

    bevel = photo.get("bevel", {})
    if bevel.get("enabled", True):
        inject_bevel_shading(radius=bevel.get("radius_m", 0.0004),
                             samples=bevel.get("samples", 4))
    apply_cycles_quality(scene, photo.get("quality", {}))
    apply_color_management(scene, manifest.get("output", {}).get("color", {}))
    if target is not None:
        apply_depth_of_field(scene, manifest.get("camera", {}), target)


MATTE_TOLERANCE = 1.5 / 255.0


def _read_alpha(img):
    """Alpha channel of a loaded Blender image as a flat float sequence."""
    n = img.size[0] * img.size[1] * img.channels
    try:
        import numpy as np
    except ImportError:
        return list(img.pixels)[3::4]
    buf = np.empty(n, dtype=np.float32)
    img.pixels.foreach_get(buf)
    return buf[3::4]


def _write_grey(matte, alpha):
    """Fill a generated image with `alpha` replicated across RGB, A = 1."""
    try:
        import numpy as np
    except ImportError:
        out = []
        for a in alpha:
            out.extend((a, a, a, 1.0))
        matte.pixels = out
        return
    flat = np.empty(len(alpha) * 4, dtype=np.float32)
    flat[0::4] = alpha
    flat[1::4] = alpha
    flat[2::4] = alpha
    flat[3::4] = 1.0
    matte.pixels.foreach_set(flat)


def _assert_matte_matches(mask_path, alpha):
    """Re-read the saved matte and prove it carries the beauty alpha.

    A silently blank mask.png survived a full verification cycle once; the
    matte is cheap to check and expensive to get wrong, so the write is
    proven here rather than trusted.
    """
    check = bpy.data.images.load(mask_path, check_existing=False)
    try:
        # Read it back the way it was written, or the sRGB->linear transform on
        # load would shift every sample and fail a matte that is actually fine.
        check.colorspace_settings.name = 'Non-Color'
        n = check.size[0] * check.size[1] * check.channels
        if check.size[0] * check.size[1] != len(alpha):
            raise RuntimeError(
                f"MATTE_DIMENSION_MISMATCH: {mask_path} is {tuple(check.size)}")
        try:
            import numpy as np
        except ImportError:
            written = list(check.pixels)[0::4]
            worst = max(abs(float(w) - float(a)) for w, a in zip(written, alpha))
            span = max(written) - min(written)
        else:
            buf = np.empty(n, dtype=np.float32)
            check.pixels.foreach_get(buf)
            written = buf[0::4]
            worst = float(np.abs(written - np.asarray(alpha, dtype=np.float32)).max())
            span = float(written.max() - written.min())
    finally:
        bpy.data.images.remove(check)
    if span == 0.0:
        raise RuntimeError(f"MATTE_DEGENERATE: {mask_path} is a single flat value")
    if worst > MATTE_TOLERANCE:
        raise RuntimeError(
            f"MATTE_ALPHA_MISMATCH: {mask_path} differs from beauty alpha by {worst:.4f}")


def write_matte_pass(output_dir: str, source_filename: str = "beauty.png"):
    """
    Writes mask.png (the alpha matte) next to beauty.png.

    Blender 5.x replaced scene.node_tree with scene.compositing_node_group and
    dropped the Composite node, so the old File Output graph no longer builds.
    The matte is the only extra pass the compositor actually needs, and it is
    already sitting in the beauty pass's alpha channel - so it is cheaper and far
    more predictable to split it out directly than to rebuild a node graph that
    changes shape every Blender release.
    """
    beauty = os.path.join(output_dir, source_filename)
    if not os.path.exists(beauty):
        raise RuntimeError(
            f"MISSING_BEAUTY: required alpha matte has no beauty source: {beauty}")
    mask_path = os.path.join(output_dir, "mask.png")
    img = bpy.data.images.load(beauty, check_existing=False)
    try:
        w, h = img.size
        alpha = _read_alpha(img)
        matte = bpy.data.images.new("MSP_Matte", width=w, height=h, alpha=False)
        try:
            # The matte is data, not colour - saving it through the view transform
            # would gamma-shift the edges and soften the silhouette.
            #
            # This MUST be set before the pixel write. Assigning
            # colorspace_settings on a generated image frees and regenerates its
            # buffer from generated_color (opaque black), so setting it
            # afterwards silently discards the matte and writes a blank mask.
            matte.colorspace_settings.name = 'Non-Color'
            _write_grey(matte, alpha)
            matte.filepath_raw = mask_path
            matte.file_format = 'PNG'
            matte.save()
        finally:
            bpy.data.images.remove(matte)
        _assert_matte_matches(mask_path, alpha)
        print(f"[MSP Render] Wrote alpha matte: {mask_path}")
    finally:
        bpy.data.images.remove(img)


def _build_hash_text(value: Any, default: str = "unknown") -> str:
    """`bpy.app.build_hash` is **bytes** in Blender, and json cannot serialise it.

    Left undecoded, `json.dump` raised TypeError partway through writing
    `render-report.json`, which landed truncated at 158 bytes - mid-key at
    `"build": ` - and aborted the job after a perfectly good render. Every other
    caller in the repo already decodes (`scripts/cloud_blender_probe.py`,
    `scripts/prepare_scene.py`, `scripts/verify_scene.py`); this one did not, and
    the unit stub handed it a `str`, so no test could see it.

    A str passes through unchanged so the stubbed-bpy tests and any future
    Blender that hands back text both keep working.
    """
    if isinstance(value, (bytes, bytearray)):
        value = bytes(value).decode("ascii", "replace")
    return value or default


def _render_report(enabled_compute_devices: list, cpu_in_mix: bool,
                   prepare_seconds: float, render_seconds: float,
                   total_seconds: float,
                   beauty_render_seconds: Optional[float] = None,
                   matte_render_seconds: Optional[float] = None) -> Dict[str, Any]:
    """The worker-side render report consumed by the remote-job contract."""
    timings: Dict[str, Any] = {
        "prepare": max(0.0, prepare_seconds),
        "render": max(0.0, render_seconds),
        "total": max(0.0, total_seconds),
    }
    # Floor mode names its two paid passes explicitly; every legacy report
    # keeps its exact historical shape (no extra keys when not floor mode).
    if beauty_render_seconds is not None:
        timings["beauty_render_seconds"] = max(0.0, beauty_render_seconds)
    if matte_render_seconds is not None:
        timings["matte_render_seconds"] = max(0.0, matte_render_seconds)
    return {
        "compute": {
            "enabled_devices": enabled_compute_devices,
            "cpu_in_mix": cpu_in_mix,
            # gpu_evidence is deliberately absent: the worker cannot sample
            # nvidia-smi for itself. The dispatching harness supplies samples and
            # _normalise_compute adjudicates them.
        },
        "runtime": {
            "blender_version": getattr(bpy.app, "version_string",
                                       ".".join(str(part) for part in bpy.app.version)),
            "image": os.environ.get("MSP_IMAGE_ID", "unknown"),
            "build": _build_hash_text(getattr(bpy.app, "build_hash", None)),
        },
        "timings": timings,
    }


def pin_render_seed(scene) -> Optional[Dict[str, Any]]:
    """Pin the Cycles seed for floor mode's paired renders; returns saved state.

    The beauty frame and its floor-hidden matte must share one stochastic
    state - pinning only the matte (as an earlier draft did) leaves the two
    passes sampled from different noise. The seed is pinned for BOTH renders
    in floor mode only; restore_render_seed puts everything back, including
    on failure.
    """
    cycles = getattr(scene, "cycles", None)
    if cycles is None:
        return None
    saved = {"seed": getattr(cycles, "seed", None),
             "use_animated_seed": getattr(cycles, "use_animated_seed", None)}
    try:
        cycles.use_animated_seed = False
        cycles.seed = 0
    except Exception:
        pass
    return saved


def restore_render_seed(scene, saved: Optional[Dict[str, Any]]) -> None:
    """Undo pin_render_seed; safe with None (no pin was taken)."""
    if not saved:
        return
    cycles = getattr(scene, "cycles", None)
    for attr, value in (("seed", saved["seed"]),
                        ("use_animated_seed", saved["use_animated_seed"])):
        if value is not None:
            try:
                setattr(cycles, attr, value)
            except Exception:
                pass


def render_floor_hidden_matte(scene, floor_obj, output_dir: str) -> float:
    """Second render: product-only cutout with the floor hidden.

    Identical camera, resolution, DOF and product graph - the ONLY mutations
    are the ones a floor-hidden transparent matte needs (film transparent
    again, floor hidden, seed pinned, denoising off: denoising acts on colour
    and the matte consumes alpha only). Every mutated piece of render state is
    restored in a finally block, including on failure, and the opaque beauty
    file is never touched.
    """
    render = scene.render
    cycles = getattr(scene, "cycles", None)
    is_cycles = getattr(render, "engine", None) == "CYCLES"
    saved = {
        "filepath": render.filepath,
        "film_transparent": render.film_transparent,
        "floor_hidden": floor_obj.hide_render,
        "samples": getattr(cycles, "samples", None),
        "seed": getattr(cycles, "seed", None),
        "animated_seed": getattr(cycles, "use_animated_seed", None),
        "denoising": getattr(cycles, "use_denoising", None),
    }
    try:
        render.filepath = os.path.join(output_dir, "beauty-matte.png")
        render.film_transparent = True
        floor_obj.hide_render = True
        if cycles is not None and is_cycles:
            # Pin the seed: the beauty frame and its matte must not carry
            # different stochastic states, and an animated seed would make
            # the second pass a different sample of the same noise.
            try:
                cycles.use_animated_seed = False
                cycles.seed = 0
                cycles.use_denoising = False
            except Exception:
                pass
        print(f"[MSP Render] Rendering product-only matte pass: "
              f"{render.filepath} (floor hidden, seed pinned, denoise off).")
        started = time.monotonic()
        bpy.ops.render.render(write_still=True)
        seconds = time.monotonic() - started
        # The cutout is split from the matte render's own alpha - never from
        # the opaque beauty, whose alpha would name the whole floor.
        write_matte_pass(output_dir, source_filename="beauty-matte.png")
        return seconds
    finally:
        render.filepath = saved["filepath"]
        render.film_transparent = saved["film_transparent"]
        floor_obj.hide_render = saved["floor_hidden"]
        if cycles is not None:
            for attr, value in (("samples", saved["samples"]),
                                ("seed", saved["seed"]),
                                ("use_animated_seed", saved["animated_seed"]),
                                ("use_denoising", saved["denoising"])):
                if value is not None:
                    try:
                        setattr(cycles, attr, value)
                    except Exception:
                        pass


def execute_render_job(manifest: Dict[str, Any]):
    """Main execution function inside Blender."""
    _t04_started = time.monotonic()
    # Cheap, loud manifest validation before anything expensive happens.
    floor_mode_on = validate_output_config(manifest)
    cad_info = manifest["cad_source"]
    file_path = cad_info["file_path"]
    format_type = cad_info.get("format", "").lower()
    if not format_type:
        format_type = file_path.split('.')[-1].lower()

    # Auto-detect real file signature (guards against GLB saved as .blend or vice-versa)
    is_real_blend = False
    is_real_glb = False
    with open(file_path, "rb") as f:
        head = f.read(16)
        if head.startswith(b"BLENDER") or head.startswith(b"\x1f\x8b"):
            is_real_blend = True
        elif head.startswith(b"glTF"):
            is_real_glb = True

    if is_real_blend or (format_type == "blend" and not is_real_glb):
        print(f"[MSP Render] Opening native Blender scene: {file_path}")
        try:
            bpy.ops.wm.open_mainfile(filepath=file_path)
            center, radius = get_scene_bounds()
        except Exception as e:
            print(f"[MSP Render] open_mainfile failed ({e}). Falling back to GLTF import...")
            clean_scene()
            bpy.ops.import_scene.gltf(filepath=file_path)
            center, radius = normalize_model_bounds()
    else:
        clean_scene()
        import_cad_model(file_path, "glb" if is_real_glb else format_type)
        center, radius = normalize_model_bounds()

    # Automatic Geometry Refinements:
    # 1. Fix faceted/boxy door latches and handles with smooth shading and subdivision
    # 2. Handle misplaced vibration isolators
    hide_isolators = manifest.get("geometry", {}).get("hide_misplaced_isolators", True)
    smooth_latches = manifest.get("geometry", {}).get("smooth_hardware", True)

    for obj in bpy.context.scene.objects:
        if obj.type == "MESH":
            name_lower = obj.name.lower()
            if smooth_latches and any(k in name_lower for k in ["latch", "handle", "lock", "hinge", "catch", "recess"]):
                try:
                    obj.select_set(True)
                    bpy.context.view_layer.objects.active = obj
                    # CAD exports carry custom split normals; shade_smooth()/SUBSURF
                    # destroys them and makes flat machined faces look melted.
                    if getattr(obj.data, "has_custom_normals", False):
                        print(f"[MSP Render] Skipping smoothing on {obj.name} "
                              f"(has CAD custom normals).")
                        continue
                    bpy.ops.object.shade_smooth()
                    if not any(m.type == "SUBSURF" for m in obj.modifiers):
                        sub = obj.modifiers.new(name="Hardware_Subdiv", type="SUBSURF")
                        sub.levels = 1
                        sub.render_levels = 1
                except Exception:
                    pass
            
            if hide_isolators and any(k in name_lower for k in ["isolator", "iso_mount", "vibration", "puck", "round_foot", "iso_"]):
                # Hide external isolators that sit out in front of the skid
                obj.hide_render = True
                print(f"[MSP Render] Hiding misplaced external isolator mesh: {obj.name}")

    # Materials
    livery_spec = manifest.get("livery", {})
    if livery_spec.get("preset") == "preserve_existing":
        print("[MSP Render] Preserving existing scene materials.")
    else:
        apply_livery_materials(livery_spec)

    # Camera
    cam_preset = manifest.get("camera", {}).get("preset", "P1_FRONT_ISO")
    # Allow a manifest to name a specific camera that already lives in the .blend.
    # Close-up detail shots are far easier to aim by placing a camera in the file
    # than by tuning azimuth/elevation/target_offset ratios against scene bounds.
    wanted_cam = manifest.get("camera", {}).get("scene_camera_name")
    if wanted_cam:
        cam_obj = bpy.data.objects.get(wanted_cam)
        if cam_obj and cam_obj.type == 'CAMERA':
            bpy.context.scene.camera = cam_obj
            print(f"[MSP Render] Using named scene camera: {wanted_cam}")
        else:
            available = [o.name for o in bpy.data.objects if o.type == 'CAMERA']
            raise KeyError(f"camera.scene_camera_name '{wanted_cam}' not found. "
                           f"Cameras in file: {available}")
    elif cam_preset in ["USE_SCENE_CAMERA", "PRESERVE_EXISTING"] and bpy.context.scene.camera:
        print(f"[MSP Render] Using existing scene camera: {bpy.context.scene.camera.name}")
    else:
        setup_camera(manifest.get("camera", {}), center, radius)

    # Ensure clean transparent alpha: inspect all scene meshes and hide any ground/floor/terrain geometry
    print("[MSP Render] Inspecting scene mesh objects for ground/floor geometry:")
    ground_keywords = [
        "ground", "floor", "plane", "backdrop", "cyclorama", "cove", "stage",
        "dirt", "soil", "mud", "sand", "pit", "terrain", "surface", "earth",
        "land", "puddle", "asphalt", "landscape", "env", "plate"
    ]
    mat_keywords = ["dirt", "soil", "mud", "sand", "ground", "floor", "earth", "brown", "rock", "pit", "terrain"]

    for obj in bpy.context.scene.objects:
        if obj.type == "MESH" and obj.name != "GroundShadowCatcher":
            name_lower = obj.name.lower()
            mat_names = [m.name.lower() for m in obj.data.materials if m]
            dim = obj.dimensions
            
            is_name_match = any(k in name_lower for k in ground_keywords)
            is_mat_match = any(any(k in mn for k in mat_keywords) for mn in mat_names)
            # Detect any large flat horizontal slab (much wider/longer than the pump package)
            # A skid rail or a long side panel can easily be >5 m and <1 m tall.
            # Only treat something as ground if it is genuinely slab-like AND
            # centred near z=0, so structural members are never silently dropped.
            _z_centre = abs(obj.matrix_world.translation.z)
            is_flat_ground_dim = (
                (dim.x > 8.0 and dim.y > 8.0) and dim.z < 0.25 and _z_centre < 0.5
            )
            is_cube_ground = ("cube" in name_lower and is_flat_ground_dim)

            if is_name_match or is_mat_match or is_flat_ground_dim or is_cube_ground:
                obj.hide_render = True
                obj.hide_viewport = True
                print(f"[MSP Render] -> HID ground/floor object: '{obj.name}' (mats: {mat_names}, dims: {dim.x:.1f}x{dim.y:.1f}x{dim.z:.1f}m)")
            else:
                print(f"[MSP Render]    Kept machine mesh: '{obj.name}' (dims: {dim.x:.1f}x{dim.y:.1f}x{dim.z:.1f}m)")

    # Lighting
    lighting_spec = manifest.get("lighting", {})
    want_shadow_catcher = lighting_spec.get("shadow_catcher", False)

    # The studio floor is created AFTER the photorealism pass (see below):
    # the ground-keyword hide pass above must never eat it, no generic
    # material pass may touch its fixed neutral finish, and the lighting
    # branches only need to know floor mode is on to suppress the catcher.
    
    # Remove any stray GroundShadowCatcher objects to ensure clean transparent alpha
    for obj in list(bpy.context.scene.objects):
        if "groundshadowcatcher" in obj.name.lower():
            bpy.data.objects.remove(obj, do_unlink=True)

    # Reset world background to neutral black to prevent world shader from filling transparency
    world = bpy.context.scene.world
    if world and world.use_nodes and world.node_tree:
        for node in world.node_tree.nodes:
            if node.type == "BACKGROUND":
                node.inputs["Color"].default_value = (0.0, 0.0, 0.0, 1.0)
                node.inputs["Strength"].default_value = 0.0

    if lighting_spec.get("preset") == "preserve_existing" and any(obj.type == 'LIGHT' for obj in bpy.context.scene.objects):
        print("[MSP Render] Preserving existing scene lighting with front fill balancing.")
        # Add a soft front-quarter fill light so front intake honeycomb and flanged ports are not in deep shadow
        if not any(obj.name == "Front_Face_Fill" for obj in bpy.context.scene.objects):
            fill_light_data = bpy.data.lights.new(name="Front_Face_Fill", type='AREA')
            fill_light_data.energy = 550.0 * (radius ** 1.3)
            fill_light_data.size = radius * 2.2
            fill_light_data.color = (1.0, 0.98, 0.95)
            fill_light_obj = bpy.data.objects.new("Front_Face_Fill", fill_light_data)
            # Position at front-left (azimuth 35 deg, elevation 20 deg) to fill front louvers & ports
            fill_light_obj.location = (center.x + radius * 2.6, center.y - radius * 2.6, center.z + radius * 1.8)
            direction = mathutils.Vector((center.x, center.y, center.z * 0.7)) - fill_light_obj.location
            fill_light_obj.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()
            bpy.context.scene.collection.objects.link(fill_light_obj)
        if want_shadow_catcher and not floor_mode_on:
            bpy.ops.mesh.primitive_plane_add(size=radius * 12.0, location=(0, 0, 0))
            plane = bpy.context.active_object
            plane.name = "GroundShadowCatcher"
            plane.is_shadow_catcher = True
            try:
                plane.cycles.is_shadow_catcher = True
            except Exception:
                pass
            plane.data.materials.clear()
            mute_catcher_bounce(plane)
    else:
        setup_lighting(lighting_spec, center, radius,
                       suppress_shadow_catcher=floor_mode_on)

    out_spec = manifest.get("output", {})
    scene = bpy.context.scene
    scene.render.engine = out_spec.get("engine", "CYCLES")
    scene.render.resolution_x = out_spec.get("width", 1920)
    scene.render.resolution_y = out_spec.get("height", 1080)
    scene.render.film_transparent = film_transparent_for(out_spec)
    scene.render.image_settings.file_format = 'PNG'
    scene.render.image_settings.color_mode = 'RGBA'

    output_dir = os.path.abspath(out_spec.get("output_dir", "./output"))
    os.makedirs(output_dir, exist_ok=True)
    scene.render.filepath = os.path.join(output_dir, "beauty.png")
    require_gpu = manifest.get("require_gpu", False)
    enabled_compute_devices = []
    cpu_in_mix = scene.render.engine != "CYCLES"

    if scene.render.engine == "CYCLES":
        cycles = scene.cycles
        cycles.samples = out_spec.get("samples", 128)
        # The manifest's denoiser choice was being ignored here, which made
        # "NONE" unrepresentable - and OIDN is exactly what erases fine surface
        # detail like powder-coat orange peel, so it has to be switchable.
        denoiser = str(out_spec.get("denoiser", "OPENIMAGEDENOISE")).upper()
        cycles.use_denoising = denoiser not in ("NONE", "OFF", "FALSE")
        if cycles.use_denoising and denoiser in ("OPENIMAGEDENOISE", "OPTIX"):
            try:
                cycles.denoiser = denoiser
            except (TypeError, AttributeError):
                pass
        print(f"[MSP Render] Denoiser: {denoiser} (enabled={cycles.use_denoising}).")
        try:
            cycles.device = 'GPU'
            prefs = bpy.context.preferences.addons['cycles'].preferences
            # Picking a backend is not enough - each device must be switched on,
            # otherwise Cycles silently falls back to CPU on the Modal worker.
            # HIP/ONEAPI matter locally: the workstation this demo runs on is an
            # AMD Radeon 780M, which only exposes HIP. Without it every local
            # render silently drops to CPU and takes minutes instead of seconds.
            for _backend in ('OPTIX', 'CUDA', 'HIP', 'ONEAPI'):
                try:
                    prefs.compute_device_type = _backend
                    prefs.get_devices()
                    _on = [d for d in prefs.devices if d.type == _backend]
                    if _on:
                        for d in prefs.devices:
                            d.use = (d.type == _backend)
                        enabled_compute_devices = [{"name": d.name, "type": d.type}
                                                  for d in prefs.devices if d.use]
                        cpu_in_mix = any(d.type == 'CPU' and d.use for d in prefs.devices)
                        print(f"[MSP Render] GPU backend {_backend}: "
                              f"{[d.name for d in _on]}")
                        break
                except Exception:
                    continue
            else:
                if require_gpu:
                    raise RuntimeError("GPU_REQUIRED: no GPU device was enabled")
                print('[MSP Render] WARNING: no GPU device enabled, rendering on CPU.')
        except Exception as exc:
            if require_gpu:
                # The for-else raise above lands here too; re-wrapping it would
                # emit "GPU_REQUIRED: GPU_REQUIRED: ...".
                if isinstance(exc, RuntimeError) and str(exc).startswith("GPU_REQUIRED"):
                    raise
                raise RuntimeError(f"GPU_REQUIRED: {exc}") from exc
            pass

    # No GPU device was enabled, so whatever the engine, this render is on the CPU.
    # Reporting cpu_in_mix False here is exactly the silent-CPU-fallback dishonesty
    # the require_gpu contract exists to remove.
    if not enabled_compute_devices:
        cpu_in_mix = True

    # --- photorealism pass (bevel shading, light transport, colour, DOF) ---
    try:
        apply_photoreal_pass(scene, manifest, target=center)
    except ValueError:
        # A ValueError here is a manifest material error (reassign rule,
        # metal_finish spec). Downgrading it to a warning would report a
        # successful render over unfinished materials.
        raise
    except Exception as e:
        print(f"[MSP Render] WARNING: photoreal pass failed: {e}")

    # The studio floor is created HERE - after the ground-keyword hide pass
    # (so the repo's own ground defences cannot eat it) and after the
    # photorealism pass (so CAD polish / bevel injection never touches its
    # fixed neutral material). It seats at the product's measured ground
    # bounds, not an assumed z=0: a native .blend is never re-normalised.
    floor_obj = (build_studio_floor(radius, scene=scene)
                 if floor_mode_on else None)

    print(f"[MSP Render] Starting render for job {manifest.get('job_id')}...")
    # Floor mode pins the seed for BOTH renders so the beauty frame and its
    # matte share one stochastic state; restored even on failure.
    _t04_seed_state = pin_render_seed(scene) if floor_mode_on else None
    _t04_beauty_seconds = None
    _t04_matte_seconds = None
    _t04_render_started = time.monotonic()
    try:
        _t04_beauty_started = time.monotonic()
        bpy.ops.render.render(write_still=True)
        if floor_mode_on:
            # A measured wall time, never a derived remainder: the floor
            # report must name what each paid pass actually cost.
            _t04_beauty_seconds = time.monotonic() - _t04_beauty_started
        print(f"[MSP Render] Beauty pass written: {scene.render.filepath}")

        if out_spec.get("passes", {}).get("alpha_mask", True):
            if floor_mode_on and floor_obj is not None:
                # Floor mode: mask.png must describe the PRODUCT, and the
                # opaque beauty's alpha describes the whole lit scene. The
                # second floor-hidden render supplies the independent cutout.
                _t04_matte_seconds = render_floor_hidden_matte(
                    scene, floor_obj, output_dir)
            else:
                write_matte_pass(output_dir)
    finally:
        if _t04_seed_state is not None:
            restore_render_seed(scene, _t04_seed_state)

    if "require_gpu" in manifest:
        # Spans BOTH passes plus matte extraction in floor mode, so the
        # legacy render_seconds contract never undercounts paid work.
        _t04_render_seconds = time.monotonic() - _t04_render_started
        _t04_total_seconds = time.monotonic() - _t04_started
        _t04_report = _render_report(enabled_compute_devices, cpu_in_mix,
                                     _t04_render_started - _t04_started,
                                     _t04_render_seconds, _t04_total_seconds,
                                     beauty_render_seconds=_t04_beauty_seconds,
                                     matte_render_seconds=_t04_matte_seconds)
        # Serialise fully before opening the file. Streaming straight into the
        # handle means an unserialisable value writes bytes up to the point it
        # fails and leaves a truncated, invalid report on disk - which
        # `_collect_artifacts` deliberately excludes from artifact hashing, so
        # nothing downstream would catch it. A failure here still raises: a job
        # that renders without recording what rendered it is exactly the silent
        # dishonesty the T04 contract exists to remove.
        _t04_payload = json.dumps(_t04_report, sort_keys=True, allow_nan=False) + "\n"
        with open(os.path.join(output_dir, "render-report.json"), "w", encoding="utf-8") as _t04_report_file:
            _t04_report_file.write(_t04_payload)

    print(f"[MSP Render] Render completed successfully. Output path: {output_dir}")

def resolve_manifest_paths(manifest: Dict[str, Any], manifest_path: str) -> Dict[str, Any]:
    """
    Rewrites the relative paths inside a manifest to absolute ones.

    Blender is launched with an unpredictable working directory, so a manifest
    that says "backgrounds/env_studio-dark.png" would otherwise silently resolve
    to nothing and the HDRI world would be dropped without an error. Relative
    paths are resolved against the project root (the manifest's parent's parent
    when it lives in jobs/, else the manifest's own directory), then the CWD.
    """
    manifest_dir = os.path.dirname(os.path.abspath(manifest_path))
    search_roots = [manifest_dir, os.path.dirname(manifest_dir), os.getcwd()]

    def _resolve(value: Optional[str]) -> Optional[str]:
        if not value or os.path.isabs(value):
            return value
        for root in search_roots:
            candidate = os.path.normpath(os.path.join(root, value))
            if os.path.exists(candidate):
                return candidate
        return value

    for section, key in (("cad_source", "file_path"),
                         ("lighting", "hdri_path"),
                         ("compositing", "background_plate")):
        block = manifest.get(section)
        if isinstance(block, dict) and block.get(key):
            resolved = _resolve(block[key])
            if resolved != block[key]:
                print(f"[MSP Render] Resolved {section}.{key} -> {resolved}")
            block[key] = resolved

    out = manifest.get("output", {})
    if out.get("output_dir") and not os.path.isabs(out["output_dir"]):
        out["output_dir"] = os.path.normpath(
            os.path.join(os.path.dirname(manifest_dir) or os.getcwd(), out["output_dir"]))
    return manifest


# Entrypoint when invoked via CLI inside Blender
if IN_BLENDER and "--" in sys.argv:
    argv = sys.argv[sys.argv.index("--") + 1:]
    if argv and os.path.exists(argv[0]):
        with open(argv[0], 'r', encoding='utf-8') as f:
            manifest_data = json.load(f)
        manifest_data = resolve_manifest_paths(manifest_data, argv[0])
        execute_render_job(manifest_data)

# ==============================================================================
# MODAL SERVERLESS DEFINITION
# ==============================================================================

try:
    import modal
    
    app = modal.App("msp-render-worker")
    
    blender_image = (
        modal.Image.debian_slim(python_version="3.11")
        .apt_install(
            "wget", "xz-utils", "libglu1-mesa", "libxi6",
            "libxrender1", "libxfixes3", "libxcursor1", "libxinerama1",
            "libxkbcommon0", "libsm6", "libxxf86vm1", "libgl1"
        )
        .run_commands(
            "wget -q https://download.blender.org/release/Blender5.1/blender-5.1.2-linux-x64.tar.xz -O /tmp/blender.tar.xz || wget -q https://download.blender.org/release/Blender5.1/blender-5.1.0-linux-x64.tar.xz -O /tmp/blender.tar.xz",
            "tar -xf /tmp/blender.tar.xz -C /opt",
            "ln -s /opt/blender-5*/blender /usr/local/bin/blender",
            "rm /tmp/blender.tar.xz"
        )
    )

    @app.function(image=blender_image, gpu="L4", timeout=300)
    def render_cad_job_serverless(manifest_json_str: str, cad_file_bytes: bytes) -> Dict[str, bytes]:
        """
        Runs headless Blender on a serverless cloud GPU (NVIDIA L4).
        Takes job manifest and CAD binary bytes; returns dictionary of rendered pass images.
        """
        import subprocess
        import tempfile

        manifest = json.loads(manifest_json_str)

        with tempfile.TemporaryDirectory() as tmpdir:
            cad_ext = manifest["cad_source"].get("format", "glb").lower()
            if not cad_ext:
                cad_ext = manifest["cad_source"]["file_path"].split('.')[-1].lower()

            cad_path = os.path.join(tmpdir, f"model.{cad_ext}")
            with open(cad_path, 'wb') as f:
                f.write(cad_file_bytes)

            manifest["cad_source"]["file_path"] = cad_path
            out_dir = os.path.join(tmpdir, "output")
            manifest["output"]["output_dir"] = out_dir

            manifest_path = os.path.join(tmpdir, "job.json")
            with open(manifest_path, 'w', encoding='utf-8') as f:
                json.dump(manifest, f)

            script_path = os.path.join(tmpdir, "worker.py")
            with open(script_path, 'w', encoding='utf-8') as f:
                with open(__file__, 'r', encoding='utf-8') as src:
                    f.write(src.read())

            cmd = ["blender", "-b", "-P", script_path, "--", manifest_path]
            res = subprocess.run(cmd, capture_output=True, text=True)
            
            print(f"[Blender STDOUT]\n{res.stdout}")
            if res.stderr:
                print(f"[Blender STDERR]\n{res.stderr}")

            if res.returncode != 0:
                raise RuntimeError(f"Blender render failed with exit code {res.returncode}")

            artifacts = {}
            # Walk all generated image files in output directory and tmpdir
            for root, dirs, files in os.walk(tmpdir):
                for file in files:
                    if file.lower().endswith((".png", ".jpg", ".jpeg", ".exr")) and file != f"model.{cad_ext}":
                        img_path = os.path.join(root, file)
                        filename = os.path.basename(img_path)
                        with open(img_path, 'rb') as f:
                            artifacts[filename] = f.read()

            print(f"[Serverless Worker] Captured {len(artifacts)} image artifacts: {list(artifacts.keys())}")
            return artifacts

    @app.local_entrypoint()
    def main(manifest: str):
        """CLI local entrypoint for `modal run render_worker.py --manifest <job.json>`."""
        if not os.path.exists(manifest):
            raise FileNotFoundError(f"Manifest file not found: {manifest}")
        
        with open(manifest, 'r', encoding='utf-8') as f:
            data = json.load(f)

        cad_path = data["cad_source"]["file_path"]
        if not os.path.exists(cad_path):
            raise FileNotFoundError(f"CAD source file not found: {cad_path}")

        print(f"[Modal] Packaging CAD/Blend asset '{cad_path}' ({os.path.getsize(cad_path)} bytes)...")
        with open(cad_path, 'rb') as f:
            cad_bytes = f.read()

        print(f"[Modal] Submitting render job '{data.get('job_id')}' to serverless GPU...")
        artifacts = render_cad_job_serverless.remote(json.dumps(data), cad_bytes)

        out_dir = data["output"].get("output_dir", "./output")
        os.makedirs(out_dir, exist_ok=True)

        if not artifacts:
            print(f"[Modal] Warning: No image files were returned by the worker.")
        else:
            for fname, img_data in artifacts.items():
                out_file = os.path.join(out_dir, fname)
                with open(out_file, 'wb') as f:
                    f.write(img_data)
                print(f"[Modal] ✓ Saved pass: {out_file}")

        print(f"\n✓ Completed. Render passes saved to: {out_dir}")

except ImportError:
    pass

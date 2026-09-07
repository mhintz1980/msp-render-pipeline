from __future__ import annotations

"""
Headless Blender Render Worker for Myers-Seth Pumps (MSP) Pipeline.
Supports GLB, OBJ, and native .blend scenes with both local execution
and remote serverless dispatch via Modal.
"""

import sys
import os
import json
import math
import glob
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
    for obj in all_objs:
        if obj.parent is None:
            obj.location += offset

    new_center = mathutils.Vector((0, 0, dim.z / 2.0))
    return new_center, radius

def apply_livery_materials(livery_spec: Dict[str, Any]):
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
    for obj in bpy.context.scene.objects:
        if obj.type == 'MESH':
            name_lower = obj.name.lower()
            if any(k in name_lower for k in ["frame", "skid", "base", "bumper", "fork", "trailer", "fender", "axle", "hitch", "tank", "chassis"]):
                obj.data.materials.clear()
                obj.data.materials.append(frame_mat)
            elif any(k in name_lower for k in ["body", "panel", "door", "enclosure", "hood", "roof", "canopy", "louver", "sheet", "cover"]):
                obj.data.materials.clear()
                obj.data.materials.append(body_mat)


def setup_camera(camera_spec: Dict[str, Any], center: Any, radius: float):
    """Configures camera placement and target tracking."""
    azimuth = math.radians(camera_spec.get("azimuth_deg", 45.0))
    elevation = math.radians(camera_spec.get("elevation_deg", 14.0))
    focal_length = camera_spec.get("focal_length_mm", 50.0)
    
    # Increase distance multiplier from 3.2 to 3.85 to capture the entire enclosure and ceiling
    dist_mult = camera_spec.get("distance_multiplier", 3.85)
    distance = radius * dist_mult
    target = center.copy()
    # Target mid-upper height (0.85 of center Z) so the roof and ceiling are fully in frame
    target_offset = camera_spec.get("target_offset", [0.0, 0.0, 0.85])
    target.z = center.z * target_offset[2]

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

def setup_lighting(lighting_spec: Dict[str, Any], center: Any, radius: float):
    """Sets up calibrated studio softbox lights or physical outdoor sun/sky environment."""
    preset = lighting_spec.get("preset", "studio_dark")
    intensity = lighting_spec.get("intensity_multiplier", 1.0)
    hdri_path = lighting_spec.get("hdri_path")

    # Remove existing lights if replacing with fresh rig
    if preset != "preserve_existing":
        for obj in list(bpy.context.scene.objects):
            if obj.type == 'LIGHT':
                bpy.data.objects.remove(obj, do_unlink=True)

    # Ground plane shadow catcher
    catcher_obj = bpy.data.objects.get("GroundShadowCatcher")
    if not catcher_obj:
        bpy.ops.mesh.primitive_plane_add(size=radius * 14.0, location=(0, 0, 0))
        catcher_obj = bpy.context.active_object
        catcher_obj.name = "GroundShadowCatcher"
    catcher_obj.is_shadow_catcher = True

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
        bg_node.inputs["Strength"].default_value = 1.0 * intensity
    elif preset == "excavation_pit_sunlit":
        try:
            sky_tex = w_nodes.new(type="ShaderNodeTexSky")
            sky_tex.location = (-200, 0)
            sky_tex.sky_type = 'NISHITA'
            sky_tex.sun_disc = True
            sky_tex.sun_elevation = math.radians(38.0)
            sky_tex.sun_rotation = math.radians(-35.0)
            sky_tex.altitude = 15.0
            sky_tex.air_density = 1.0
            sky_tex.dust_density = 1.3
            sky_tex.ozone_density = 1.0
            w_links.new(sky_tex.outputs["Color"], bg_node.inputs["Color"])
            bg_node.inputs["Strength"].default_value = 0.85 * intensity
        except Exception:
            bg_node.inputs["Color"].default_value = (0.75, 0.85, 1.0, 1.0)
            bg_node.inputs["Strength"].default_value = 0.60 * intensity
    else:
        bg_node.inputs["Color"].default_value = (0.05, 0.05, 0.05, 1.0)
        bg_node.inputs["Strength"].default_value = 1.0

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


def setup_compositor_multipass(output_dir: str):
    """Sets up compositor nodes to export Beauty, Mask, and Depth passes."""
    os.makedirs(output_dir, exist_ok=True)
    scene = bpy.context.scene
    try:
        scene.use_nodes = True
    except Exception:
        pass
    tree = getattr(scene, "node_tree", None) or getattr(scene, "compositing_node_group", None) or getattr(scene, "compositor_node_tree", None)
    if tree is None:
        raise AttributeError("Compositor node tree not accessible on Scene")
    tree.nodes.clear()

    view_layer = scene.view_layers[0] if scene.view_layers else None
    if view_layer:
        view_layer.use_pass_z = True
        view_layer.use_pass_shadow = True

    render_layers = tree.nodes.new("CompositorNodeRLayers")
    render_layers.location = (0, 0)

    # CRITICAL: Compositor Output node is required for Blender render pipeline to execute!
    comp_out = tree.nodes.new("CompositorNodeComposite")
    comp_out.location = (450, 200)
    tree.links.new(render_layers.outputs["Image"], comp_out.inputs["Image"])

    # File Output node for passes
    file_out = tree.nodes.new("CompositorNodeOutputFile")
    file_out.location = (450, -50)
    file_out.base_path = output_dir
    file_out.format.file_format = 'PNG'
    file_out.format.color_mode = 'RGBA'

    file_out.file_slots[0].path = "beauty"
    tree.links.new(render_layers.outputs["Image"], file_out.inputs[0])

    file_out.file_slots.new("mask")
    tree.links.new(render_layers.outputs["Alpha"], file_out.inputs["mask"])

    norm_depth = tree.nodes.new("CompositorNodeNormalize")
    norm_depth.location = (240, -150)
    tree.links.new(render_layers.outputs["Depth"], norm_depth.inputs[0])
    
    file_out.file_slots.new("depth")
    tree.links.new(norm_depth.outputs[0], file_out.inputs["depth"])

def execute_render_job(manifest: Dict[str, Any]):
    """Main execution function inside Blender."""
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
                    bpy.ops.object.shade_smooth()
                    if not any(m.type == "SUBSURF" for m in obj.modifiers):
                        sub = obj.modifiers.new(name="Hardware_Subdiv", type="SUBSURF")
                        sub.levels = 1
                        sub.render_levels = 1
                except Exception:
                    pass
            
            if hide_isolators and any(k in name_lower for k in ["isolator", "vibration", "puck", "round_foot"]):
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
    if cam_preset in ["USE_SCENE_CAMERA", "PRESERVE_EXISTING"] and bpy.context.scene.camera:
        print(f"[MSP Render] Using existing scene camera: {bpy.context.scene.camera.name}")
    else:
        setup_camera(manifest.get("camera", {}), center, radius)

    # Lighting
    lighting_spec = manifest.get("lighting", {})
    if lighting_spec.get("preset") == "preserve_existing" and any(obj.type == 'LIGHT' for obj in bpy.context.scene.objects):
        print("[MSP Render] Preserving existing scene lighting.")
        if not any(obj.name == "GroundShadowCatcher" for obj in bpy.context.scene.objects):
            bpy.ops.mesh.primitive_plane_add(size=radius * 12.0, location=(0, 0, 0))
            plane = bpy.context.active_object
            plane.name = "GroundShadowCatcher"
            plane.is_shadow_catcher = True
    else:
        setup_lighting(lighting_spec, center, radius)

    out_spec = manifest.get("output", {})
    scene = bpy.context.scene
    scene.render.engine = out_spec.get("engine", "CYCLES")
    scene.render.resolution_x = out_spec.get("width", 1920)
    scene.render.resolution_y = out_spec.get("height", 1080)
    scene.render.film_transparent = True
    scene.render.image_settings.file_format = 'PNG'
    scene.render.image_settings.color_mode = 'RGBA'

    output_dir = os.path.abspath(out_spec.get("output_dir", "./output"))
    os.makedirs(output_dir, exist_ok=True)
    scene.render.filepath = os.path.join(output_dir, "beauty.png")

    if scene.render.engine == "CYCLES":
        cycles = scene.cycles
        cycles.samples = out_spec.get("samples", 128)
        cycles.use_denoising = True
        try:
            cycles.device = 'GPU'
            prefs = bpy.context.preferences.addons['cycles'].preferences
            prefs.compute_device_type = 'OPTIX'
        except Exception:
            pass

    try:
        setup_compositor_multipass(output_dir)
    except Exception as e:
        print(f"[MSP Render] Note: Multi-pass compositor setup bypassed in Blender 5.x ({e}). Rendering direct beauty pass.")

    print(f"[MSP Render] Starting render for job {manifest.get('job_id')}...")
    bpy.ops.render.render(write_still=True)
    print(f"[MSP Render] Render completed successfully. Output path: {output_dir}")

# Entrypoint when invoked via CLI inside Blender
if IN_BLENDER and "--" in sys.argv:
    argv = sys.argv[sys.argv.index("--") + 1:]
    if argv and os.path.exists(argv[0]):
        with open(argv[0], 'r', encoding='utf-8') as f:
            manifest_data = json.load(f)
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

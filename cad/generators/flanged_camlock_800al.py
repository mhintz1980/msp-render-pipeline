# Preserved from the `Text` datablock embedded in
# cad/RL300-SAFE-photoreal.blend, where Mark authored it to generate
# V2FTG-CAMLOCK-800AL-1/-2. It lives here instead because the T01/T02
# still-scene policy rejects embedded text and scripts outright, and
# prepare_scene.py blocks rather than removing them silently
# (UNSUPPORTED_DEPENDENCY on `texts:Text`).
#
# REVISION: this is Mark's second version, superseding the earlier
# `Flanged_Camlock_800AL` attempt. It produces `8in_Flange_x_8in_Camlock`:
# 13.50 in flange OD, 1.125 in thick, 11.75 in bolt circle, eight 0.875 in
# holes, 9.00 in cam OD on an 8.625 in neck. Measured in the assembly as
# 342.9 mm OD on a 149.22 mm bolt-circle radius, 136.53 mm long.
#
# Kept verbatim below as the authoritative record of what the fitting is
# dimensioned to. Not run by the pipeline.
"""
8" ANSI Class 150 Flange x 8" Male Camlock Adapter Geometry Generator
Compatible with Blender 3.x, 4.x, and 5.x.

Usage:
1. Open Blender.
2. Switch to the 'Scripting' workspace.
3. Click 'New' to create a new text block, paste this script, and click 'Run Script' (Alt+P).
"""

import math
import bpy
import bmesh

# ==============================================================================
# PARAMETRIC CONFIGURATION (Dimensions in INCHES)
# ==============================================================================

# Scaling:
# False: 1 Blender Unit = 1 Inch (typical for CAD / CAM modeling)
# True:  1 Blender Unit = 1 Meter (converts inches to meters via 0.0254)
SCALE_TO_METERS = True

# Flange Dimensions (ASME B16.5 Class 150, 8" NPS):
FLANGE_OD = 13.50           # Flange outer diameter
FLANGE_THICKNESS = 1.125    # Flange thickness (1-1/8")
BOLT_CIRCLE_DIA = 11.75     # Bolt circle PCD (11-3/4")
BOLT_HOLE_DIA = 0.875       # Bolt hole diameter (7/8" for 3/4" studs)
NUM_BOLT_HOLES = 8          # Quantity of flange bolt holes
BORE_ID = 7.80              # Internal flow bore diameter

# Sealing Face Options:
HAS_RAISED_FACE = True      # Set False for Flat Face (common on cast aluminum)
RAISED_FACE_DIA = 10.625    # 10-5/8" raised face diameter
RAISED_FACE_HEIGHT = 0.0625 # 1/16" standard Class 150 raised face height

# 8" Male Camlock Adapter Dimensions:
# - Set 8.975 for PTK (PT Coupling / Kuriyama)
# - Set 9.125 for NAE / Dixon (Andrews) / NECO
CAM_OD = 9.00               # Nominal male adapter OD
CAM_GROOVE_ROOT_DIA = 8.25  # Groove root diameter
CAM_GROOVE_WIDTH = 0.65     # Groove axial width
CAM_GROOVE_DIST = 1.30      # Center of groove distance from nose face
CAM_ADAPTER_LEN = 2.50      # Male shank insertion length to stop shoulder
NECK_OD = 8.625             # Intermediate neck OD (standard 8" pipe OD)

# Overall Length:
OVERALL_LENGTH = 5.375      # 5-3/8" compact casting (use 6.0 or 8.0 for spools)

# Mesh Topology & Resolution:
RADIAL_SEGMENTS = 96        # Circumferential revolution steps
GROOVE_SUBDIV = 12          # Sample subdivisions along the groove profile
BOLT_HOLE_SEGMENTS = 32     # Radial segments per bolt hole cutter
APPLY_BOOLEAN = True        # Automatically apply boolean modifier for bolt holes


def build_adapter_profile(scale_factor):
    """Calculates 2D cross-section coordinate points (R, Z) for revolution."""
    r_bore = (BORE_ID / 2.0) * scale_factor
    r_flange = (FLANGE_OD / 2.0) * scale_factor
    r_rf = (RAISED_FACE_DIA / 2.0) * scale_factor
    r_neck = (NECK_OD / 2.0) * scale_factor
    r_cam = (CAM_OD / 2.0) * scale_factor
    r_groove = (CAM_GROOVE_ROOT_DIA / 2.0) * scale_factor

    flange_thk = FLANGE_THICKNESS * scale_factor
    rf_h = (RAISED_FACE_HEIGHT * scale_factor) if HAS_RAISED_FACE else 0.0
    oal = OVERALL_LENGTH * scale_factor
    cam_len = CAM_ADAPTER_LEN * scale_factor
    cam_groove_dist = CAM_GROOVE_DIST * scale_factor
    cam_groove_w = CAM_GROOVE_WIDTH * scale_factor
    chamfer = 0.125 * scale_factor

    profile = []

    # 1. Flange bore at Z = 0
    profile.append((r_bore, 0.0))

    # 2. Flange sealing face
    if HAS_RAISED_FACE:
        profile.append((r_rf, 0.0))
        profile.append((r_rf, rf_h))
        profile.append((r_flange, rf_h))
        z_flange_back = rf_h + flange_thk
    else:
        profile.append((r_flange, 0.0))
        z_flange_back = flange_thk

    # 3. Flange OD to flange back face
    profile.append((r_flange, z_flange_back))

    # 4. Flange back face to hub/neck fillet
    profile.append((r_neck + 0.35 * scale_factor, z_flange_back))
    profile.append((r_neck, z_flange_back + 0.35 * scale_factor))

    # 5. Neck to Camlock stop shoulder
    z_cam_shoulder = oal - cam_len
    profile.append((r_neck, z_cam_shoulder - 0.25 * scale_factor))
    profile.append((r_cam, z_cam_shoulder))

    # 6. Camlock body leading to locking groove
    z_groove_center = oal - cam_groove_dist
    z_groove_start = z_groove_center - cam_groove_w / 2.0
    z_groove_end = z_groove_center + cam_groove_w / 2.0
    profile.append((r_cam, z_groove_start))

    # 7. Curved camlock groove contour
    groove_depth = r_cam - r_groove
    for i in range(1, GROOVE_SUBDIV):
        t = i / float(GROOVE_SUBDIV)
        zg = z_groove_center - (cam_groove_w / 2.0) * math.cos(math.pi * t)
        rg = r_cam - groove_depth * math.sin(math.pi * t)
        profile.append((rg, zg))

    profile.append((r_cam, z_groove_end))

    # 8. Camlock adapter body to nose chamfer
    profile.append((r_cam, oal - chamfer))
    profile.append((r_cam - chamfer, oal))

    # 9. Adapter front sealing face to internal bore
    profile.append((r_bore + chamfer, oal))
    profile.append((r_bore, oal - chamfer))

    # 10. Straight bore back down to flange face
    profile.append((r_bore, 0.0))

    return profile


def create_revolved_mesh(profile, steps, obj_name="8in_Flange_x_8in_Camlock"):
    """Revolves the 2D profile around the Z axis to create a closed quad mesh."""
    num_p = len(profile) - 1
    verts = []
    faces = []

    # Vertex ring generation
    for step in range(steps):
        angle = 2.0 * math.pi * step / steps
        cos_a = math.cos(angle)
        sin_a = math.sin(angle)
        for r, z in profile[:-1]:
            verts.append((r * cos_a, r * sin_a, z))

    # Quad face stitching
    for step in range(steps):
        next_step = (step + 1) % steps
        for i in range(num_p):
            next_i = (i + 1) % num_p
            v0 = step * num_p + i
            v1 = next_step * num_p + i
            v2 = next_step * num_p + next_i
            v3 = step * num_p + next_i
            faces.append((v0, v1, v2, v3))

    mesh = bpy.data.meshes.new(obj_name)
    mesh.from_pydata(verts, [], faces)
    mesh.update()

    # Ensure outward face normals
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(mesh)
    bm.free()

    obj = bpy.data.objects.new(obj_name, mesh)
    bpy.context.collection.objects.link(obj)
    return obj


def add_pbr_material(obj, name="Machined_Aluminum"):
    """Applies a metallic PBR material."""
    mat = bpy.data.materials.get(name)
    if mat is None:
        mat = bpy.data.materials.new(name=name)
        mat.use_nodes = True
        nodes = mat.node_tree.nodes
        bsdf = nodes.get("Principled BSDF")
        if bsdf:
            bsdf.inputs["Base Color"].default_value = (0.82, 0.83, 0.85, 1.0)
            bsdf.inputs["Metallic"].default_value = 0.92
            bsdf.inputs["Roughness"].default_value = 0.28
    if obj.data.materials:
        obj.data.materials[0] = mat
    else:
        obj.data.materials.append(mat)


def main():
    scale_factor = 0.0254 if SCALE_TO_METERS else 1.0

    # 1. Build revolved adapter body
    profile = build_adapter_profile(scale_factor)
    adapter_obj = create_revolved_mesh(profile, RADIAL_SEGMENTS)

    # 2. Build 8 bolt-hole cutter cylinders on bolt circle
    bc_r = (BOLT_CIRCLE_DIA / 2.0) * scale_factor
    hole_r = (BOLT_HOLE_DIA / 2.0) * scale_factor
    flange_thk = (FLANGE_THICKNESS + (RAISED_FACE_HEIGHT if HAS_RAISED_FACE else 0.0)) * scale_factor
    z_min = -0.15 * scale_factor
    z_max = flange_thk + 0.25 * scale_factor
    cutter_depth = z_max - z_min
    cutter_center_z = (z_min + z_max) / 2.0

    cutters = []
    for hole_idx in range(NUM_BOLT_HOLES):
        angle = (2.0 * math.pi * hole_idx) / NUM_BOLT_HOLES
        cx = bc_r * math.cos(angle)
        cy = bc_r * math.sin(angle)

        bpy.ops.mesh.primitive_cylinder_add(
            vertices=BOLT_HOLE_SEGMENTS,
            radius=hole_r,
            depth=cutter_depth,
            location=(cx, cy, cutter_center_z)
        )
        cutters.append(bpy.context.active_object)

    # Combine cutters into a single object
    bpy.ops.object.select_all(action='DESELECT')
    for c in cutters:
        c.select_set(True)
    bpy.context.view_layer.objects.active = cutters[0]
    bpy.ops.object.join()
    compound_cutter = bpy.context.active_object
    compound_cutter.name = "Bolt_Hole_Cutters"

    # 3. Apply Boolean Difference to punch bolt holes through flange
    bool_mod = adapter_obj.modifiers.new(name="Flange_Bolt_Holes", type='BOOLEAN')
    bool_mod.operation = 'DIFFERENCE'
    bool_mod.object = compound_cutter
    bool_mod.solver = 'EXACT'

    if APPLY_BOOLEAN:
        bpy.ops.object.select_all(action='DESELECT')
        adapter_obj.select_set(True)
        bpy.context.view_layer.objects.active = adapter_obj
        try:
            bpy.ops.object.modifier_apply(modifier=bool_mod.name)
            bpy.data.objects.remove(compound_cutter, do_unlink=True)
        except Exception:
            compound_cutter.hide_viewport = True
            compound_cutter.hide_render = True
    else:
        compound_cutter.hide_viewport = True
        compound_cutter.hide_render = True

    # 4. Configure smooth shading and auto-smooth
    bpy.ops.object.select_all(action='DESELECT')
    adapter_obj.select_set(True)
    bpy.context.view_layer.objects.active = adapter_obj
    bpy.ops.object.shade_smooth()

    if hasattr(adapter_obj.data, "use_auto_smooth"):
        adapter_obj.data.use_auto_smooth = True
        adapter_obj.data.auto_smooth_angle = math.radians(35)
    else:
        try:
            bpy.ops.object.modifier_add(type='SMOOTH_BY_ANGLE')
        except Exception:
            pass

    # 5. Assign material
    add_pbr_material(adapter_obj)
    print("Created 8in ANSI 150# Flange x 8in Male Camlock Adapter.")


if __name__ == "__main__":
    main()
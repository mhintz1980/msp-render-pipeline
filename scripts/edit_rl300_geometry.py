"""Apply the owner-authorised RL300 geometry edits to the photoreal CAD source.

Run headless against the authoring master:

    blender -b <source.blend> --factory-startup -noaudio \
        -P scripts/edit_rl300_geometry.py -- --save-as <dest.blend>

Editing the `.blend` invalidates the pinned `source.sha256` in
`preparation-report.json`, so `verify_scene.py` will raise `SOURCE_CHANGED`
until the scene is re-prepared and a new dark reference is accepted. That
sequence is deliberate; see HANDOFF-2026-09-13.md section 6.

Why a script rather than hand edits: the same three changes have to be
reproducible against a re-exported CAD file, and a diff of intent is reviewable
in a way that a 34 MB binary is not.

The edits, in the order they are applied:

1. **Fittings.** The two `V28 inch to 6 inch coupling 8 bolt` meshes are stand-in
   CAD geometry. They are replaced by `8in_Flange_x_8in_Camlock`, the authored
   part Mark parks off to the side, seated by mating its flange face onto the
   plane the old flange face occupied rather than by matching bounding-box
   centres - the new part is shorter than the old 209.55 mm, so centre-matching
   would sink it into the housing.

   The parked part has been revised once already (it superseded a first attempt,
   `Flanged_Camlock_800AL`), so nothing here is keyed to its dimensions. The bolt
   circle is measured off the bolts in the assembly and the flange plate is found
   from the part's own profile, which means a further revision either fits and is
   verified, or fails loudly.

   Each old coupling's spin about its own barrel axis is measured and preserved
   (one is 0 deg, the other 40.773 deg), because the flange bolt holes have to
   stay registered with the separate `HWR-*` bolt and washer objects.

   The replacement's authored orientation carries its barrel along world Y via a
   90 deg object rotation about X. That rotation is baked into the mesh so the
   barrel lies along **local** Y, matching the old couplings' convention. This
   matters for more than tidiness: `ShaderNodeTangent` in radial mode takes an
   object-space axis, so the anisotropy axis is only meaningful once every object
   sharing the material agrees on which local axis is the axis of revolution.

2. **Washers.** The 32 flange washers (16 per fitting, `HWR-BLTSET-*` and
   `HWR-KIT-BLF-*`, all sharing `Mesh_205`) measure as a dimensionally exact
   3/4 in SAE flat washer: 37.313 mm OD, 20.62 mm ID. The photographs show the
   wide pattern, so they go to USS: 50.8 mm OD, **same** 20.62 mm bore. The mesh
   is a plain annulus with exactly two vertex radii, so the outer ring is moved
   and the bore is left alone - a uniform scale would have opened the bore to
   28 mm and produced a washer that fits no bolt in the assembly.

3. **Anisotropy scope.** The turned fittings get their own material,
   `MSP_ALUMINUM_CAST_TURNED`, cloned from `MSP_ALUMINUM_CAST`. The four objects
   on `MSP_ALUMINUM_CAST` do not share an axis of revolution - the 8 in couplings
   are local Y but `V251415K55_Aluminum Cam and Groove Hose Coupling-1` is local
   X - so a single radial tangent axis on the shared material would streak that
   coupling across its barrel instead of around it. Scoping the material is what
   makes `anisotropy_axis: "Y"` a true statement rather than a guess.

4. **Pump.** `Volumenkoerper1` is renamed to an ASCII name so a manifest
   `reassign` rule can match it, and parented into `PUMP_HOUSING` like the rest
   of the driveline. Optional paired `--pump-glb` and `--pump-reference` inputs
   replace its tessellation after checking local and world bounds within 0.5 mm,
   carrying placement from the approved reference. Its shading stays in the manifest.

5. **Scaffolding.** `Bolt_Hole_Cutters` is an empty mesh (0 vertices) left over
   from generating the replacement fitting, and an embedded `Text` datablock holds
   the generator script. Both are removed; preparation blocks on `texts:Text`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from pathlib import Path

import bpy
from mathutils import Matrix, Vector

# The stand-in fittings being replaced, and the authored part replacing them.
OLD_FITTINGS = (
    "V28 inch to 6 inch coupling 8 bolt-1",
    "V28 inch to 6 inch coupling 8 bolt-1.001",
)
REPLACEMENT = "8in_Flange_x_8in_Camlock"
NEW_FITTING_NAMES = (
    "V2FTG-CAMLOCK-800AL-1",
    "V2FTG-CAMLOCK-800AL-2",
)

WASHER_MESH = "Mesh_205"
WASHER_TARGET_OD_MM = 50.80  # 3/4 in USS wide pattern, 2.000 in
WASHER_EXPECTED_USERS = 32

TURNED_MATERIAL = "MSP_ALUMINUM_CAST_TURNED"
CAST_MATERIAL = "MSP_ALUMINUM_CAST"

PUMP_PREFIX = "Volumenk"
PUMP_NEW_NAME = "PUMP_END_CASTSTEEL-1"
PUMP_PARENT = "PUMP_HOUSING"

SCAFFOLDING = ("Bolt_Hole_Cutters",)
# Where the embedded generator script is kept now that it is out of the blend.
GENERATOR_COPY = "cad/generators/flanged_camlock_800al.py"

# One micron: enough to fuse the glTF's coincident patch seams, far below any
# real feature size in the assembly, so no distinct surfaces can merge.
WELD_DISTANCE_M = 1e-6
# Normals must agree this closely before two faces are merged. 1 degree is below
# the tessellation's own facet step on every curved surface measured here.
DEFAULT_DISSOLVE_DEG = 1.0
# Blender's "Smooth by Angle" default. Reproduced as static mesh data, because
# the modifier itself is geometry nodes and the still-scene policy rejects those.
SMOOTH_ANGLE_DEG = 30.0

# ASME B16.5 Class 150, 8 in nominal: eight holes on an 11.750 in bolt circle.
# `BOLT_CIRCLE_RADIUS_M` is a **cross-check only** - the radius actually probed is
# measured off the assembly's own bolts, so a revised fitting with a different
# drilling is caught rather than silently mis-measured.
BOLT_COUNT = 8
BOLT_PITCH_DEG = 360.0 / BOLT_COUNT
BOLT_CIRCLE_RADIUS_M = 5.875 * 0.0254
# The bolts this flange has to accept, per fitting.
BOLT_PREFIXES = ("HWR-KIT-BLF", "HWR-BLTSET")
# --- axial seating -----------------------------------------------------------
# Past this radius from the barrel axis you are on the flange plate rim, not the
# neck or the cam lugs, so the plate's two faces can be measured directly.
FLANGE_RIM_R_M = 0.160
# A bolt/washer further than this off the fitting axis belongs to the other one.
RING_RADIUS_LIMIT_M = 0.25
SEAT_TOLERANCE_MM = 0.25
MATING_FLANGE_PREFIX = "V2FLG-WO-A200-"
# --- bolts -------------------------------------------------------------------
BOLT_MESH = "Mesh_203_LP"
BOLT_EXPECTED_USERS = 16
BOLT_NOMINAL_SHANK_D_M = 0.75 * 0.0254
BOLT_SHANK_TOL_M = 0.0005
BOLT_MIN_SHANK_M = 0.020
DEFAULT_BOLT_LENGTH_IN = 3.25
# Where the replacement part is parked before it is seated.
FITTING_PARK_M = (0.0, 2.0, 0.0)

# The assembly lives in this collection; the three hand-added objects landed in
# the scene root instead.
ASSEMBLY_COLLECTION = "Collection"

AXIS_Y = 1


def barrel_frame(obj) -> dict:
    """Measure an object's world-space barrel: axis extent, centre and spin.

    The barrel axis is world Y for every fitting in this assembly, which is
    checked rather than assumed - a solid of revolution has a single-valued
    radius at each axial station, so the axis that minimises radial spread per
    axial slice is the axis of revolution.
    """
    matrix = obj.matrix_world
    world = [matrix @ vertex.co for vertex in obj.data.vertices]
    ys = [v.y for v in world]
    xs = [v.x for v in world]
    zs = [v.z for v in world]
    centre_x = (max(xs) + min(xs)) / 2.0
    centre_z = (max(zs) + min(zs)) / 2.0

    # Spin about world Y, read off where the object's local X axis points in the
    # world XZ plane. This is the flange's bolt-hole phase. Ry(t) sends X to
    # (cos t, 0, -sin t), so the z component is negated going in - getting this
    # backwards mirrors the phase and pulls the bolt holes 2t off the bolts.
    local_x = matrix.col[0].to_3d()
    spin = math.atan2(-local_x.z, local_x.x)

    radii = [math.hypot(v.x - centre_x, v.z - centre_z) for v in world]
    flange_y = max(ys)
    return {
        "flange_y": flange_y,
        "tail_y": min(ys),
        "length": max(ys) - min(ys),
        "centre_x": centre_x,
        "centre_z": centre_z,
        "spin_rad": spin,
        "spin_deg": math.degrees(spin),
        "max_radius": max(radii),
        # Carried so placement can reuse the measured orientation verbatim
        # instead of decomposing it and rebuilding it from an angle.
        "rotation": matrix.to_3x3().normalized(),
    }


def revolution_scores(mesh) -> dict:
    """Radial spread per axial slice for each local axis; lowest wins."""
    coords = [v.co for v in mesh.vertices]
    scores = {}
    for index, name in enumerate("XYZ"):
        axial = [c[index] for c in coords]
        lo, hi = min(axial), max(axial)
        if hi - lo < 1e-9:
            scores[name] = None
            continue
        first, second = [i for i in range(3) if i != index]
        c1 = (max(c[first] for c in coords) + min(c[first] for c in coords)) / 2.0
        c2 = (max(c[second] for c in coords) + min(c[second] for c in coords)) / 2.0
        slices: dict[int, list[float]] = {}
        for coord in coords:
            bucket = min(23, int((coord[index] - lo) / (hi - lo) * 24))
            slices.setdefault(bucket, []).append(
                math.hypot(coord[first] - c1, coord[second] - c2)
            )
        spreads = [
            (max(rs) - min(rs)) / max(rs)
            for rs in slices.values()
            if len(rs) >= 4 and max(rs) > 1e-9
        ]
        scores[name] = round(sum(spreads) / len(spreads), 4) if spreads else None
    return scores


def bake_barrel_to_local_y(obj) -> dict:
    """Rewrite the replacement's mesh so its barrel is local +Y, flange at y=0.

    The part is authored with a 90 deg object rotation about X carrying the
    barrel into world Y. Baking that rotation in means the object can be placed
    with a pure `Ry(spin)` rotation, and - the reason it is worth doing - the
    radial tangent's object-space axis becomes Y for every object that shares
    the turned material.
    """
    matrix = obj.matrix_world.copy()
    mesh = obj.data
    world = [matrix @ vertex.co for vertex in mesh.vertices]
    centre_x = (max(v.x for v in world) + min(v.x for v in world)) / 2.0
    centre_z = (max(v.z for v in world) + min(v.z for v in world)) / 2.0
    flange_y = max(v.y for v in world)

    # Local origin sits on the barrel axis, in the plane of the flange face.
    origin = Vector((centre_x, flange_y, centre_z))
    for vertex, position in zip(mesh.vertices, world):
        vertex.co = position - origin
    mesh.update()

    obj.matrix_world = Matrix.Identity(4)
    scores = revolution_scores(mesh)
    return {
        "baked_origin": [round(c, 6) for c in origin],
        "local_flange_y_mm": round(max(v.co.y for v in mesh.vertices) * 1000, 4),
        "local_tail_y_mm": round(min(v.co.y for v in mesh.vertices) * 1000, 4),
        "revolution_scores": scores,
        "best_local_axis": min(
            (k for k, v in scores.items() if v is not None), key=lambda k: scores[k]
        ),
    }


def ensure_turned_material() -> str:
    """Clone the cast material so anisotropy can be scoped to turned parts."""
    existing = bpy.data.materials.get(TURNED_MATERIAL)
    if existing is not None:
        return "reused"
    source = bpy.data.materials.get(CAST_MATERIAL)
    if source is None:
        raise SystemExit(f"material not found: {CAST_MATERIAL}")
    clone = source.copy()
    clone.name = TURNED_MATERIAL
    return "created"


def bolt_ring(prefix: str, centre_x: float, centre_z: float) -> dict:
    """Where the existing flange bolts actually sit, measured off the washers.

    The bolts and washers are separate objects that the CAD placed against the
    old coupling; they are the fixed reference the replacement has to meet.
    """
    angles, radii = [], []
    for obj in bpy.data.objects:
        if not obj.name.startswith(prefix) or "/HWR-WSH-F8Z-075-" not in obj.name:
            continue
        world = [obj.matrix_world @ v.co for v in obj.data.vertices]
        wx = (max(v.x for v in world) + min(v.x for v in world)) / 2.0
        wz = (max(v.z for v in world) + min(v.z for v in world)) / 2.0
        radii.append(math.hypot(wx - centre_x, wz - centre_z))
        angles.append(math.degrees(math.atan2(wz - centre_z, wx - centre_x)) % 360.0)
    if not angles:
        raise SystemExit(f"no flange washers matched prefix {prefix}")
    # 16 washers sit in 8 pairs, one each side of the flange.
    phase = min(a % BOLT_PITCH_DEG for a in angles)
    return {
        "prefix": prefix,
        "washers": len(angles),
        "bolt_circle_radius_mm": round(sum(radii) / len(radii) * 1000, 3),
        "phase_deg": phase,
    }


def hole_ring(obj, probe_radius: float) -> dict:
    """Find the flange's bolt holes by probing the solid at the bolt circle.

    The hole cutters are applied as a boolean into one watertight body, so a point
    at the bolt circle and mid-flange depth is either in metal or in a hole -
    ray-crossing parity says which, and the gaps are the holes.

    `probe_radius` comes from the bolts actually in the assembly, not from a
    drawing. The part being fitted has changed once already, and a probe radius
    taken from the previous part's generator would have quietly measured the wrong
    circle on the new one and reported a hole count instead of a mismatch.

    The flange depth is derived from this part's own geometry too: the flange is
    the band of maximum radius at the +Y end, so the probe sits at the middle of
    that band whatever the plate thickness turns out to be.
    """
    import bmesh
    from mathutils.bvhtree import BVHTree

    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.transform(bm, matrix=obj.matrix_world, verts=bm.verts)
    bvh = BVHTree.FromBMesh(bm)
    coords = [v.co for v in bm.verts]
    centre_x = (max(c.x for c in coords) + min(c.x for c in coords)) / 2.0
    centre_z = (max(c.z for c in coords) + min(c.z for c in coords)) / 2.0
    # Locate the flange: walk in from the +Y face while the section still reaches
    # nearly the part's maximum radius. That band is the flange plate.
    face_y = max(c.y for c in coords)
    max_r = max(
        math.hypot(c.x - centre_x, c.z - centre_z) for c in coords
    )
    flange_span = 0.0
    for depth_mm in range(1, 121):
        depth = depth_mm / 1000.0
        band = [
            c for c in coords
            if face_y - depth - 0.0015 <= c.y <= face_y - depth + 0.0015
        ]
        if not band:
            continue
        if max(math.hypot(c.x - centre_x, c.z - centre_z) for c in band) < max_r * 0.97:
            break
        flange_span = depth
    if flange_span < 0.004:
        raise SystemExit(
            f"{obj.name}: could not find a flange plate at the +Y end "
            f"(span {flange_span * 1000:.1f} mm)"
        )
    probe_y = face_y - flange_span / 2.0

    up = Vector((0.0, 1.0, 0.0))
    def in_metal(point):
        crossings, cursor = 0, point + up * 1e-7
        for _ in range(200):
            hit = bvh.ray_cast(cursor, up, 5.0)
            if hit[2] is None:
                break
            crossings += 1
            cursor = hit[0] + up * 1e-7
        return crossings % 2 == 1

    step = 0.25
    samples = int(360 / step)
    metal = []
    for i in range(samples):
        angle = math.radians(i * step)
        metal.append(in_metal(Vector((
            centre_x + probe_radius * math.cos(angle),
            probe_y,
            centre_z + probe_radius * math.sin(angle),
        ))))
    bm.free()

    voids, start = [], None
    for i in range(samples):
        if not metal[i] and start is None:
            start = i
        elif metal[i] and start is not None:
            voids.append((start, i - 1))
            start = None
    if start is not None:
        if voids and voids[0][0] == 0:
            voids[0] = (start - samples, voids[0][1])
        else:
            voids.append((start, samples - 1))
    centres = sorted(((a + b) / 2.0 * step) % 360.0 for a, b in voids)
    if len(centres) != BOLT_COUNT:
        raise SystemExit(
            f"expected {BOLT_COUNT} bolt holes in {obj.name}, probed {len(centres)}"
        )
    return {
        "holes": len(centres),
        "centres_deg": [round(c, 3) for c in centres],
        "phase_deg": min(c % BOLT_PITCH_DEG for c in centres),
        "probe_radius_mm": round(probe_radius * 1000, 3),
        "flange_plate_mm": round(flange_span * 1000, 2),
        "max_radius_mm": round(max_r * 1000, 2),
    }


def phase_error(hole_phase: float, bolt_phase: float) -> float:
    """Signed hole-to-bolt error, folded into a single bolt pitch."""
    half = BOLT_PITCH_DEG / 2.0
    return ((hole_phase - bolt_phase + half) % BOLT_PITCH_DEG) - half


def static_smooth_shading(mesh, angle_deg: float) -> dict:
    """Bake "Smooth by Angle" down into sharp-edge flags on the mesh itself.

    Mark shade-auto-smoothed the corrected fitting in the GUI. Since Blender 4.1
    that is not a mesh property any more - it is a **geometry nodes modifier**
    that links `geometry_nodes_essentials.blend` out of the Blender installation.
    Preparation rejects all three of those (linked library, NODES modifier,
    geometry-nodes datablock) and is right to: a still-scene proof cannot depend
    on a node graph evaluated from a file outside the payload.

    The shading intent is worth keeping, though, so it is reproduced statically:
    every face smooth, and every edge whose two faces disagree by more than
    `angle_deg` marked sharp. That is what auto-smooth computes, written into the
    mesh where it needs no modifier and no external file.
    """
    import bmesh

    bm = bmesh.new()
    bm.from_mesh(mesh)
    bm.normal_update()
    threshold = math.radians(angle_deg)
    sharp = 0
    for edge in bm.edges:
        faces = edge.link_faces
        if len(faces) == 2:
            if faces[0].normal.angle(faces[1].normal) > threshold:
                edge.smooth = False
                sharp += 1
            else:
                edge.smooth = True
        else:
            edge.smooth = False
    for face in bm.faces:
        face.smooth = True
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()
    return {"angle_deg": angle_deg, "sharp_edges": sharp, "edges": len(mesh.edges)}


def strip_geometry_nodes(report: dict) -> None:
    """Remove NODES modifiers, their node groups, and the libraries they pull in.

    Explicit and reviewable, for the same reason the embedded `Text` is removed
    here rather than by the preparer: dropping a dependency silently is how a
    prepared scene stops matching the scene someone authored. `static_smooth_shading`
    has already preserved what the modifier was doing.
    """
    removed_mods = []
    for obj in bpy.data.objects:
        for modifier in list(obj.modifiers):
            if modifier.type == "NODES":
                removed_mods.append(f"{obj.name}/{modifier.name}")
                obj.modifiers.remove(modifier)

    removed_groups = []
    for group in list(bpy.data.node_groups):
        removed_groups.append(group.name)
        bpy.data.node_groups.remove(group)

    # The linked libraries are only referenced through those groups, so with the
    # groups gone nothing needs them. `orphans_purge` does not clear the library
    # entries themselves in background mode, so remove them outright - that is
    # what leaves `bpy.utils.blend_paths` empty, which is the thing preparation
    # actually checks.
    # Read every path up front. Both entries here point at the same file, and
    # removing one invalidates the other's StructRNA, so touching `.filepath`
    # mid-loop raises. Drain the collection by index instead of iterating it.
    removed_libs = [lib.filepath for lib in bpy.data.libraries]
    guard = 0
    while bpy.data.libraries and guard < 64:
        guard += 1
        bpy.data.libraries.remove(bpy.data.libraries[0])
    remaining = [lib.filepath for lib in bpy.data.libraries]

    report["stripped_geometry_nodes"] = {
        "modifiers": removed_mods,
        "node_groups": removed_groups,
        "libraries_removed": removed_libs,
        "libraries_remaining": remaining,
        "external_paths_remaining": list(bpy.utils.blend_paths(packed=False)),
    }
    if remaining:
        raise SystemExit(
            f"linked libraries still present after purge: {remaining}"
        )
    if any(m.type == "NODES" for o in bpy.data.objects for m in o.modifiers):
        raise SystemExit("a NODES modifier survived the strip")


def replace_fittings(report: dict) -> None:
    scene = bpy.context.scene
    replacement = bpy.data.objects.get(REPLACEMENT)
    if replacement is None:
        raise SystemExit(f"replacement part not found: {REPLACEMENT}")

    olds = []
    for name in OLD_FITTINGS:
        obj = bpy.data.objects.get(name)
        if obj is None:
            raise SystemExit(f"fitting to replace not found: {name}")
        olds.append(obj)

    report["old_fittings"] = [
        dict(name=o.name, **{k: (round(v, 5) if isinstance(v, float) else v)
                             for k, v in barrel_frame(o).items()
                             if k != "rotation"})
        for o in olds
    ]
    frames = [barrel_frame(o) for o in olds]

    # Every fitting here is a barrel on world Y, differing only in its spin about
    # that barrel. If one of them is tilted, seating the replacement by
    # translation plus spin is not a valid operation and the numbers below would
    # look perfect while the part sat crooked.
    for obj, frame in zip(olds, frames):
        axis = frame["rotation"].col[AXIS_Y]
        if (axis - Vector((0.0, 1.0, 0.0))).length > 1e-6:
            raise SystemExit(
                f"{obj.name} barrel axis is not world Y (local Y maps to "
                f"{tuple(round(c, 6) for c in axis)}); refusing to seat by spin"
            )
    parent = olds[0].parent
    collections = [c.name for c in olds[0].users_collection]
    report["inherited_parent"] = parent.name if parent else None
    report["inherited_collections"] = collections

    report["bake"] = bake_barrel_to_local_y(replacement)
    mesh = replacement.data
    mesh.name = "Flanged_Camlock_8in_Body"

    # The authored part carries an empty first slot with every face assigned to
    # it, so the mesh renders with no material at all until this is fixed. A
    # manifest `reassign` rule could not repair it either: that code skips slots
    # whose material is None.
    turned = bpy.data.materials[TURNED_MATERIAL]
    mesh.materials.clear()
    mesh.materials.append(turned)
    for polygon in mesh.polygons:
        polygon.material_index = 0
        polygon.use_smooth = True
    mesh.update()
    report["fitting_material"] = turned.name
    report["fitting_smooth"] = static_smooth_shading(mesh, SMOOTH_ANGLE_DEG)

    target_collection = bpy.data.collections.get(ASSEMBLY_COLLECTION)
    if target_collection is None:
        raise SystemExit(f"collection not found: {ASSEMBLY_COLLECTION}")

    placed, corrections = [], []
    for index, (frame, new_name) in enumerate(zip(frames, NEW_FITTING_NAMES)):
        if index == 0:
            obj = replacement
            obj.name = new_name
        else:
            obj = bpy.data.objects.new(new_name, mesh)

        # Link and parent BEFORE measuring anything. A freshly created object
        # that is not yet in the view layer has no evaluated `matrix_world`, so
        # probing its geometry would read the mesh at identity - which looks like
        # a perfectly plausible answer and is silently wrong.
        for collection in list(obj.users_collection):
            collection.objects.unlink(obj)
        target_collection.objects.link(obj)
        if parent is not None:
            obj.parent = parent
            # With the parent's inverse held here, matrix_basis is the world
            # transform, so the seat below can be expressed in world terms.
            obj.matrix_parent_inverse = parent.matrix_world.inverted()

        # Baking put local y=0 on the flange face and the barrel on local Y, so
        # the seat is the old part's own orientation plus a translation onto the
        # flange plane and the barrel centre. Reusing the measured matrix keeps
        # the old part's orientation exact; rebuilding it from an extracted angle
        # is where a sign convention can mirror the flange without moving it.
        seat = Matrix.Translation(
            Vector((frame["centre_x"], frame["flange_y"], frame["centre_z"]))
        )
        obj.matrix_basis = seat @ frame["rotation"].to_4x4()
        bpy.context.view_layer.update()

        # Inheriting the old coupling's orientation seats the part but says
        # nothing about where the new flange's holes are. The generator starts
        # its eight holes at local 0 deg while this assembly's bolts sit at half
        # a pitch, so as-inherited every bolt would pass through solid metal and
        # the holes would sit in the gaps between them. Measure the error and
        # take it out, rather than carrying 22.5 as a magic number that a
        # re-generated part would silently invalidate.
        bolts = bolt_ring(BOLT_PREFIXES[index], frame["centre_x"], frame["centre_z"])
        holes = hole_ring(obj, bolts["bolt_circle_radius_mm"] / 1000.0)
        delta = phase_error(holes["phase_deg"], bolts["phase_deg"])
        # Ry(d) lowers the atan2 angle by d, so the correction is applied as-is.
        obj.matrix_basis = (
            seat
            @ Matrix.Rotation(math.radians(delta), 4, "Y")
            @ frame["rotation"].to_4x4()
        )
        bpy.context.view_layer.update()

        corrected = hole_ring(obj, bolts["bolt_circle_radius_mm"] / 1000.0)
        residual = phase_error(corrected["phase_deg"], bolts["phase_deg"])
        report.setdefault("bolt_registration", []).append({
            "fitting": new_name,
            "bolt_prefix": bolts["prefix"],
            "washers_measured": bolts["washers"],
            "bolt_circle_radius_mm": bolts["bolt_circle_radius_mm"],
            "generator_bolt_circle_radius_mm": round(BOLT_CIRCLE_RADIUS_M * 1000, 3),
            "bolt_phase_deg": round(bolts["phase_deg"], 3),
            "hole_phase_inherited_deg": round(holes["phase_deg"], 3),
            "phase_correction_deg": round(delta, 3),
            "hole_phase_corrected_deg": round(corrected["phase_deg"], 3),
            "residual_deg": round(residual, 4),
            "hole_centres_deg": corrected["centres_deg"],
            "probe_radius_mm": corrected["probe_radius_mm"],
            "flange_plate_mm": corrected["flange_plate_mm"],
            "fitting_max_radius_mm": corrected["max_radius_mm"],
        })
        # A 0.875 in hole on a 0.750 in bolt leaves about 1.2 deg of angular
        # slack at this bolt circle, so anything past a third of that means a
        # bolt fouls the flange.
        if abs(residual) > 0.3:
            raise SystemExit(
                f"{new_name}: bolt holes still {residual:.3f} deg off the bolts"
            )
        if abs(bolts["bolt_circle_radius_mm"] - BOLT_CIRCLE_RADIUS_M * 1000) > 0.5:
            raise SystemExit(
                f"{new_name}: assembly bolt circle is "
                f"{bolts['bolt_circle_radius_mm']} mm but the flange is drilled "
                f"for {BOLT_CIRCLE_RADIUS_M * 1000:.3f} mm"
            )

        corrections.append(delta)
        placed.append(obj)

    bpy.context.view_layer.update()
    for obj, frame, delta in zip(placed, frames, corrections):
        after = barrel_frame(obj)
        # The part is deliberately spun off the old coupling's orientation by the
        # measured bolt-phase correction, so that - not the inherited angle - is
        # what the placed spin has to equal.
        expected_spin = frame["spin_rad"] + math.radians(delta)
        spin_error = math.degrees(
            math.atan2(
                math.sin(after["spin_rad"] - expected_spin),
                math.cos(after["spin_rad"] - expected_spin),
            )
        )
        placed_report = {
            "name": obj.name,
            "spin_deg": round(after["spin_deg"], 4),
            "inherited_spin_deg": round(frame["spin_deg"], 4),
            "bolt_phase_correction_deg": round(delta, 4),
            "target_spin_deg": round(math.degrees(expected_spin), 4),
            "spin_error_deg": round(spin_error, 6),
            "flange_y_mm": round(after["flange_y"] * 1000, 3),
            "target_flange_y_mm": round(frame["flange_y"] * 1000, 3),
            "flange_error_mm": round((after["flange_y"] - frame["flange_y"]) * 1000, 6),
            "centre_error_mm": [
                round((after["centre_x"] - frame["centre_x"]) * 1000, 6),
                round((after["centre_z"] - frame["centre_z"]) * 1000, 6),
            ],
            "length_mm": round(after["length"] * 1000, 2),
            "max_radius_mm": round(after["max_radius"] * 1000, 2),
            "parent": obj.parent.name if obj.parent else None,
        }
        report.setdefault("new_fittings", []).append(placed_report)
        worst = max(
            abs(placed_report["flange_error_mm"]),
            *[abs(v) for v in placed_report["centre_error_mm"]],
        )
        if worst > 1e-3:
            raise SystemExit(f"fitting seat off by {worst} mm: {placed_report}")
        # A mirrored or drifted spin is a defect even though it leaves the part
        # in exactly the right place; `bolt_registration` is the check that says
        # the holes and the bolts agree.
        if abs(spin_error) > 1e-4:
            raise SystemExit(
                f"fitting bolt-hole phase off by {spin_error:.4f} deg: "
                f"{placed_report}"
            )

    for obj in olds:
        bpy.data.objects.remove(obj, do_unlink=True)
    report["removed_fittings"] = list(OLD_FITTINGS)
    _ = scene


def widen_washers(report: dict) -> None:
    """Move the outer ring of the shared washer annulus out to the USS OD."""
    mesh = bpy.data.meshes.get(WASHER_MESH)
    if mesh is None:
        raise SystemExit(f"washer mesh not found: {WASHER_MESH}")
    if mesh.users != WASHER_EXPECTED_USERS:
        raise SystemExit(
            f"{WASHER_MESH} has {mesh.users} users, expected "
            f"{WASHER_EXPECTED_USERS}; refusing to reshape shared geometry"
        )

    coords = [v.co for v in mesh.vertices]
    extents = {
        "X": max(c.x for c in coords) - min(c.x for c in coords),
        "Y": max(c.y for c in coords) - min(c.y for c in coords),
        "Z": max(c.z for c in coords) - min(c.z for c in coords),
    }
    thin = min(extents, key=extents.get)
    if thin != "X":
        raise SystemExit(f"expected washer thickness on local X, measured {thin}")
    centre_y = (max(c.y for c in coords) + min(c.y for c in coords)) / 2.0
    centre_z = (max(c.z for c in coords) + min(c.z for c in coords)) / 2.0

    radii = [math.hypot(c.y - centre_y, c.z - centre_z) for c in coords]
    outer = max(radii)
    inner = min(radii)
    # A flat washer is an annulus: two vertex radii and nothing between them. If
    # that is not what this mesh is, the outer-ring move is the wrong operation.
    midpoint = (inner + outer) / 2.0
    between = [r for r in radii if inner * 1.02 < r < outer * 0.98]
    if between:
        raise SystemExit(
            f"{WASHER_MESH} is not a plain annulus: {len(between)} vertices sit "
            "between the bore and the rim"
        )

    target_outer = WASHER_TARGET_OD_MM / 2000.0  # mm diameter -> m radius
    scale = target_outer / outer
    moved = 0
    for vertex in mesh.vertices:
        radius = math.hypot(vertex.co.y - centre_y, vertex.co.z - centre_z)
        if radius < midpoint:
            continue  # bore stays at the 20.62 mm bolt size
        vertex.co.y = centre_y + (vertex.co.y - centre_y) * scale
        vertex.co.z = centre_z + (vertex.co.z - centre_z) * scale
        moved += 1
    mesh.update()

    after = [
        math.hypot(v.co.y - centre_y, v.co.z - centre_z) for v in mesh.vertices
    ]
    report["washers"] = {
        "mesh": mesh.name,
        "instances": WASHER_EXPECTED_USERS,
        "vertices_moved": moved,
        "before_od_mm": round(outer * 2000, 3),
        "after_od_mm": round(max(after) * 2000, 3),
        "bore_id_mm": round(min(after) * 2000, 3),
        "thickness_mm": round(extents["X"] * 1000, 3),
        "outer_scale": round(scale, 6),
    }


def rehome_pump(report: dict) -> None:
    matches = [o for o in bpy.data.objects if o.name.startswith(PUMP_PREFIX)]
    if not matches:
        report["pump"] = {"status": "not found", "prefix": PUMP_PREFIX}
        return
    if len(matches) > 1:
        raise SystemExit(f"expected one pump object, found {len(matches)}")
    pump = matches[0]
    original = pump.name
    pump.name = PUMP_NEW_NAME
    pump.data.name = f"{PUMP_NEW_NAME}_Mesh"

    parent = bpy.data.objects.get(PUMP_PARENT)
    if parent is not None and pump.parent is None:
        pump.parent = parent
        pump.matrix_parent_inverse = parent.matrix_world.inverted()

    target = bpy.data.collections.get(ASSEMBLY_COLLECTION)
    if target is not None and target not in list(pump.users_collection):
        for collection in list(pump.users_collection):
            collection.objects.unlink(pump)
        target.objects.link(pump)

    report["pump"] = {
        "renamed_from": original,
        "name": pump.name,
        "parent": pump.parent.name if pump.parent else None,
        "polys": len(pump.data.polygons),
        "slots": len(pump.material_slots),
        "collections": [c.name for c in pump.users_collection],
    }


def swap_pump(report: dict, glb_path: str, reference_path: str) -> None:
    """Replace tessellation only, retaining the approved source's placement."""
    import hashlib
    from pathlib import Path

    old = bpy.data.objects.get(PUMP_NEW_NAME)
    parent = bpy.data.objects.get(PUMP_PARENT)
    collection = bpy.data.collections.get(ASSEMBLY_COLLECTION)
    if old is None or parent is None or collection is None:
        raise SystemExit("pump swap requires the existing pump, parent and collection")
    if old.data.users != 1:
        raise SystemExit("pump mesh is shared; refusing to replace it")

    def bounds(obj, world=False):
        coords = [obj.matrix_world @ v.co if world else v.co for v in obj.data.vertices]
        return [[min(v[i] for v in coords), max(v[i] for v in coords)] for i in range(3)]

    def delta_mm(a, b):
        return max(abs(a[i][j] - b[i][j]) * 1000 for i in range(3) for j in range(2))

    with bpy.data.libraries.load(reference_path, link=False) as (source, target):
        if PUMP_NEW_NAME not in source.objects:
            raise SystemExit("approved reference pump is missing")
        target.objects = [PUMP_NEW_NAME]
    reference = target.objects[0]
    collection.objects.link(reference)
    bpy.context.view_layer.update()
    matrix = reference.matrix_world.copy()
    local_before = bounds(reference)
    world_before = bounds(reference, True)
    reference_mesh = reference.data
    bpy.data.objects.remove(reference, do_unlink=True)
    if reference_mesh.users == 0:
        bpy.data.meshes.remove(reference_mesh)

    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=glb_path)
    imported = set(bpy.data.objects) - before
    if len(imported) != 1 or next(iter(imported)).type != "MESH":
        raise SystemExit("coarse export must import as exactly one mesh object")
    pump = next(iter(imported))
    local_after = bounds(pump)
    local_error = delta_mm(local_before, local_after)
    if local_error > 0.5:
        raise SystemExit(f"pump local bounds differ by {local_error:.6f} mm; transform not transferable")
    for current in list(pump.users_collection):
        current.objects.unlink(pump)
    collection.objects.link(pump)
    pump.parent = parent
    pump.matrix_parent_inverse = parent.matrix_world.inverted()
    pump.matrix_world = matrix
    bpy.context.view_layer.update()
    world_after = bounds(pump, True)
    world_error = delta_mm(world_before, world_after)
    if world_error > 0.5:
        raise SystemExit(f"pump world bounds differ by {world_error:.6f} mm")
    old_mesh = old.data
    bpy.data.objects.remove(old, do_unlink=True)
    bpy.data.meshes.remove(old_mesh)
    pump.name = PUMP_NEW_NAME
    pump.data.name = f"{PUMP_NEW_NAME}_Mesh"
    report["pump_swap"] = {
        "glb": glb_path,
        "glb_sha256": hashlib.sha256(Path(glb_path).read_bytes()).hexdigest(),
        "reference": reference_path,
        "reference_sha256": hashlib.sha256(Path(reference_path).read_bytes()).hexdigest(),
        "matrix_world": [list(row) for row in matrix],
        "local_bounds_before_m": local_before, "local_bounds_after_m": local_after,
        "world_bounds_before_m": world_before, "world_bounds_after_m": world_after,
        "local_max_error_mm": local_error, "world_max_error_mm": world_error,
        "imported_triangles": sum(len(p.vertices) - 2 for p in pump.data.polygons),
    }


def reduce_pump(report: dict, dissolve_deg: float) -> None:
    """Weld the pump's glTF seams, then merge its coplanar tessellation.

    Two facts about this asset drove the approach, both measured rather than
    assumed:

    * The glTF arrives as ~5,900 unwelded surface patches - 354,350 boundary
      edges, 549,630 vertices for 727,602 triangles. Welding at one micron takes
      it to 361,271 vertices and **zero** boundary edges: the whole pump is one
      closed manifold. Only coincident vertices merge at that distance, so the
      surface is unchanged.

    * Because it welds into a single shell, the pump has no separable parts. The
      vendor supplied one fused solid - "Volumenkoerper" is literally "solid
      body" - so the internals, bolt shanks and thread helices cannot be deleted
      as parts, because they are not parts. Shell-level surgery has nothing to
      grip.

    Visibility-based face culling was measured and rejected: the never-hit face
    count did not converge with sampling density (59.8% -> 32.7% -> 16.7% ->
    11.0% as the ray step went 30 mm -> 5.4 mm), so any threshold would have
    deleted geometry that is merely unsampled rather than hidden.

    That leaves limited dissolve, which merges faces whose normals agree to
    within `dissolve_deg` and is the one reduction with a bounded visual cost.
    The real saving is upstream: 727k triangles is far finer than this part needs
    at any framing where it sits inside the enclosure, and a coarser chord
    deflection on re-export would beat anything done here.
    """
    import bmesh

    pump = bpy.data.objects.get(PUMP_NEW_NAME)
    if pump is None:
        report["pump_reduction"] = {"status": "pump not found"}
        return

    mesh = pump.data
    bm = bmesh.new()
    bm.from_mesh(mesh)
    before = (len(bm.verts), len(bm.faces))
    boundary_before = sum(1 for e in bm.edges if len(e.link_faces) == 1)

    bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=WELD_DISTANCE_M)
    welded = (len(bm.verts), len(bm.faces))
    boundary_after = sum(1 for e in bm.edges if len(e.link_faces) == 1)
    nonmanifold = sum(1 for e in bm.edges if len(e.link_faces) > 2)

    if dissolve_deg > 0.0:
        bmesh.ops.dissolve_limit(
            bm,
            angle_limit=math.radians(dissolve_deg),
            verts=bm.verts[:],
            edges=bm.edges[:],
        )
    final = (len(bm.verts), len(bm.faces))
    render_tris = sum(max(0, len(f.verts) - 2) for f in bm.faces)
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()

    report["pump_reduction"] = {
        "weld_distance_m": WELD_DISTANCE_M,
        "dissolve_deg": dissolve_deg,
        "verts": {"before": before[0], "welded": welded[0], "final": final[0]},
        "stored_faces": {"before": before[1], "welded": welded[1], "final": final[1]},
        "render_triangles": render_tris,
        "boundary_edges": {"before": boundary_before, "after": boundary_after},
        "nonmanifold_edges": nonmanifold,
        "watertight_after_weld": boundary_after == 0 and nonmanifold == 0,
        "vert_reduction_pct": round(100 * (before[0] - final[0]) / before[0], 2),
        "render_tri_reduction_pct": round(
            100 * (before[1] - render_tris) / before[1], 2
        ),
    }
    if boundary_after != 0:
        # Worth knowing loudly: if a re-export ever arrives that does not weld
        # shut, the single-solid conclusion above no longer holds.
        print(
            f"[warning] pump still has {boundary_after} boundary edges after "
            "welding; it is no longer a single closed solid"
        )


def drop_embedded_texts(report: dict) -> None:
    """Remove `Text` datablocks, which the still-scene policy rejects outright.

    Authoring the replacement fitting left its generator script embedded in the
    file, and `prepare_scene.py` blocks on `texts:Text` rather than deleting it -
    correctly, since silently dropping a dependency is how a prepared scene stops
    matching the scene someone authored. Removing it here is the explicit,
    reviewable version of that decision, and the script itself is preserved at
    GENERATOR_COPY so the fitting's dimensions are not lost with it.
    """
    removed = []
    for text in list(bpy.data.texts):
        removed.append({"name": text.name, "lines": len(text.as_string().splitlines())})
        bpy.data.texts.remove(text)
    report["removed_texts"] = removed
    report["generator_preserved_at"] = GENERATOR_COPY


def drop_scaffolding(report: dict) -> None:
    removed = []
    for name in SCAFFOLDING:
        obj = bpy.data.objects.get(name)
        if obj is None:
            continue
        if obj.type == "MESH" and len(obj.data.vertices) > 0:
            raise SystemExit(
                f"{name} has {len(obj.data.vertices)} vertices; it is not the "
                "empty helper this expects and will not be removed"
            )
        removed.append(name)
        bpy.data.objects.remove(obj, do_unlink=True)
    report["removed_scaffolding"] = removed


def regenerate_fitting(report: dict, raised_face: bool) -> None:
    """Build the replacement part by running Mark's generator, not by trusting
    an object someone authored into the .blend by hand.

    The authored part carried a 1/16 in raised face, which is wrong for this
    joint: the gasket is full-face out to the flange OD, so the raised boss left
    the bolt circle clamping a 1.6 mm air gap. Running the generator here makes a
    dimension change a one-line edit plus a replay, and means nobody has to open
    Blender and risk saving over the authoring master.
    """
    source = Path(GENERATOR_COPY)
    if not source.exists():
        raise SystemExit(f"generator not found: {GENERATOR_COPY}")
    text = source.read_text(encoding="utf-8")
    if "HAS_RAISED_FACE = " not in text:
        raise SystemExit("generator no longer exposes HAS_RAISED_FACE")
    text = re.sub(
        r"HAS_RAISED_FACE = (?:True|False)",
        f"HAS_RAISED_FACE = {bool(raised_face)}",
        text, count=1)
    if "SCALE_TO_METERS = True" not in text:
        raise SystemExit("generator is not set to metres; refusing to run it")

    existing = bpy.data.objects.get(REPLACEMENT)
    if existing is not None:
        # Drop the mesh too. An orphaned mesh still counts as a user of its
        # material, and Blender's save-time purge is a single pass: the mesh goes
        # and the material stays, leaving one more material in the source than
        # the prepared scene keeps (SOURCE_STRUCTURE_MISMATCH).
        stale_mesh = existing.data if existing.type == "MESH" else None
        bpy.data.objects.remove(existing, do_unlink=True)
        if stale_mesh is not None and stale_mesh.users == 0:
            bpy.data.meshes.remove(stale_mesh)
    before = {o.name for o in bpy.data.objects}
    materials_before = {m.name for m in bpy.data.materials}

    namespace = {"__name__": "__main__"}
    exec(compile(text, GENERATOR_COPY, "exec"), namespace)

    built = bpy.data.objects.get(REPLACEMENT)
    if built is None:
        raise SystemExit(f"generator did not produce {REPLACEMENT}")
    for name in {o.name for o in bpy.data.objects} - before - {REPLACEMENT}:
        if name in SCAFFOLDING:
            bpy.data.objects.remove(bpy.data.objects[name], do_unlink=True)

    # The generator ends by assigning its own PBR material. replace_fittings
    # overwrites that with the turned aluminium anyway, and leaving the datablock
    # behind puts an extra material in the source that the prepared scene drops -
    # which the verifier reports as SOURCE_STRUCTURE_MISMATCH.
    assigned = [m.name for m in built.data.materials if m is not None]
    built.data.materials.clear()
    stray_materials = []
    candidates = sorted(
        set(assigned) | ({m.name for m in bpy.data.materials} - materials_before))
    for name in candidates:
        material = bpy.data.materials.get(name)
        if material is None:
            continue
        # The generator marks its material with a fake user, which would keep it
        # in the saved file even with nothing using it.
        material.use_fake_user = False
        if material.users == 0:
            bpy.data.materials.remove(material)
            stray_materials.append(name)

    # The generator builds along local +Z with the flange face at z=0.
    # Everything downstream - bake_barrel_to_local_y, hole_ring - expects the
    # part parked off to the side with its barrel on world Y and the flange at
    # the +Y end, which is how Mark's hand-authored copy arrived. Rx(+90) maps
    # local +Z to world -Y, so the flange face becomes the part's +Y extreme.
    built.location = FITTING_PARK_M
    built.rotation_euler = (math.pi / 2.0, 0.0, 0.0)
    bpy.context.view_layer.update()

    coords = [v.co for v in built.data.vertices]
    axial = [c.z for c in coords]
    rim = [c.z for c in coords if math.hypot(c.x, c.y) > FLANGE_RIM_R_M]
    report["fitting_regenerated"] = {
        "generator": GENERATOR_COPY,
        "generator_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "raised_face": bool(raised_face),
        "vertices": len(coords),
        "polygons": len(built.data.polygons),
        "length_mm": round((max(axial) - min(axial)) * 1000, 3),
        "flange_plate_mm": round((max(rim) - min(rim)) * 1000, 3),
        "discarded_materials": stray_materials,
    }


def _axis_index(mesh) -> int:
    """Local axis of revolution for a turned part."""
    scores = revolution_scores(mesh)
    ranked = [
        (scores[name], index)
        for index, name in enumerate("XYZ")
        if scores.get(name) is not None
    ]
    if not ranked:
        raise SystemExit("no axis of revolution could be scored")
    return min(ranked)[1]


def _stations(values, tol=1e-4):
    """Collapse coordinates into distinct axial stations."""
    out = []
    for value in sorted(values):
        if not out or value - out[-1][-1] > tol:
            out.append([value])
        else:
            out[-1].append(value)
    return [sum(group) / len(group) for group in out]


def lengthen_bolts(report: dict, target_in: float) -> None:
    """Stretch the flange bolts to `target_in` under-head length.

    The stretch is applied across the plain shank - the one long run of constant
    radius between the head and the first thread - so the thread pitch is carried
    rather than scaled. Refuses if that run cannot be found, because a stretch
    applied across a thread would silently deform every crest.
    """
    mesh = bpy.data.meshes.get(BOLT_MESH)
    if mesh is None:
        raise SystemExit(f"bolt mesh not found: {BOLT_MESH}")
    users = [o for o in bpy.data.objects if o.type == "MESH" and o.data is mesh]
    if len(users) != BOLT_EXPECTED_USERS:
        raise SystemExit(
            f"{BOLT_MESH} has {len(users)} users, expected {BOLT_EXPECTED_USERS}; "
            "refusing to edit geometry shared with anything else")

    axis = _axis_index(mesh)
    radial = [i for i in range(3) if i != axis]
    coords = [v.co.copy() for v in mesh.vertices]

    def radius(co):
        return math.hypot(co[radial[0]], co[radial[1]])

    nominal = BOLT_NOMINAL_SHANK_D_M / 2.0
    # Only stations that actually carry the nominal shank diameter can bound the
    # plain run. The hex corners sit on their own stations at nearly twice that
    # radius, and picking one of those as a boundary would stretch the head.
    on_shank = _stations([
        c[axis] for c in coords if abs(radius(c) - nominal) <= BOLT_SHANK_TOL_M
    ])
    if len(on_shank) < 2:
        raise SystemExit(
            f"{BOLT_MESH} carries no run at {BOLT_NOMINAL_SHANK_D_M * 1000:.2f} mm "
            "diameter; this is not the bolt this expects")
    span, index = max(
        (on_shank[i + 1] - on_shank[i], i) for i in range(len(on_shank) - 1))
    low, high = on_shank[index], on_shank[index + 1]
    if span < BOLT_MIN_SHANK_M:
        raise SystemExit(
            f"longest plain shank run on {BOLT_MESH} is {span * 1000:.2f} mm; "
            "cannot stretch without deforming the thread")

    # The head is whichever end carries the largest radius in the mesh.
    head_low = max(radius(c) for c in coords if c[axis] <= low) > max(
        radius(c) for c in coords if c[axis] >= high)
    # Under-head length is measured from the head's bearing face - the far edge
    # of the hex - not from where the shank cylinder happens to start.
    head_axial = [c[axis] for c in coords if radius(c) > nominal * 1.2]
    if not head_axial:
        raise SystemExit(f"{BOLT_MESH}: no bolt head found")
    under_head = max(head_axial) if head_low else min(head_axial)
    tip = max(c[axis] for c in coords) if head_low else min(c[axis] for c in coords)
    current = abs(tip - under_head)
    delta = target_in * 0.0254 - current
    if abs(delta) < 1e-6:
        report["bolt_length"] = {"mesh": BOLT_MESH, "skipped": "already at target"}
        return

    moved = 0
    for vertex in mesh.vertices:
        beyond = vertex.co[axis] >= high if head_low else vertex.co[axis] <= low
        if beyond:
            vertex.co[axis] += delta if head_low else -delta
            moved += 1
    mesh.update()

    report["bolt_length"] = {
        "mesh": BOLT_MESH,
        "bolts": len(users),
        "plain_shank_before_mm": round(span * 1000, 3),
        "plain_shank_after_mm": round((span + abs(delta)) * 1000, 3),
        "under_head_before_mm": round(current * 1000, 3),
        "under_head_after_mm": round(target_in * 0.0254 * 1000, 3),
        "target_in": target_in,
        "vertices_moved": moved,
    }


def seat_flange_hardware(report: dict) -> None:
    """Push the inboard washers and bolts back onto the flange they clamp.

    Nothing in this script moved them before. Every other placement check here is
    radial or rotational - bolt circle, hole phase - so a replacement flange of a
    different thickness passed every gate while burying the hardware inside
    itself. This measures the axial stack and fails if it does not close.
    """
    seated = []
    for index, name in enumerate(NEW_FITTING_NAMES):
        fitting = bpy.data.objects.get(name)
        if fitting is None:
            raise SystemExit(f"fitting not found: {name}")
        world = [fitting.matrix_world @ v.co for v in fitting.data.vertices]
        cx = sum(v.x for v in world) / len(world)
        cz = sum(v.z for v in world) / len(world)
        rim = [v.y for v in world if math.hypot(v.x - cx, v.z - cz) > FLANGE_RIM_R_M]
        if not rim:
            raise SystemExit(f"{name}: no flange rim found to seat against")
        back_face, front_face = min(rim), max(rim)

        washers, bolts = [], []
        for obj in bpy.data.objects:
            if obj.type != "MESH" or not obj.name.startswith(BOLT_PREFIXES[index]):
                continue
            own = [obj.matrix_world @ v.co for v in obj.data.vertices]
            ox = sum(v.x for v in own) / len(own)
            oz = sum(v.z for v in own) / len(own)
            if math.hypot(ox - cx, oz - cz) > RING_RADIUS_LIMIT_M:
                continue
            entry = (obj, min(v.y for v in own), max(v.y for v in own))
            if "/HWR-WSH-F8Z-075-" in obj.name:
                washers.append(entry)
            elif "/HWR-BLT-" in obj.name:
                bolts.append(entry)

        inboard = [w for w in washers if w[2] <= front_face]
        outboard = [w for w in washers if w[2] > front_face]
        if len(inboard) != BOLT_COUNT or len(outboard) != BOLT_COUNT:
            raise SystemExit(
                f"{name}: expected {BOLT_COUNT} washers each side of the flange, "
                f"found {len(inboard)} inboard and {len(outboard)} outboard")
        if len(bolts) != BOLT_COUNT:
            raise SystemExit(
                f"{name}: found {len(bolts)} bolts, expected {BOLT_COUNT}")

        before = max(w[2] for w in inboard)
        delta = back_face - before
        for obj, _, _ in inboard + bolts:
            obj.location.y += delta
        bpy.context.view_layer.update()

        after = max(
            (obj.matrix_world @ v.co).y
            for obj, _, _ in inboard for v in obj.data.vertices)
        residual_mm = (after - back_face) * 1000
        if abs(residual_mm) > SEAT_TOLERANCE_MM:
            raise SystemExit(
                f"{name}: inboard washers still {residual_mm:.3f} mm off the "
                "flange back face after seating")

        # Second seat: the bolt heads. In the source CAD each head sinks 3.66 mm
        # into its own washer. That was invisible while the whole stack was
        # buried inside the flange; with the joint closed up it would show.
        head_face = None
        for obj, _, _ in bolts:
            own = [obj.matrix_world @ v.co for v in obj.data.vertices]
            bx = sum(v.x for v in own) / len(own)
            bz = sum(v.z for v in own) / len(own)
            heads = [
                v.y for v in own
                if math.hypot(v.x - bx, v.z - bz) > BOLT_NOMINAL_SHANK_D_M * 0.6
            ]
            if not heads:
                raise SystemExit(f"{obj.name}: no bolt head found to seat")
            head_face = max(heads) if head_face is None else max(head_face, max(heads))
        washer_back = min(
            (obj.matrix_world @ v.co).y
            for obj, _, _ in inboard for v in obj.data.vertices)
        head_delta = washer_back - head_face
        for obj, _, _ in bolts:
            obj.location.y += head_delta
        bpy.context.view_layer.update()

        mating_gap_mm = None
        mating = bpy.data.objects.get(f"{MATING_FLANGE_PREFIX}{index + 1}")
        if mating is not None:
            mating_world = [mating.matrix_world @ v.co for v in mating.data.vertices]
            mx = sum(v.x for v in mating_world) / len(mating_world)
            mz = sum(v.z for v in mating_world) / len(mating_world)
            if math.hypot(mx - cx, mz - cz) < RING_RADIUS_LIMIT_M:
                mating_gap_mm = round(
                    (min(w[1] for w in outboard)
                     - max(v.y for v in mating_world)) * 1000, 3)

        seated.append({
            "fitting": name,
            "flange_back_face_mm": round(back_face * 1000, 3),
            "flange_front_face_mm": round(front_face * 1000, 3),
            "flange_plate_mm": round((front_face - back_face) * 1000, 3),
            "inboard_washer_before_mm": round(before * 1000, 3),
            "moved_mm": round(delta * 1000, 3),
            "seating_residual_mm": round(residual_mm, 4),
            "outboard_washer_gap_to_mating_flange_mm": mating_gap_mm,
            "bolt_head_sunk_into_washer_mm": round(-head_delta * 1000, 3),
            "bolt_head_seated_by_mm": round(head_delta * 1000, 3),
            "washers_moved": len(inboard),
            "bolts_moved": len(bolts),
        })
    report["hardware_seating"] = seated


def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser(prog="edit_rl300_geometry")
    parser.add_argument("--save-as", required=True, help="destination .blend")
    parser.add_argument("--report", help="write a JSON report here")
    parser.add_argument("--pump-glb", help="coarse replacement pump export")
    parser.add_argument("--pump-reference", help="approved blend providing pump placement")
    parser.add_argument(
        "--dissolve-deg", type=float, default=DEFAULT_DISSOLVE_DEG,
        help="coplanar merge angle for the pump; 0 welds only")
    parser.add_argument(
        "--raised-face", action="store_true",
        help="regenerate the fitting WITH a raised face (wrong for a full-face "
             "gasket; the joint here needs a flat face)")
    parser.add_argument(
        "--bolt-length-in", type=float, default=DEFAULT_BOLT_LENGTH_IN,
        help="under-head length to stretch the flange bolts to")
    parser.add_argument(
        "--no-compress", action="store_true",
        help="save uncompressed (the authoring master is compressed)")
    args = parser.parse_args(argv)
    if bool(args.pump_glb) != bool(args.pump_reference):
        parser.error("--pump-glb and --pump-reference must be supplied together")

    report: dict = {"source": bpy.data.filepath}
    report["material"] = {TURNED_MATERIAL: ensure_turned_material()}
    regenerate_fitting(report, args.raised_face)
    replace_fittings(report)
    widen_washers(report)
    seat_flange_hardware(report)
    lengthen_bolts(report, args.bolt_length_in)
    rehome_pump(report)
    if args.pump_glb:
        swap_pump(report, args.pump_glb, args.pump_reference)
    reduce_pump(report, args.dissolve_deg)
    if args.pump_glb and not report["pump_reduction"]["watertight_after_weld"]:
        raise SystemExit("coarse pump did not weld watertight; refusing to save")
    drop_scaffolding(report)
    drop_embedded_texts(report)
    strip_geometry_nodes(report)

    report["object_count"] = len(bpy.context.scene.objects)
    bpy.ops.wm.save_as_mainfile(
        filepath=args.save_as, compress=not args.no_compress)
    report["saved_to"] = args.save_as

    text = json.dumps(report, indent=1)
    if args.report:
        with open(args.report, "w", encoding="utf-8") as handle:
            handle.write(text)
    print("=== RL300 GEOMETRY EDIT REPORT ===")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

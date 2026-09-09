"""
Photoreal material calibration for MSP packages.

Additive companion to `materials.py` - that file is left untouched and its
presets are re-exported here, so this module is a drop-in replacement import.

Everything below is expressed in LINEAR values (what Blender's Principled BSDF
actually consumes), not sRGB hex, because metal base colours are measured
reflectance and round-tripping them through hex loses the point.
"""

from typing import Dict, Any

from .materials import (  # re-exported unchanged
    LIVERY_PRESETS,
    SUB_ASSEMBLY_MATERIALS,
    hex_to_linear_rgb,
)

__all__ = [
    "LIVERY_PRESETS",
    "SUB_ASSEMBLY_MATERIALS",
    "hex_to_linear_rgb",
    "HARDWARE_MATERIALS",
    "BEVEL_DEFAULTS",
    "METAL_REFERENCE",
    "apply_hardware_calibration",
]


# ---------------------------------------------------------------------------
# Measured linear base-colour reflectance for real metals.
#
# The most common cause of "my metal looks like white plastic" is a base colour
# up around 0.72-0.80 with metallic=1.0 under a bright uniform sky: the surface
# becomes a near-perfect mirror of a featureless environment and blows out.
# Real metals sit lower than most CAD material libraries assume.
# ---------------------------------------------------------------------------
METAL_REFERENCE: Dict[str, Dict[str, float]] = {
    "aluminium_polished":  {"r": 0.913, "g": 0.922, "b": 0.924},
    "aluminium_cast":      {"r": 0.615, "g": 0.620, "b": 0.625},
    "steel_machined":      {"r": 0.560, "g": 0.570, "b": 0.577},
    "stainless_304":       {"r": 0.620, "g": 0.628, "b": 0.636},
    "stainless_polished":  {"r": 0.720, "g": 0.730, "b": 0.750},
    "zinc_plated":         {"r": 0.664, "g": 0.674, "b": 0.680},
    "black_oxide":         {"r": 0.052, "g": 0.048, "b": 0.045},
    "cast_iron":           {"r": 0.180, "g": 0.180, "b": 0.184},
}


# ---------------------------------------------------------------------------
# Hardware materials, keyed to the MSP_* material names already in the .blend.
#
# `roughness_range` drives a per-object Object Info -> Random -> Map Range
# jitter. Fasteners are linked duplicates sharing one mesh datablock, so
# without this every bolt in a flange ring shades identically and the whole
# joint reads as one extruded part rather than eight separate fasteners.
# ---------------------------------------------------------------------------
HARDWARE_MATERIALS: Dict[str, Dict[str, Any]] = {
    "MSP_STAINLESS_FASTENER": {
        "description": "Bolt heads and nuts - 304 stainless, as-forged (duller than a washer)",
        "base_color": METAL_REFERENCE["stainless_304"],
        "metallic": 1.0,
        "roughness": 0.36,
        "roughness_range": [0.30, 0.42],
    },
    "MSP_STAINLESS": {
        "description": "Flat washers and general stainless hardware - polished",
        "base_color": METAL_REFERENCE["stainless_polished"],
        "metallic": 1.0,
        "roughness": 0.22,
        "roughness_range": [0.16, 0.29],
    },
    "MSP_ALUMINUM_CAST": {
        "description": "Hose fittings and cam-and-groove couplings - sand-cast aluminium",
        "base_color": METAL_REFERENCE["aluminium_cast"],
        "metallic": 1.0,
        "roughness": 0.62,
        "roughness_range": [0.55, 0.69],
        "noise_bump": {"scale": 380.0, "detail": 6.0, "strength": 0.28, "distance": 0.0016},
    },
    "MSP_ALUMINUM": {
        "description": "Extruded / machined aluminium components",
        "base_color": METAL_REFERENCE["aluminium_polished"],
        "metallic": 1.0,
        "roughness": 0.45,
        "roughness_range": [0.40, 0.52],
    },
    "MSP_STEEL_MACHINED": {
        "description": "Weld-on flanges and machined steel faces",
        "base_color": METAL_REFERENCE["steel_machined"],
        "metallic": 1.0,
        "roughness": 0.38,
        "roughness_range": [0.32, 0.45],
        "anisotropic": 0.35,
    },
    "MSP_STEEL_CAST": {
        "description": "Cast and weldment steel, mill scale finish",
        "base_color": METAL_REFERENCE["cast_iron"],
        "metallic": 0.90,
        "roughness": 0.62,
        "roughness_range": [0.55, 0.70],
    },
    "MSP_RUBBER": {
        "description": "Flange gaskets and rubber seals",
        "base_color": {"r": 0.016, "g": 0.018, "b": 0.020},
        "metallic": 0.0,
        "roughness": 0.78,
        "roughness_range": [0.72, 0.86],
    },
}


# Radius is in scene metres. 0.4 mm is a realistic machined break-edge and is
# the single highest realism-per-byte change available: it costs no geometry.
BEVEL_DEFAULTS: Dict[str, Any] = {
    "enabled": True,
    "radius_m": 0.0004,
    "samples": 4,
    "skip_keywords": ["glass", "airway", "volume", "shadow"],
}


def _rgba(c: Dict[str, float]):
    return (c["r"], c["g"], c["b"], 1.0)


def apply_hardware_calibration(bpy, overrides: Dict[str, Any] = None) -> Dict[str, str]:
    """Retune MSP_* metal materials in an already-open scene.

    Safe to call on any scene: materials that are not present are skipped, and
    nothing is created. Intended to be called from the render worker after the
    .blend is opened and before the photoreal pass runs.
    """
    overrides = overrides or {}
    table = dict(HARDWARE_MATERIALS)
    for name, patch in overrides.items():
        table.setdefault(name, {}).update(patch)

    report = {}
    for name, spec in table.items():
        mat = bpy.data.materials.get(name)
        if not mat or not mat.use_nodes or mat.node_tree is None:
            report[name] = "absent"
            continue
        bsdf = next((n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
        if bsdf is None:
            report[name] = "no principled bsdf"
            continue

        bsdf.inputs["Base Color"].default_value = _rgba(spec["base_color"])
        bsdf.inputs["Metallic"].default_value = spec.get("metallic", 1.0)
        if "anisotropic" in spec and "Anisotropic" in bsdf.inputs:
            bsdf.inputs["Anisotropic"].default_value = spec["anisotropic"]

        rough_in = bsdf.inputs["Roughness"]
        lo, hi = spec.get("roughness_range", [spec.get("roughness", 0.4)] * 2)
        if rough_in.is_linked:
            # An existing jitter chain is already wired; just retarget its range.
            up = rough_in.links[0].from_node
            if up.type == "MAP_RANGE":
                up.inputs["To Min"].default_value = lo
                up.inputs["To Max"].default_value = hi
                report[name] = f"retuned jitter {lo:.2f}-{hi:.2f}"
            else:
                report[name] = "roughness driven by custom nodes, left alone"
        else:
            nt = mat.node_tree
            oi = nt.nodes.new("ShaderNodeObjectInfo")
            oi.location = (-620, -260)
            mr = nt.nodes.new("ShaderNodeMapRange")
            mr.location = (-400, -260)
            mr.inputs["From Min"].default_value = 0.0
            mr.inputs["From Max"].default_value = 1.0
            mr.inputs["To Min"].default_value = lo
            mr.inputs["To Max"].default_value = hi
            nt.links.new(oi.outputs["Random"], mr.inputs["Value"])
            nt.links.new(mr.outputs["Result"], rough_in)
            report[name] = f"added per-object jitter {lo:.2f}-{hi:.2f}"

        # Keep Workbench / solid-shading previews in sync with the shader.
        mat.diffuse_color = _rgba(spec["base_color"])
        mat.metallic = spec.get("metallic", 1.0)
        mat.roughness = spec.get("roughness", 0.4)

    return report

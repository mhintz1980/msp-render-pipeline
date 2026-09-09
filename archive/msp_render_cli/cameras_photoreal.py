"""
Photoreal camera presets for MSP packages.

Additive companion to `cameras.py`, which is left untouched and re-exported.

Two things are different here:

1.  Longer glass. The stock P1-P8 hero set uses 35-50 mm at 2.1-2.8x radius.
    At those distances a 50 mm lens gives noticeable wide-angle divergence on
    vertical panel edges, which reads as "3D render" rather than "photograph".
    Real equipment product photography is shot long - 85-135 mm from further
    back. The PR_* presets below hold roughly the same framing with a longer
    lens and a larger distance multiplier.

2.  Depth of field. Every preset carries a `depth_of_field` block. A render
    that is uniformly sharp from the front flange to the rear hitch is the
    other instant tell. f/8 to f/11 keeps the machine readable while still
    softening the background.
"""

import math
from typing import Dict, Any, Tuple

from .cameras import CAMERA_PRESETS, calculate_camera_transform  # re-exported

__all__ = [
    "CAMERA_PRESETS",
    "calculate_camera_transform",
    "PHOTOREAL_CAMERA_PRESETS",
    "DETAIL_CAMERA_PRESETS",
    "ALL_PRESETS",
    "resolve_preset",
]


def _dof(f_stop: float, focus_object: str = None, focus_distance: float = None):
    spec: Dict[str, Any] = {"enabled": True, "f_stop": f_stop, "blades": 8}
    if focus_object:
        spec["focus_object"] = focus_object
    if focus_distance is not None:
        spec["focus_distance"] = focus_distance
    return spec


# ---------------------------------------------------------------------------
# Long-lens equivalents of the standard hero set.
# ---------------------------------------------------------------------------
PHOTOREAL_CAMERA_PRESETS: Dict[str, Dict[str, Any]] = {
    "PR1_FRONT_ISO": {
        "name": "PR1 Front Three-Quarter Isometric (long lens)",
        "description": "P1 framing shot at 100 mm from further back - flat perspective, product-photo feel",
        "azimuth_deg": 45.0,
        "elevation_deg": 13.0,
        "focal_length_mm": 100.0,
        "distance_multiplier": 4.8,
        "target_offset_z_ratio": 0.40,
        "depth_of_field": _dof(9.0),
    },
    "PR2_FRONT_ELEVATION": {
        "name": "PR2 Direct Front Elevation (long lens)",
        "description": "Head-on view of the discharge manifold and flanged ports at 135 mm",
        "azimuth_deg": 0.0,
        "elevation_deg": 3.0,
        "focal_length_mm": 135.0,
        "distance_multiplier": 6.4,
        "target_offset_z_ratio": 0.45,
        "depth_of_field": _dof(11.0),
    },
    "PR3_RIGHT_THREE_QUARTER": {
        "name": "PR3 Right Three-Quarter (long lens)",
        "azimuth_deg": 62.0,
        "elevation_deg": 11.0,
        "focal_length_mm": 100.0,
        "distance_multiplier": 4.8,
        "target_offset_z_ratio": 0.42,
        "depth_of_field": _dof(9.0),
    },
    "PR4_LEFT_THREE_QUARTER": {
        "name": "PR4 Left Three-Quarter (long lens)",
        "azimuth_deg": -62.0,
        "elevation_deg": 11.0,
        "focal_length_mm": 100.0,
        "distance_multiplier": 4.8,
        "target_offset_z_ratio": 0.42,
        "depth_of_field": _dof(9.0),
    },
    "PR7_LOW_HERO": {
        "name": "PR7 Low-Angle Hero (moderate wide)",
        "description": "Kept deliberately wider than the others - the low hero wants some drama",
        "azimuth_deg": 35.0,
        "elevation_deg": 4.0,
        "focal_length_mm": 50.0,
        "distance_multiplier": 3.0,
        "target_offset_z_ratio": 0.35,
        "depth_of_field": _dof(7.1),
    },
}


# ---------------------------------------------------------------------------
# Close-up detail presets.
#
# `distance_multiplier` here is relative to the package radius as usual, but
# these sit close enough that `target_offset` in the manifest should be used
# to aim at the specific feature. `focus_object` names a mesh in the .blend
# so focus tracks the feature instead of a hard-coded distance.
# ---------------------------------------------------------------------------
DETAIL_CAMERA_PRESETS: Dict[str, Dict[str, Any]] = {
    "D1_DISCHARGE_FLANGE": {
        "name": "D1 Discharge Flange Detail",
        "description": "Bolted flange joint - gasket line, fastener heads, cast coupling texture",
        "azimuth_deg": 28.0,
        "elevation_deg": 8.0,
        "focal_length_mm": 110.0,
        "distance_multiplier": 0.95,
        "target_offset_z_ratio": 0.62,
        "depth_of_field": _dof(6.3, focus_object="V2FLG-WO-A200-1.001"),
    },
    "D2_FASTENER_MACRO": {
        "name": "D2 Fastener Macro",
        "description": "Single bolt head - grade markings, washer separation, edge highlights",
        "azimuth_deg": 14.0,
        "elevation_deg": 6.0,
        "focal_length_mm": 135.0,
        "distance_multiplier": 0.42,
        "target_offset_z_ratio": 0.62,
        "depth_of_field": _dof(4.0),
    },
    "D3_CONTROL_PANEL": {
        "name": "D3 Control Panel Detail",
        "description": "LCD cluster and panel face at a shallow angle",
        "azimuth_deg": -40.0,
        "elevation_deg": 10.0,
        "focal_length_mm": 85.0,
        "distance_multiplier": 1.20,
        "target_offset_z_ratio": 0.70,
        "depth_of_field": _dof(5.6),
    },
    "D4_INTAKE_LOUVER": {
        "name": "D4 Intake Louver Detail",
        "description": "Honeycomb intake screen - shows AO depth and paint sheen",
        "azimuth_deg": 20.0,
        "elevation_deg": 16.0,
        "focal_length_mm": 100.0,
        "distance_multiplier": 1.10,
        "target_offset_z_ratio": 0.78,
        "depth_of_field": _dof(7.1),
    },
}


ALL_PRESETS: Dict[str, Dict[str, Any]] = {
    **CAMERA_PRESETS,
    **PHOTOREAL_CAMERA_PRESETS,
    **DETAIL_CAMERA_PRESETS,
}


def resolve_preset(name: str) -> Dict[str, Any]:
    """Look a preset up across the stock, photoreal and detail sets."""
    if name in ALL_PRESETS:
        return dict(ALL_PRESETS[name])
    raise KeyError(
        f"Unknown camera preset '{name}'. Available: {sorted(ALL_PRESETS)}"
    )


def hyperfocal_focus_distance(focal_length_mm: float, f_stop: float,
                              subject_distance_m: float,
                              circle_of_confusion_mm: float = 0.029) -> float:
    """Focus point that maximises usable sharpness across a subject.

    Focusing one third into the subject depth is the usual product-photography
    rule; this returns that point clamped to the near limit of acceptable
    sharpness so the front flange never goes soft.
    """
    f = focal_length_mm
    h = (f * f) / (f_stop * circle_of_confusion_mm) + f          # hyperfocal, mm
    s = subject_distance_m * 1000.0
    if s >= h:
        return h / 1000.0
    near = (h * s) / (h + (s - f))
    return max(near, s * 0.92) / 1000.0

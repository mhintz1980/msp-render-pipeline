"""
Standard Studio Camera Presets for Myers-Seth Pumps.
Calibrated to match the P1–P8 physical studio photography series.
"""

import math
from typing import Dict, Any, Tuple

CAMERA_PRESETS: Dict[str, Dict[str, Any]] = {
    "P1_FRONT_ISO": {
        "name": "P1 Front Three-Quarter Isometric",
        "description": "Standard commercial hero view showing front intake/discharge and side profile",
        "azimuth_deg": 45.0,
        "elevation_deg": 14.0,
        "focal_length_mm": 50.0,
        "distance_multiplier": 2.4,
        "target_offset_z_ratio": 0.40
    },
    "P2_FRONT_ELEVATION": {
        "name": "P2 Direct Front Elevation",
        "description": "Direct head-on view of pump face, manifold connections, and front doors",
        "azimuth_deg": 0.0,
        "elevation_deg": 4.0,
        "focal_length_mm": 65.0,
        "distance_multiplier": 2.5,
        "target_offset_z_ratio": 0.45
    },
    "P3_RIGHT_THREE_QUARTER": {
        "name": "P3 Right Three-Quarter Perspective",
        "description": "Offset view emphasizing right-hand maintenance access door and engine bay",
        "azimuth_deg": 65.0,
        "elevation_deg": 12.0,
        "focal_length_mm": 50.0,
        "distance_multiplier": 2.4,
        "target_offset_z_ratio": 0.42
    },
    "P4_LEFT_THREE_QUARTER": {
        "name": "P4 Left Three-Quarter Perspective",
        "description": "Offset view emphasizing left-hand discharge manifold and battery compartment",
        "azimuth_deg": -65.0,
        "elevation_deg": 12.0,
        "focal_length_mm": 50.0,
        "distance_multiplier": 2.4,
        "target_offset_z_ratio": 0.42
    },
    "P5_REAR_THREE_QUARTER": {
        "name": "P5 Rear Three-Quarter Elevation",
        "description": "Rear view showing radiator exhaust louver, muffler stack, and hitch connection",
        "azimuth_deg": 135.0,
        "elevation_deg": 16.0,
        "focal_length_mm": 50.0,
        "distance_multiplier": 2.4,
        "target_offset_z_ratio": 0.45
    },
    "P6_SIDE_PROFILE": {
        "name": "P6 Direct Side Profile 90°",
        "description": "Strict orthogonal side elevation for engineering line-up and dimensional verification",
        "azimuth_deg": 90.0,
        "elevation_deg": 2.0,
        "focal_length_mm": 85.0,
        "distance_multiplier": 2.8,
        "target_offset_z_ratio": 0.42
    },
    "P7_LOW_HERO": {
        "name": "P7 Low-Angle Hero Ground View",
        "description": "Dramatic ground-level perspective conveying scale, durability, and ground clearance",
        "azimuth_deg": 35.0,
        "elevation_deg": 4.0,
        "focal_length_mm": 35.0,
        "distance_multiplier": 2.1,
        "target_offset_z_ratio": 0.35
    },
    "P8_OVERHEAD_PLAN": {
        "name": "P8 Overhead 45° Plan View",
        "description": "High vantage point showing roof lifting bail, exhaust stack, and top panel layout",
        "azimuth_deg": 45.0,
        "elevation_deg": 45.0,
        "focal_length_mm": 50.0,
        "distance_multiplier": 2.6,
        "target_offset_z_ratio": 0.50
    }
}

def calculate_camera_transform(
    azimuth_deg: float,
    elevation_deg: float,
    distance: float,
    target_pos: Tuple[float, float, float] = (0.0, 0.0, 0.5)
) -> Tuple[Tuple[float, float, float], Tuple[float, float, float]]:
    """
    Computes camera (X, Y, Z) position and rotation Euler angles (pitch, roll, yaw)
    pointing directly at target_pos.
    """
    azimuth_rad = math.radians(azimuth_deg)
    elevation_rad = math.radians(elevation_deg)

    # Spherical to Cartesian coordinate system (Z-Up)
    x = target_pos[0] + distance * math.cos(elevation_rad) * math.sin(azimuth_rad)
    y = target_pos[1] - distance * math.cos(elevation_rad) * math.cos(azimuth_rad)
    z = target_pos[2] + distance * math.sin(elevation_rad)

    # Point at target
    dx = target_pos[0] - x
    dy = target_pos[1] - y
    dz = target_pos[2] - z
    dist_xy = math.sqrt(dx * dx + dy * dy)

    pitch = math.pi / 2.0 - math.atan2(dz, dist_xy)
    yaw = math.atan2(dx, -dy)
    roll = 0.0

    return ((x, y, z), (pitch, roll, yaw))

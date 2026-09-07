"""
PBR Material and RAL Color Palette Definitions for Myers-Seth Pumps (MSP) Packages.
Calibrated against physical studio photography (DD4S, RL200, RL300).
"""

from typing import Dict, Any

LIVERY_PRESETS: Dict[str, Dict[str, Any]] = {
    "msp_standard_yellow": {
        "name": "MSP Standard Industrial Yellow & Black",
        "description": "Standard factory livery: RAL 1023 Traffic Yellow body with Satin Black chassis frame",
        "body_color_hex": "#F7B500",
        "body_roughness": 0.35,
        "body_clearcoat": 0.25,
        "body_metallic": 0.0,
        "frame_color_hex": "#1B1B1B",
        "frame_roughness": 0.55,
        "frame_clearcoat": 0.10,
        "frame_metallic": 0.05,
        "decal_pack": "MSP"
    },
    "united_rentals_blue": {
        "name": "United Rentals Fleet Blue",
        "description": "Custom client fleet livery: Safety Blue powder coat with Satin Black containment base",
        "body_color_hex": "#00529B",
        "body_roughness": 0.32,
        "body_clearcoat": 0.30,
        "body_metallic": 0.0,
        "frame_color_hex": "#141414",
        "frame_roughness": 0.55,
        "frame_clearcoat": 0.10,
        "frame_metallic": 0.05,
        "decal_pack": "UNITED_RENTALS"
    },
    "sunbelt_green": {
        "name": "Sunbelt Rentals Fleet Green",
        "description": "Custom client fleet livery: Sunbelt Green powder coat with Dark Slate frame",
        "body_color_hex": "#006B3F",
        "body_roughness": 0.34,
        "body_clearcoat": 0.25,
        "body_metallic": 0.0,
        "frame_color_hex": "#1E201E",
        "frame_roughness": 0.50,
        "frame_clearcoat": 0.10,
        "frame_metallic": 0.05,
        "decal_pack": "SUNBELT"
    },
    "herc_rentals_white": {
        "name": "Herc Rentals Fleet White",
        "description": "Custom client fleet livery: Clean Equipment White with Safety Yellow accents",
        "body_color_hex": "#F2F4F7",
        "body_roughness": 0.28,
        "body_clearcoat": 0.35,
        "body_metallic": 0.0,
        "frame_color_hex": "#202020",
        "frame_roughness": 0.55,
        "frame_clearcoat": 0.10,
        "frame_metallic": 0.05,
        "decal_pack": "HERC"
    }
}

SUB_ASSEMBLY_MATERIALS: Dict[str, Dict[str, Any]] = {
    "cast_iron_pump": {
        "base_color_hex": "#282828",
        "roughness": 0.65,
        "metallic": 0.80,
        "normal_strength": 0.4
    },
    "zinc_plated_hardware": {
        "base_color_hex": "#D8D8D8",
        "roughness": 0.25,
        "metallic": 0.95,
        "normal_strength": 0.1
    },
    "rubber_fenders_tires": {
        "base_color_hex": "#171717",
        "roughness": 0.88,
        "metallic": 0.0,
        "normal_strength": 0.6
    },
    "exhaust_muffler": {
        "base_color_hex": "#4A4A4A",
        "roughness": 0.55,
        "metallic": 0.85,
        "normal_strength": 0.3
    },
    "control_panel_face": {
        "base_color_hex": "#1F1F1F",
        "roughness": 0.30,
        "metallic": 0.10,
        "normal_strength": 0.1
    }
}

def hex_to_linear_rgb(hex_code: str):
    """Converts hex color code to sRGB linear color tuple (R, G, B, A=1.0)."""
    hex_code = hex_code.lstrip('#')
    r = int(hex_code[0:2], 16) / 255.0
    g = int(hex_code[2:4], 16) / 255.0
    b = int(hex_code[4:6], 16) / 255.0
    # Convert sRGB gamma to linear space for Blender Cycles
    to_linear = lambda c: c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    return (to_linear(r), to_linear(g), to_linear(b), 1.0)

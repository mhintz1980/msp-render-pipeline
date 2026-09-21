"""
Job Manifest Parser and Validator for MSP Render Pipeline.
"""

import json
import os
from typing import Dict, Any, Tuple, Optional
from msp_render_cli.materials import LIVERY_PRESETS
from msp_render_cli.cameras import CAMERA_PRESETS

def load_manifest(manifest_path: str) -> Dict[str, Any]:
    """Loads a JSON manifest file from disk."""
    if not os.path.exists(manifest_path):
        raise FileNotFoundError(f"Manifest file not found: {manifest_path}")
    with open(manifest_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def validate_manifest(data: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """
    Validates manifest structure against required MSP fields.
    Returns (is_valid, error_message).
    """
    required_top = ["job_id", "package_model", "cad_source", "camera", "livery", "lighting", "output"]
    for field in required_top:
        if field not in data:
            return False, f"Missing required top-level field: '{field}'"

    # Validate cad_source
    if "file_path" not in data["cad_source"]:
        return False, "Missing 'cad_source.file_path'"

    # Validate camera
    cam_preset = data["camera"].get("preset")
    if not cam_preset:
        return False, "Missing 'camera.preset'"
    if cam_preset not in ["CUSTOM", "USE_SCENE_CAMERA", "PRESERVE_EXISTING"] and cam_preset not in CAMERA_PRESETS:
        return False, f"Unknown camera preset '{cam_preset}'. Valid: {list(CAMERA_PRESETS.keys())}"

    # Validate livery
    livery_preset = data["livery"].get("preset")
    if not livery_preset:
        return False, "Missing 'livery.preset'"
    if livery_preset not in ["custom", "preserve_existing"] and livery_preset not in LIVERY_PRESETS:
        return False, f"Unknown livery preset '{livery_preset}'. Valid: {list(LIVERY_PRESETS.keys())}"

    # Validate output dimensions
    out = data["output"]
    if out.get("width", 0) <= 0 or out.get("height", 0) <= 0:
        return False, "Output width and height must be positive integers"

    # New batch-3b fields are type-strict (a typo must fail loudly), while
    # every legacy field keeps its permissive behaviour.
    film = out.get("film_transparent")
    if film is not None and not isinstance(film, bool):
        return False, "output.film_transparent must be a boolean"
    floor_block = data.get("lighting", {}).get("floor")
    if floor_block is not None:
        if not isinstance(floor_block, dict):
            return False, "lighting.floor must be an object"
        floor_enabled = floor_block.get("enabled")
        if floor_enabled is not None and not isinstance(floor_enabled, bool):
            return False, "lighting.floor.enabled must be a boolean"
    comp = data.get("compositing", {})
    for key in ("product_scale",):
        if key in comp:
            value = comp[key]
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                return False, f"compositing.{key} must be a number"
    for key in ("product_offset_px", "product_offset_pct"):
        if key in comp:
            value = comp[key]
            if (not isinstance(value, (list, tuple)) or len(value) != 2
                    or any(isinstance(v, bool) or not isinstance(v, (int, float))
                           for v in value)):
                return False, f"compositing.{key} must be two numbers"

    # Feature combinations (floor vs film vs placement) have one authoritative
    # implementation, shared with the dispatcher and the probe.
    from composite_worker import validate_floor_config
    combo_errors = validate_floor_config(data)
    if combo_errors:
        return False, combo_errors[0]

    return True, None

def create_default_manifest(
    job_id: str,
    package_model: str,
    cad_path: str,
    camera_preset: str = "P1_FRONT_ISO",
    livery_preset: str = "msp_standard_yellow",
    lighting_preset: str = "studio_dark"
) -> Dict[str, Any]:
    """Generates a populated default manifest ready for execution."""
    livery_data = LIVERY_PRESETS.get(livery_preset, LIVERY_PRESETS["msp_standard_yellow"])
    return {
        "job_id": job_id,
        "package_model": package_model,
        "cad_source": {
            "file_path": cad_path,
            "format": cad_path.split('.')[-1].lower() if '.' in cad_path else "glb",
            "up_axis": "Z",
            "unit_scale": 1.0
        },
        "camera": {
            "preset": camera_preset,
            "focal_length_mm": 50.0,
            "elevation_deg": CAMERA_PRESETS.get(camera_preset, {}).get("elevation_deg", 14.0),
            "azimuth_deg": CAMERA_PRESETS.get(camera_preset, {}).get("azimuth_deg", 45.0),
            "target_offset": [0.0, 0.0, 0.45]
        },
        "livery": {
            "preset": livery_preset,
            "body_color_hex": livery_data["body_color_hex"],
            "body_roughness": livery_data["body_roughness"],
            "body_clearcoat": livery_data["body_clearcoat"],
            "frame_color_hex": livery_data["frame_color_hex"],
            "frame_roughness": livery_data["frame_roughness"],
            "decal_pack": livery_data["decal_pack"]
        },
        "lighting": {
            "preset": lighting_preset,
            "intensity_multiplier": 1.0,
            "color_temperature_k": 5500,
            "shadow_catcher": True
        },
        "output": {
            "width": 1920,
            "height": 1080,
            "samples": 128,
            "engine": "CYCLES",
            "denoiser": "OPENIMAGEDENOISE",
            "passes": {
                "beauty": True,
                "alpha_mask": True,
                "depth_map": True,
                "surface_normals": False,
                "contact_shadow": True
            },
            "output_dir": f"./output/{job_id}"
        },
        "compositing": {
            "enabled": False,
            "background_plate": "",
            "ai_environment_prompt": "construction bypass excavation trench, muddy soil, standing water, morning diffuse light",
            "shadow_opacity": 0.85,
            "edge_feather_px": 1
        }
    }

"""
Command Line Interface for Myers-Seth Pumps Render & Compositing Pipeline.
Built according to CLI-Anything agent-native ergonomics.
"""

import argparse
import sys
import os
import json
import subprocess
from typing import Optional

from msp_render_cli.manifest import load_manifest, validate_manifest, create_default_manifest
from msp_render_cli.materials import LIVERY_PRESETS
from msp_render_cli.cameras import CAMERA_PRESETS
from composite_worker import MSPCompositor

def cmd_presets(args):
    """Lists available camera, livery, and material presets."""
    print("\n=======================================================")
    print("  MYERS-SETH PUMPS (MSP) RENDER PRESETS & STANDARDS    ")
    print("=======================================================\n")
    
    print("--- LIVERY & POWDER COAT PRESETS ---")
    for key, spec in LIVERY_PRESETS.items():
        print(f"  • {key:<22} : {spec['name']}")
        print(f"    Body Color: {spec['body_color_hex']} | Frame: {spec['frame_color_hex']} | Decals: {spec['decal_pack']}")
    
    print("\n--- CAMERA RIG PRESETS (Physical Studio Series P1–P8) ---")
    for key, cam in CAMERA_PRESETS.items():
        print(f"  • {key:<24} : {cam['name']}")
        print(f"    Azimuth: {cam['azimuth_deg']}° | Elevation: {cam['elevation_deg']}° | Lens: {cam['focal_length_mm']}mm")
    print()

def cmd_new_job(args):
    """Generates a new job manifest JSON."""
    out_file = args.output or f"./job_{args.job_id}.json"
    manifest = create_default_manifest(
        job_id=args.job_id,
        package_model=args.model,
        cad_path=args.cad,
        camera_preset=args.camera,
        livery_preset=args.livery,
        lighting_preset=args.lighting
    )
    with open(out_file, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, indent=2)
    print(f"✓ Created job manifest at: {out_file}")

def cmd_validate(args):
    """Validates an existing job manifest."""
    try:
        data = load_manifest(args.manifest)
        is_valid, err = validate_manifest(data)
        if is_valid:
            print(f"✓ Manifest '{args.manifest}' is VALID.")
            print(f"  - Job ID:        {data.get('job_id')}")
            print(f"  - Model:         {data.get('package_model')}")
            print(f"  - CAD Source:    {data['cad_source'].get('file_path')}")
            print(f"  - Camera Preset: {data['camera'].get('preset')}")
            print(f"  - Livery:        {data['livery'].get('preset')} ({data['livery'].get('body_color_hex')})")
            print(f"  - Resolution:    {data['output'].get('width')}x{data['output'].get('height')}")
        else:
            print(f"✗ Manifest Validation FAILED: {err}", file=sys.stderr)
            sys.exit(1)
    except Exception as e:
        print(f"✗ Error reading manifest: {e}", file=sys.stderr)
        sys.exit(1)

def cmd_render_local(args):
    """Renders locally using Blender installed on host machine."""
    data = load_manifest(args.manifest)
    blender_bin = args.blender_bin or "blender"
    worker_script = os.path.join(os.path.dirname(__file__), "..", "render_worker.py")
    
    cmd = [blender_bin, "-b", "-P", worker_script, "--", os.path.abspath(args.manifest)]
    print(f"[MSP Render CLI] Executing local Blender command: {' '.join(cmd)}")
    try:
        res = subprocess.run(cmd, check=True)
        print(f"✓ Local render finished successfully.")
    except FileNotFoundError:
        print(f"✗ Blender executable '{blender_bin}' not found on PATH. Specify with --blender-bin or use dispatch-modal.", file=sys.stderr)
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        print(f"✗ Blender render failed with exit code {e.returncode}", file=sys.stderr)
        sys.exit(e.returncode)

def cmd_dispatch_modal(args):
    """Submits render job to Modal serverless cloud GPU worker."""
    print(f"[MSP Render CLI] Submitting job '{args.manifest}' to Modal Serverless GPU...")
    manifest = load_manifest(args.manifest)
    cad_path = manifest["cad_source"]["file_path"]
    
    if not os.path.exists(cad_path):
        print(f"✗ CAD source file not found locally: {cad_path}", file=sys.stderr)
        sys.exit(1)

    modal_cmd = [
        "modal", "run",
        os.path.join(os.path.dirname(__file__), "..", "render_worker.py"),
        "--manifest", os.path.abspath(args.manifest)
    ]
    print(f"  Executing command: {' '.join(modal_cmd)}")
    try:
        res = subprocess.run(modal_cmd, check=True)
        print(f"✓ Modal cloud job completed successfully.")
    except FileNotFoundError:
        print(f"✗ 'modal' CLI is not installed or authenticated. Run 'pip install modal && modal setup'.", file=sys.stderr)
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        print(f"✗ Modal dispatch failed: {e}", file=sys.stderr)
        sys.exit(e.returncode)

def cmd_composite(args):
    """Merges rendered/photographed product with background plate."""
    print(f"[MSP Render CLI] Compositing product '{args.product}' onto background '{args.background}'...")
    try:
        res = MSPCompositor.composite_asset(
            product_image_path=args.product,
            background_image_path=args.background,
            output_image_path=args.output,
            mask_image_path=args.mask,
            shadow_opacity=args.shadow_opacity
        )
        print("✓ Compositing Complete!")
        print(f"  - Output Image:          {res['output_path']}")
        print(f"  - Dimensions:            {res['dimensions'][0]}x{res['dimensions'][1]}")
        print(f"  - Product Fidelity Gate: {'PASS (100% exact pixels)' if res['fidelity_gate_pass'] else 'FAIL'}")
        print(f"  - Max Pixel Drift:       {res['max_pixel_drift']}")
    except Exception as e:
        print(f"✗ Compositing failed: {e}", file=sys.stderr)
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(
        prog="msp-render",
        description="Myers-Seth Pumps (MSP) Deterministic Render & Zero-Loss Compositing CLI"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Subcommand: presets
    sub_presets = subparsers.add_parser("presets", help="List available camera, livery, and lighting presets")
    sub_presets.set_defaults(func=cmd_presets)

    # Subcommand: new-job
    sub_new = subparsers.add_parser("new-job", help="Create a new render job manifest JSON")
    sub_new.add_argument("--job-id", required=True, help="Unique identifier for the job")
    sub_new.add_argument("--model", default="RL300_SAFE", help="MSP model identifier (e.g. RL300_SAFE, DD4SE_TRAILER)")
    sub_new.add_argument("--cad", required=True, help="Path to input CAD / GLB file")
    sub_new.add_argument("--camera", default="P1_FRONT_ISO", help="Camera preset (e.g. P1_FRONT_ISO, P7_LOW_HERO)")
    sub_new.add_argument("--livery", default="msp_standard_yellow", help="Livery preset (msp_standard_yellow, united_rentals_blue)")
    sub_new.add_argument("--lighting", default="studio_dark", help="Lighting preset (studio_dark, studio_white, excavation_pit_sunlit)")
    sub_new.add_argument("-o", "--output", help="Path to write JSON manifest to")
    sub_new.set_defaults(func=cmd_new_job)

    # Subcommand: validate
    sub_val = subparsers.add_parser("validate", help="Validate a job manifest against schema")
    sub_val.add_argument("manifest", help="Path to manifest JSON file")
    sub_val.set_defaults(func=cmd_validate)

    # Subcommand: render-local
    sub_rend = subparsers.add_parser("render-local", help="Render manifest locally using Blender")
    sub_rend.add_argument("manifest", help="Path to manifest JSON file")
    sub_rend.add_argument("--blender-bin", help="Path to blender executable if not on PATH")
    sub_rend.set_defaults(func=cmd_render_local)

    # Subcommand: dispatch-modal
    sub_modal = subparsers.add_parser("dispatch-modal", help="Dispatch render job to Modal cloud serverless worker")
    sub_modal.add_argument("manifest", help="Path to manifest JSON file")
    sub_modal.set_defaults(func=cmd_dispatch_modal)

    # Subcommand: composite
    sub_comp = subparsers.add_parser("composite", help="Composite beauty pass onto background plate with contact shadow")
    sub_comp.add_argument("-p", "--product", required=True, help="Path to product render or transparent studio photo")
    sub_comp.add_argument("-b", "--background", required=True, help="Path to background environment plate")
    sub_comp.add_argument("-o", "--output", required=True, help="Path to save final composited image")
    sub_comp.add_argument("-m", "--mask", help="Optional path to separate alpha mask")
    sub_comp.add_argument("--shadow-opacity", type=float, default=0.85, help="Contact shadow opacity (0.0 to 1.0)")
    sub_comp.set_defaults(func=cmd_composite)

    args = parser.parse_args()
    args.func(args)

if __name__ == "__main__":
    main()

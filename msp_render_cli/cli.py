"""
Command Line Interface for the Myers-Seth Pumps render & compositing pipeline.

    msp-render presets                 list camera / livery presets
    msp-render validate <job.json>     check a manifest before you burn GPU time
    msp-render render   <job.json>     Blender Cycles render -> transparent PNG
    msp-render composite <job.json>    seat that render on its background plate
    msp-render run      <job.json>     render + composite in one shot
"""

import argparse
import glob
import json
import os
import shutil
import subprocess
import sys
from typing import Optional

from msp_render_cli.manifest import load_manifest, validate_manifest, create_default_manifest
from msp_render_cli.materials import LIVERY_PRESETS
from msp_render_cli.cameras import CAMERA_PRESETS
from composite_worker import MSPCompositor, floor_mode as manifest_floor_mode

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
WORKER_SCRIPT = os.path.join(PROJECT_ROOT, "render_worker.py")


def _enable_unicode_output() -> None:
    """
    The Windows console defaults to cp1252, which cannot encode the check marks
    and bullets this CLI prints - every command would die with a
    UnicodeEncodeError before doing any work. Force UTF-8 on both streams.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def find_blender(explicit: Optional[str] = None) -> str:
    """
    Locates the Blender executable.

    Blender's Windows installer does not put blender.exe on PATH, so falling
    back to the standard install locations is the difference between the demo
    running and the demo stopping on 'blender not found'.
    """
    if explicit:
        if os.path.exists(explicit) or shutil.which(explicit):
            return explicit
        raise FileNotFoundError(f"--blender-bin '{explicit}' does not exist.")

    env = os.environ.get("MSP_BLENDER_BIN")
    if env and os.path.exists(env):
        return env

    on_path = shutil.which("blender")
    if on_path:
        return on_path

    patterns = [
        r"C:\Program Files\Blender Foundation\Blender *\blender.exe",
        r"C:\Program Files (x86)\Steam\steamapps\common\Blender\blender.exe",
        "/Applications/Blender.app/Contents/MacOS/Blender",
        "/usr/bin/blender",
        "/usr/local/bin/blender",
    ]
    found = []
    for pattern in patterns:
        found.extend(glob.glob(pattern))
    if found:
        # Highest version number wins.
        return sorted(found)[-1]

    raise FileNotFoundError(
        "Blender was not found. Install it, add it to PATH, pass --blender-bin "
        "<path to blender.exe>, or set the MSP_BLENDER_BIN environment variable.")


def _job_paths(manifest: dict, manifest_path: str):
    """Returns (output_dir, beauty_png, final_png) for a manifest."""
    out_dir = manifest.get("output", {}).get("output_dir") or f"./output/{manifest['job_id']}"
    if not os.path.isabs(out_dir):
        out_dir = os.path.normpath(os.path.join(PROJECT_ROOT, out_dir))
    return (out_dir,
            os.path.join(out_dir, "beauty.png"),
            os.path.join(out_dir, f"final_{manifest['job_id']}.png"))


def _resolve_asset(path: str, manifest_path: str) -> str:
    """Resolves a manifest-relative asset path against the project root."""
    if not path or os.path.isabs(path):
        return path
    for root in (PROJECT_ROOT, os.path.dirname(os.path.abspath(manifest_path)), os.getcwd()):
        candidate = os.path.normpath(os.path.join(root, path))
        if os.path.exists(candidate):
            return candidate
    return path


def _load_valid(manifest_path: str) -> dict:
    data = load_manifest(manifest_path)
    ok, err = validate_manifest(data)
    if not ok:
        print(f"✗ Manifest validation FAILED: {err}", file=sys.stderr)
        sys.exit(1)
    return data


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

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

    print("\n--- LIGHTING PRESETS ---")
    print("  • studio_dark            : 3-point softbox rig on black")
    print("  • studio_white           : 3-point softbox rig on white")
    print("  • excavation_pit_sunlit  : physical sky + 5400K key sun + soil bounce")
    print("  • preserve_existing      : keep the lights already in the .blend")
    print("  Any preset can add image-based lighting via lighting.hdri_path.\n")


def cmd_new_job(args):
    """Generates a new job manifest JSON."""
    out_file = args.output or f"./jobs/{args.job_id}.json"
    manifest = create_default_manifest(
        job_id=args.job_id,
        package_model=args.model,
        cad_path=args.cad,
        camera_preset=args.camera,
        livery_preset=args.livery,
        lighting_preset=args.lighting,
    )
    os.makedirs(os.path.dirname(os.path.abspath(out_file)), exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    print(f"✓ Created job manifest at: {out_file}")


def cmd_validate(args):
    """Validates an existing job manifest and checks every file it references."""
    try:
        data = load_manifest(args.manifest)
    except Exception as e:
        print(f"✗ Error reading manifest: {e}", file=sys.stderr)
        sys.exit(1)

    ok, err = validate_manifest(data)
    if not ok:
        print(f"✗ Manifest Validation FAILED: {err}", file=sys.stderr)
        sys.exit(1)

    print(f"✓ Manifest '{args.manifest}' is VALID.")
    print(f"  - Job ID:        {data.get('job_id')}")
    print(f"  - Model:         {data.get('package_model')}")
    print(f"  - Camera Preset: {data['camera'].get('preset')}")
    print(f"  - Livery:        {data['livery'].get('preset')}")
    print(f"  - Lighting:      {data['lighting'].get('preset')}")
    print(f"  - Resolution:    {data['output'].get('width')}x{data['output'].get('height')}"
          f" @ {data['output'].get('samples')} samples")

    # Referenced files are the thing that actually breaks a live run, so check them.
    missing = 0
    checks = [("CAD source", data["cad_source"].get("file_path")),
              ("HDRI plate", data["lighting"].get("hdri_path")),
              ("Background plate", data.get("compositing", {}).get("background_plate"))]
    for label, raw in checks:
        if not raw:
            continue
        resolved = _resolve_asset(raw, args.manifest)
        if os.path.exists(resolved):
            print(f"  ✓ {label}: {resolved}")
        else:
            print(f"  ✗ {label} NOT FOUND: {raw}", file=sys.stderr)
            missing += 1

    try:
        print(f"  ✓ Blender:   {find_blender(getattr(args, 'blender_bin', None))}")
    except FileNotFoundError as e:
        print(f"  ✗ {e}", file=sys.stderr)
        missing += 1

    if missing:
        print(f"\n✗ {missing} referenced item(s) missing - fix these before rendering.",
              file=sys.stderr)
        sys.exit(1)
    print("\n✓ Pre-flight clean. Ready to render.")


def cmd_render(args):
    """Renders a manifest locally with headless Blender Cycles."""
    manifest = _load_valid(args.manifest)
    blender_bin = find_blender(args.blender_bin)
    out_dir, beauty, _ = _job_paths(manifest, args.manifest)

    cmd = [blender_bin, "-b", "-P", WORKER_SCRIPT, "--", os.path.abspath(args.manifest)]
    print(f"[MSP Render CLI] Blender: {blender_bin}")
    print(f"[MSP Render CLI] Job:     {manifest['job_id']}")
    print(f"[MSP Render CLI] Output:  {out_dir}\n")

    try:
        subprocess.run(cmd, check=True, cwd=PROJECT_ROOT)
    except subprocess.CalledProcessError as e:
        print(f"✗ Blender render failed with exit code {e.returncode}", file=sys.stderr)
        sys.exit(e.returncode)

    if not os.path.exists(beauty):
        print(f"✗ Render reported success but no beauty pass was written to {beauty}",
              file=sys.stderr)
        sys.exit(1)
    print(f"\n✓ Render complete (transparent background): {beauty}")


def cmd_composite(args):
    """Seats an existing beauty pass on the manifest's background plate."""
    manifest = _load_valid(args.manifest)
    comp = manifest.get("compositing", {})
    floor_on = manifest_floor_mode(manifest)
    plate = args.background or comp.get("background_plate")
    if not plate and not floor_on:
        print("✗ No background plate. Set compositing.background_plate in the "
              "manifest or pass --background.", file=sys.stderr)
        sys.exit(1)
    plate = _resolve_asset(plate, args.manifest)

    out_dir, beauty, final = _job_paths(manifest, args.manifest)
    product = args.product or beauty
    output = args.output or final

    if not os.path.exists(product):
        print(f"✗ No render found at {product}.\n"
              f"  Run:  python -m msp_render_cli render {args.manifest}", file=sys.stderr)
        sys.exit(1)

    print(f"[MSP Render CLI] Product:    {product}")
    if floor_on:
        print(f"[MSP Render CLI] Mode:        rendered_floor (no plate is "
              f"pasted; the rendered floor is preserved)\n")
    else:
        print(f"[MSP Render CLI] Background: {plate}\n")
    try:
        if floor_on:
            matte_path = os.path.join(out_dir, "beauty-matte.png")
            mask_path = os.path.join(out_dir, "mask.png")
            lens_kwargs = {key: comp[key] for key in
                           ("lens_vignette", "lens_bloom", "lens_grain")
                           if key in comp}
            res = MSPCompositor.composite_rendered_floor_asset(
                product,
                mask_path,
                matte_path,
                output,
                shadow_opacity=(args.shadow_opacity if args.shadow_opacity is not None
                                else comp.get("shadow_opacity")),
                **lens_kwargs,
            )
        else:
            res = MSPCompositor.composite_asset(
                product_image_path=product,
                background_image_path=plate,
                output_image_path=output,
                shadow_opacity=(args.shadow_opacity if args.shadow_opacity is not None
                                else comp.get("shadow_opacity", 0.85)),
                product_scale=comp.get("product_scale", 1.0),
                product_offset_px=comp.get("product_offset_px", (0, 0)),
                product_offset_pct=comp.get("product_offset_pct"),
                sun_direction=comp.get("sun_direction", "top_left"),
            )
    except Exception as e:
        print(f"✗ Compositing failed: {e}", file=sys.stderr)
        sys.exit(1)

    print("✓ Compositing complete.")
    if res.get("mode") == "rendered_floor":
        print("  - Composite Mode:        rendered_floor")
        print(f"  - Synthetic Shadow:      "
              f"configured {res.get('configured_shadow_opacity', comp.get('shadow_opacity'))}, "
              f"effective {res.get('effective_shadow_opacity', 0.0)} (real rendered "
              f"floor supplies the shadow)")
    print(f"  - Output Image:          {res['output_path']}")
    print(f"  - Dimensions:            {res['dimensions'][0]}x{res['dimensions'][1]}")
    print(f"  - Product Fidelity Gate: "
          f"{'PASS (100% exact machine pixels)' if res['fidelity_gate_pass'] else 'FAIL'}")
    if res["mask_gate_pass"] is None:
        mask_gate = "N/A (no mask file supplied)"
    else:
        mask_gate = ("PASS (mask seated with the product)"
                     if res["mask_gate_pass"] else "FAIL")
    print(f"  - Mask Consistency Gate: {mask_gate}")
    print(f"  - Saved Image Check:     "
          f"{'PASS (file re-read pixel-exact)' if res['saved_check_pass'] else 'FAIL'}")
    print(f"  - Max Pixel Drift:       {res['max_pixel_drift']}")
    print(f"  - Frame Coverage:        {res['coverage_pct']}%")
    if res["status"] != "success":
        sys.exit(1)


def cmd_run(args):
    """Render then composite, in one command."""
    cmd_render(args)
    manifest = _load_valid(args.manifest)
    comp = manifest.get("compositing", {})
    if not args.background and not (comp.get("enabled") and comp.get("background_plate")):
        # A no-background job is a legitimate deliverable, not an error: the
        # transparent cut-out is the master asset for print and web.
        print("\n[MSP Render CLI] compositing.enabled is false for this job - "
              "the transparent render is the final deliverable.")
        return
    print()
    cmd_composite(args)


def cmd_dispatch_modal(args):
    """Submits the render job to a Modal serverless cloud GPU worker."""
    manifest = _load_valid(args.manifest)
    cad_path = _resolve_asset(manifest["cad_source"]["file_path"], args.manifest)
    if not os.path.exists(cad_path):
        print(f"✗ CAD source file not found locally: {cad_path}", file=sys.stderr)
        sys.exit(1)

    modal_cmd = [sys.executable, "-m", "modal", "run", WORKER_SCRIPT,
                 "--manifest", os.path.abspath(args.manifest)]
    print(f"[MSP Render CLI] Submitting '{manifest['job_id']}' to Modal serverless GPU...")
    try:
        subprocess.run(modal_cmd, check=True, cwd=PROJECT_ROOT)
        print("✓ Modal cloud job completed successfully.")
    except FileNotFoundError:
        print("✗ The 'modal' CLI is not installed or authenticated. "
              "Run 'pip install modal && modal setup'.", file=sys.stderr)
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        print(f"✗ Modal dispatch failed: {e}", file=sys.stderr)
        sys.exit(e.returncode)


# ---------------------------------------------------------------------------

def main():
    _enable_unicode_output()

    parser = argparse.ArgumentParser(
        prog="msp-render",
        description="Myers-Seth Pumps deterministic render & zero-loss compositing CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    sub = subparsers.add_parser("presets", help="List camera, livery, and lighting presets")
    sub.set_defaults(func=cmd_presets)

    sub = subparsers.add_parser("new-job", help="Create a new render job manifest JSON")
    sub.add_argument("--job-id", required=True, help="Unique identifier for the job")
    sub.add_argument("--model", default="RL300_SAFE", help="MSP model identifier")
    sub.add_argument("--cad", required=True, help="Path to the input .blend / .glb / .obj")
    sub.add_argument("--camera", default="P1_FRONT_ISO", help="Camera preset")
    sub.add_argument("--livery", default="msp_standard_yellow", help="Livery preset")
    sub.add_argument("--lighting", default="studio_dark", help="Lighting preset")
    sub.add_argument("-o", "--output", help="Path to write the manifest to")
    sub.set_defaults(func=cmd_new_job)

    sub = subparsers.add_parser("validate", help="Validate a manifest and pre-flight its assets")
    sub.add_argument("manifest")
    sub.add_argument("--blender-bin", help="Path to blender executable")
    sub.set_defaults(func=cmd_validate)

    sub = subparsers.add_parser("render", help="Render locally with headless Blender Cycles")
    sub.add_argument("manifest")
    sub.add_argument("--blender-bin", help="Path to blender executable")
    sub.set_defaults(func=cmd_render)

    sub = subparsers.add_parser("composite", help="Composite a render onto its background plate")
    sub.add_argument("manifest")
    sub.add_argument("-p", "--product", help="Override the product render path")
    sub.add_argument("-b", "--background", help="Override the background plate path")
    sub.add_argument("-o", "--output", help="Override the output image path")
    sub.add_argument("--shadow-opacity", type=float, help="Contact shadow opacity (0.0-1.0)")
    sub.set_defaults(func=cmd_composite)

    sub = subparsers.add_parser("run", help="Render and composite in one command")
    sub.add_argument("manifest")
    sub.add_argument("--blender-bin", help="Path to blender executable")
    sub.add_argument("-p", "--product", help="Override the product render path")
    sub.add_argument("-b", "--background", help="Override the background plate path")
    sub.add_argument("-o", "--output", help="Override the output image path")
    sub.add_argument("--shadow-opacity", type=float, help="Contact shadow opacity (0.0-1.0)")
    sub.set_defaults(func=cmd_run)

    sub = subparsers.add_parser("dispatch-modal", help="Dispatch the job to a Modal cloud GPU")
    sub.add_argument("manifest")
    sub.set_defaults(func=cmd_dispatch_modal)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

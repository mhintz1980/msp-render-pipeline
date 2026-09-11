"""Local T03 reference proof. Linux runs receive only declared read-only inputs.

Run with the repository Python environment on Windows (WSL Ubuntu) or Linux.
This writes a review candidate, never an owner approval or cloud authorization.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
VERSION = "5.1.1"
BUILD = "b70da489d7f4"
ARCHIVE_SHA256 = "6f9fff89fef154ef7974d1a1c4b916ab4bc1f5618bcb48d5befee1bd0a7c7f2a"
LIMITS = {"mask_iou_min": 0.995, "coverage_delta_max": 0.005,
          "linear_rgb_mae_max": 0.01, "linear_rgb_p99_max": 0.05,
          "occupancy_min": 0.01, "structure_absolute_tolerance": 1e-5}


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def image_metrics(reference, candidate, heatmap=None):
    """Compare decoded 8-bit sRGB PNGs; product interior excludes alpha edges."""
    import numpy as np
    from PIL import Image

    with Image.open(reference) as im:
        a = np.asarray(im.convert("RGBA"))
    with Image.open(candidate) as im:
        b = np.asarray(im.convert("RGBA"))
    if a.shape != b.shape:
        return {"passed": False, "failures": ["DIMENSIONS_MISMATCH"]}
    ma, mb = a[..., 3] > 8, b[..., 3] > 8
    ca, cb = float(ma.mean()), float(mb.mean())
    opaque = (a[..., 3] == 255) & (b[..., 3] == 255)
    interior = np.zeros_like(opaque)
    if min(opaque.shape) >= 3:
        interior[1:-1, 1:-1] = np.logical_and.reduce([
            opaque[y:y + opaque.shape[0] - 2, x:x + opaque.shape[1] - 2]
            for y in range(3) for x in range(3)])
    failures = []
    if min(ca, cb) < LIMITS["occupancy_min"]:
        failures.append("EMPTY_PRODUCT")
    if not np.any(a[..., 3] == 255) or not np.any(b[..., 3] == 255):
        failures.append("NO_OPAQUE_PIXELS")
    union = int((ma | mb).sum())
    iou = float((ma & mb).sum()) / union if union else 0.0
    if iou < LIMITS["mask_iou_min"] or abs(ca - cb) > LIMITS["coverage_delta_max"]:
        failures.append("SILHOUETTE_MISMATCH")

    def linear(x):
        x = x[..., :3].astype(np.float64) / 255.0
        return np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4)

    delta = np.abs(linear(a) - linear(b))
    mae = float(delta[interior].mean()) if interior.any() else None
    p99 = float(np.percentile(delta[interior], 99)) if interior.any() else None
    if mae is None:
        failures.append("EMPTY_INTERIOR")
    elif mae > LIMITS["linear_rgb_mae_max"] or p99 > LIMITS["linear_rgb_p99_max"]:
        failures.append("RGB_MISMATCH")
    if heatmap:
        visible = ma | mb
        heat = np.maximum(delta.max(axis=2), (ma != mb).astype(float)) * visible
        rgb = np.zeros((*heat.shape, 3), dtype=np.uint8)
        rgb[..., 0] = np.clip(heat * 1020, 0, 255).astype(np.uint8)
        Image.fromarray(rgb).save(heatmap)
    return {"passed": not failures, "failures": failures, "mask_iou": iou,
            "reference_coverage": ca, "candidate_coverage": cb, "coverage_delta": abs(ca - cb),
            "interior_pixels": int(interior.sum()), "linear_rgb_mae": mae, "linear_rgb_p99": p99}


def structure_differences(a, b, path="root"):
    """Exact identities/settings, small absolute tolerance for evaluated geometry."""
    import math
    if isinstance(a, dict) and isinstance(b, dict):
        if a.keys() != b.keys():
            return [path + ": keys differ"]
        return [d for key in a for d in structure_differences(a[key], b[key], path + "." + key)]
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return [path + ": length differs"]
        return [d for i, (x, y) in enumerate(zip(a, b)) for d in structure_differences(x, y, f"{path}[{i}]")]
    if isinstance(a, float) and isinstance(b, (float, int)):
        equal = math.isfinite(a) and math.isfinite(b) and abs(a - b) <= LIMITS["structure_absolute_tolerance"]
    else:
        equal = type(a) is type(b) and a == b
    return [] if equal else [path + ": value differs"]


def snapshot(bpy):
    from mathutils import Vector
    scene = bpy.context.scene
    graph = bpy.context.evaluated_depsgraph_get()
    records = []
    for instance in graph.object_instances:
        obj = instance.object
        if obj.type != "MESH" or obj.hide_render:
            continue
        mesh = obj.to_mesh()
        try:
            points = [instance.matrix_world @ Vector(p) for p in obj.bound_box]
            records.append({"name": obj.original.name, "instance_id": list(instance.persistent_id),
                            "matrix": [list(row) for row in instance.matrix_world],
                            "vertices": len(mesh.vertices), "edges": len(mesh.edges), "polygons": len(mesh.polygons),
                            "bounds": [[min(p[i] for p in points), max(p[i] for p in points)] for i in range(3)],
                            "materials": [slot.material.name if slot.material else None for slot in obj.material_slots],
                            "polygon_materials": hashlib.sha256(json.dumps([p.material_index for p in mesh.polygons]).encode()).hexdigest()})
        finally:
            obj.to_mesh_clear()
    camera = scene.camera
    return {"objects": sorted(records, key=lambda x: (x["name"], x["instance_id"])),
            "materials": sorted(m.name for m in bpy.data.materials),
            "camera": None if camera is None else {"name": camera.name, "matrix": [list(row) for row in camera.matrix_world],
                "lens": camera.data.lens, "sensor_width": camera.data.sensor_width, "type": camera.data.type,
                "clip_start": camera.data.clip_start, "clip_end": camera.data.clip_end,
                "dof": {"enabled": camera.data.dof.use_dof, "distance": camera.data.dof.focus_distance,
                        "fstop": camera.data.dof.aperture_fstop}},
            "lights": [{"name": o.name, "matrix": [list(row) for row in o.matrix_world], "type": o.data.type,
                        "energy": o.data.energy, "color": list(o.data.color)}
                       for o in sorted(scene.objects, key=lambda o: o.name) if o.type == "LIGHT" and not o.hide_render],
            "frame": scene.frame_current, "engine": scene.render.engine,
            "resolution": [scene.render.resolution_x, scene.render.resolution_y, scene.render.resolution_percentage],
            "samples": scene.cycles.samples, "seed": scene.cycles.seed,
            "denoiser": scene.cycles.denoiser, "denoising": scene.cycles.use_denoising,
            "color": {"view": scene.view_settings.view_transform, "look": scene.view_settings.look,
                      "exposure": scene.view_settings.exposure, "gamma": scene.view_settings.gamma}}


def blender_probe(mode):
    import bpy
    from bpy.app.handlers import persistent
    import prepare_scene

    output = Path("/output")
    report = {"status": "blocked", "mode": mode, "runtime": {"version": bpy.app.version_string,
              "build": bpy.app.build_hash.decode()}, "blockers": [], "source_paths_inaccessible": False}
    try:
        if (bpy.app.version_string, bpy.app.build_hash.decode()) != (VERSION, BUILD):
            raise ValueError("RUNTIME_MISMATCH")
        # No source mounts, host home, or network namespace shared with the parent.
        if any(Path(p).exists() for p in ("/mnt/c", "/home/markimus", "/run/host", "/input/cad")):
            raise ValueError("ISOLATION_FAILED")
        report["source_paths_inaccessible"] = True
        payload = Path("/input/prepared.blend")
        declared = json.loads(Path("/input/inputs.json").read_text())
        for name, expected in declared.items():
            if digest(Path("/input") / name) != expected:
                raise ValueError("HASH_MISMATCH: " + name)
        bpy.ops.wm.open_mainfile(filepath=str(payload), load_ui=False, use_scripts=False)
        audit = prepare_scene.new_report(payload)
        prepare_scene.audit(bpy, audit)
        report["dependency_audit"] = {key: audit[key] for key in
                                     ("blockers", "dependencies", "remaining_external_paths", "sanitized_metadata", "scene_summary")}
        if audit["blockers"] or audit["remaining_external_paths"] or audit["sanitized_metadata"]:
            raise ValueError("PREPARED_DEPENDENCY_AUDIT_FAILED")
        save(output / "reopened-structure.json", snapshot(bpy))
        manifest = json.loads(Path("/input/manifest.json").read_text())
        if mode == "missing_texture":
            manifest["lighting"]["hdri_path"] = "/input/missing-environment.png"
        if not Path(manifest["lighting"]["hdri_path"]).is_file():
            raise ValueError("MISSING_DEPENDENCY: world_environment")
        import render_worker

        @persistent
        def before_render(scene, *_):
            scene.frame_set(1)
            scene.render.resolution_percentage = 100
            scene.render.image_settings.color_depth = "8"
            scene.render.threads_mode = "FIXED"
            scene.render.threads = 8
            scene.cycles.seed = 0
            scene.cycles.use_animated_seed = False
            scene.cycles.device = "CPU"
            scene.cycles.use_denoising = True
            scene.cycles.denoiser = "OPENIMAGEDENOISE"
            if mode == "camera_shift":
                scene.camera.location.x += 0.5
            if mode == "material_change":
                for material in bpy.data.materials:
                    if material.use_nodes:
                        for node in material.node_tree.nodes:
                            if node.type == "BSDF_PRINCIPLED":
                                node.inputs["Base Color"].default_value = (0.8, 0.01, 0.7, 1.0)
            bpy.context.view_layer.update()
            save(output / "render-structure.json", snapshot(bpy))

        bpy.app.handlers.render_pre.append(before_render)
        render_worker.execute_render_job(manifest)
        if not (output / "beauty.png").is_file() or not (output / "mask.png").is_file():
            raise ValueError("MISSING_OUTPUT")
        report["status"] = "rendered"
        report["device_policy"] = "CPU reference; no GPU execution claim"
    except Exception as exc:
        report["blockers"].append(f"{type(exc).__name__}: {exc}")
    save(output / "probe-report.json", report)
    return 0 if report["status"] == "rendered" else 1


def linux_path(path, distro):
    if sys.platform != "win32":
        return str(Path(path).resolve())
    return subprocess.check_output(["wsl.exe", "-d", distro, "--exec", "wslpath", "-a", str(Path(path).resolve())], text=True).strip()


def isolation_command(runtime, payload, output, mode, distro):
    command = ["bwrap", "--unshare-all", "--die-with-parent", "--new-session", "--clearenv",
               "--ro-bind", "/usr", "/usr", "--symlink", "usr/bin", "/bin",
               "--symlink", "usr/lib", "/lib", "--symlink", "usr/lib64", "/lib64",
               "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp", "--dir", "/home",
               "--ro-bind", runtime, "/blender", "--ro-bind", payload, "/input",
               "--bind", output, "/output", "--setenv", "HOME", "/tmp",
               "--setenv", "PATH", "/usr/bin:/blender", "--setenv", "PYTHONPATH", "/input",
               "--chdir", "/output", "--", "/blender/blender", "--background", "--factory-startup",
               "--disable-autoexec", "--python-exit-code", "20", "--python", "/input/verify_scene.py",
               "--", "--_probe", mode]
    return ["wsl.exe", "-d", distro, "--exec", *command] if sys.platform == "win32" else command


def run_proof(args):
    output = Path(args.output_dir).resolve()
    output.mkdir(parents=True, exist_ok=False)
    save(output / "scene-parity-report.json", {"schema_version": 1, "status": "blocked", "owner_accepted": False,
         "g0_passed": False, "cloud_authorized": False, "failures": ["VERIFICATION_INCOMPLETE"]})
    preparation = json.loads(Path(args.preparation_report).read_text(encoding="utf-8"))
    if preparation["status"] != "prepared" or preparation["blockers"] or preparation["remaining_external_paths"]:
        raise ValueError("Preparation report is not successful")
    source, prepared = Path(preparation["source"]["path"]), Path(preparation["prepared"]["path"])
    archive = args.linux_runtime.rstrip("/") + ".tar.xz"
    checksum_command = ["sha256sum", archive]
    if sys.platform == "win32":
        checksum_command = ["wsl.exe", "-d", args.distro, "--exec", *checksum_command]
    actual_archive = subprocess.check_output(checksum_command, text=True, timeout=60).split()[0]
    if actual_archive != ARCHIVE_SHA256:
        raise ValueError("RUNTIME_ARCHIVE_HASH_MISMATCH")
    for path, expected in [(source, preparation["source"]["sha256"]), (prepared, preparation["prepared"]["sha256"])]:
        if digest(path) != expected:
            raise ValueError("HASH_MISMATCH: " + str(path))
    from msp_render_cli.cli import find_blender
    local_blender = find_blender() if sys.platform == "win32" else str(Path(args.linux_runtime) / "blender")
    command = [local_blender, "--background", "--factory-startup", "--disable-autoexec", "--python-exit-code", "20",
               "--python", str(Path(__file__).resolve()), "--", "--_source-snapshot", str(source), str(output / "source-structure.json")]
    with (output / "source-snapshot.log").open("w", encoding="utf-8") as log:
        subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=120, check=True)
    manifest = json.loads((ROOT / "jobs/rl300_02_studio-dark.json").read_text())
    environment = ROOT / manifest["lighting"]["hdri_path"]
    payload = output / "payload"
    payload.mkdir()
    for src, name in [(prepared, "prepared.blend"), (environment, "environment.png"),
                      (ROOT / "scripts/prepare_scene.py", "prepare_scene.py"),
                      (Path(__file__), "verify_scene.py"), (ROOT / "render_worker.py", "render_worker.py")]:
        shutil.copyfile(src, payload / name)
    manifest["cad_source"]["file_path"] = "/input/prepared.blend"
    manifest["lighting"]["hdri_path"] = "/input/environment.png"
    manifest["compositing"]["background_plate"] = "/input/environment.png"
    manifest["output"].update(width=900, height=625, samples=48, output_dir="/output")
    manifest["output"]["passes"] = {"beauty": True, "alpha_mask": True}
    save(payload / "manifest.json", manifest)
    inputs = {p.name: digest(p) for p in sorted(payload.iterdir())}
    save(payload / "inputs.json", inputs)
    modes = ("reference", "repeat", "camera_shift", "material_change", "missing_texture")
    runs = {}
    for mode in modes:
        dest = output / mode
        dest.mkdir()
        command = isolation_command(args.linux_runtime, linux_path(payload, args.distro), linux_path(dest, args.distro), mode, args.distro)
        # Bound Linux execution even if a killed Windows WSL client leaves its
        # guest process alive. bwrap also dies with its Linux supervisor.
        prefix = command[:4] if sys.platform == "win32" else []
        command = prefix + ["timeout", "--signal=TERM", "--kill-after=5", str(args.timeout)] + command[len(prefix):]
        started = time.monotonic()
        with (dest / "blender.log").open("w", encoding="utf-8") as log:
            try:
                result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=args.timeout + 30)
                exit_code = result.returncode
            except subprocess.TimeoutExpired:
                exit_code = -1
        report_path = dest / "probe-report.json"
        report = json.loads(report_path.read_text()) if report_path.exists() else {"status": "blocked", "blockers": ["PROBE_FAILED_OR_TIMEOUT"]}
        runs[mode] = {"exit_code": exit_code, "seconds": round(time.monotonic() - started, 3), "report": report}
        save(output / "progress.json", runs)
        print(json.dumps({"mode": mode, "status": report["status"], "seconds": runs[mode]["seconds"]}), flush=True)
        if mode in ("reference", "repeat") and (exit_code or report["status"] != "rendered"):
            break
    return summarize(output, runs, inputs, preparation, manifest)


def summarize(output, runs, inputs, preparation, manifest):
    failures, comparisons = [], {}
    if any(mode not in runs for mode in ("reference", "repeat", "camera_shift", "material_change", "missing_texture")):
        failures.append("INCOMPLETE_RUNS")
    if (output / "reference/reopened-structure.json").exists():
        source_structure = json.loads((output / "source-structure.json").read_text())
        reopened = json.loads((output / "reference/reopened-structure.json").read_text())
        differences = structure_differences(source_structure, reopened)
        comparisons["source_to_prepared"] = {"structural_differences": differences}
        if differences:
            failures.append("SOURCE_STRUCTURE_MISMATCH")
    if "repeat" in runs and runs["repeat"]["report"]["status"] == "rendered":
        for mode in ("repeat", "camera_shift", "material_change"):
            dest = output / mode
            if mode not in runs or runs[mode]["exit_code"] or runs[mode]["report"]["status"] != "rendered":
                failures.append(mode + ": RENDER_FAILED")
                continue
            metrics = image_metrics(output / "reference/beauty.png", dest / "beauty.png", dest / "heatmap.png")
            a = json.loads((output / "reference/render-structure.json").read_text())
            b = json.loads((dest / "render-structure.json").read_text())
            diffs = structure_differences(a, b)
            comparisons[mode] = {"image": metrics, "structural_differences": diffs}
            if mode == "repeat" and (not metrics["passed"] or diffs):
                failures.append("GOOD_REPEAT_FAILED")
            if mode != "repeat" and metrics["passed"]:
                failures.append(mode + ": NEGATIVE_IMAGE_PASSED")
        missing = runs.get("missing_texture", {})
        if missing.get("exit_code") == 0 or not any("MISSING_DEPENDENCY" in x for x in missing.get("report", {}).get("blockers", [])):
            failures.append("MISSING_TEXTURE_CONTROL_FAILED")
    if digest(Path(preparation["source"]["path"])) != preparation["source"]["sha256"]:
        failures.append("SOURCE_CHANGED")
    if digest(Path(preparation["prepared"]["path"])) != preparation["prepared"]["sha256"]:
        failures.append("PREPARED_CHANGED")
    if (output / "reference/beauty.png").exists():
        from composite_worker import MSPCompositor
        settings = {k: v for k, v in manifest["compositing"].items() if k not in ("enabled", "background_plate")}
        MSPCompositor.composite_asset(str(output / "reference/beauty.png"), str(output / "payload/environment.png"),
                                      str(output / "reference/composite.png"), **settings)
        # Check the saved product pixels, independently of the legacy compositor
        # in-memory gate (the renderer/compositor implementation remains T04/T05).
        import numpy as np
        from PIL import Image
        with Image.open(output / "reference/beauty.png") as im:
            product = im.convert("RGBA")
        offset = manifest["compositing"].get("product_offset_pct", [0, 0])
        placed = Image.new("RGBA", product.size)
        placed.paste(product, tuple(int(round(offset[i] * product.size[i])) for i in range(2)))
        pixels = np.asarray(placed)
        opaque = pixels[..., 3] == 255
        with Image.open(output / "reference/composite.png") as im:
            composite = np.asarray(im.convert("RGB"))
        if not opaque.any() or not np.array_equal(pixels[..., :3][opaque], composite[opaque]):
            failures.append("SAVED_COMPOSITE_FIDELITY_FAILED")
        for mode in ("reference", "repeat", "camera_shift", "material_change"):
            try:
                with Image.open(output / mode / "beauty.png") as im:
                    alpha = np.asarray(im.convert("RGBA"))[..., 3]
                with Image.open(output / mode / "mask.png") as im:
                    mask = np.asarray(im.convert("L"))
                if mask.shape != alpha.shape or np.abs(mask.astype(int) - alpha.astype(int)).max() > 1:
                    failures.append(mode + ": MASK_ALPHA_MISMATCH")
            except (OSError, ValueError):
                failures.append(mode + ": INVALID_MASK")
    profile = {"schema_version": 1, "status": "proposed_pending_owner", "limits": LIMITS,
               "encoding": "8-bit PNG, sRGB transfer inverse on AgX display-referred RGB; not scene-linear radiance",
               "fixed_settings": manifest["output"], "seed": 0, "frame": 1, "device": "CPU",
               "reference_sha256": digest(output / "reference/beauty.png") if (output / "reference/beauty.png").exists() else None}
    save(output / "scene-parity-profile.json", profile)
    inventory = [{"path": p.relative_to(output).as_posix(), "sha256": digest(p), "size_bytes": p.stat().st_size}
                 for p in sorted(output.rglob("*")) if p.is_file() and p.name != "scene-parity-report.json"]
    report = {"schema_version": 1, "status": "blocked" if failures else "awaiting_reference_acceptance",
              "owner_accepted": False, "g0_passed": False, "cloud_authorized": False,
              "inputs": inputs, "runtime": {"version": VERSION, "build": BUILD, "archive_sha256": ARCHIVE_SHA256},
              "source_sha256": preparation["source"]["sha256"], "prepared_sha256": preparation["prepared"]["sha256"],
              "failures": failures, "runs": runs, "comparisons": comparisons, "artifacts": inventory}
    from jsonschema import Draft202012Validator
    schema = json.loads((ROOT / "docs/scene_parity.schema.json").read_text())
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(report)
    save(output / "scene-parity-report.json", report)
    return 1 if failures else 0


def main():
    arguments = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    if arguments[:1] == ["--_probe"]:
        return blender_probe(arguments[1])
    if arguments[:1] == ["--_source-snapshot"]:
        import bpy
        if (bpy.app.version_string, bpy.app.build_hash.decode()) != (VERSION, BUILD):
            raise ValueError("RUNTIME_MISMATCH")
        bpy.ops.wm.open_mainfile(filepath=arguments[1], load_ui=False, use_scripts=False)
        save(arguments[2], snapshot(bpy))
        return 0
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preparation-report", required=True)
    parser.add_argument("--linux-runtime", required=True, help="Absolute Linux directory containing the checksum-verified Blender build")
    parser.add_argument("--output-dir", required=True, help="New evidence directory")
    parser.add_argument("--distro", default="Ubuntu")
    parser.add_argument("--timeout", type=float, default=600)
    args = parser.parse_args(arguments)
    import math
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error("Timeout must be finite and positive")
    try:
        return run_proof(args)
    except Exception as exc:
        print(f"Verification failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

"""Run the frozen scene probe on a required NVIDIA GPU inside Blender.

Invoke with Blender's --python-exit-code 1 and --python this_file, optionally
followed by -- --force-no-gpu. /input is the untouched accepted payload.
The frozen probe report retains its CPU policy wording; compute-evidence.json
is the separate authority for the observed compute configuration.
"""

import argparse
import json
from pathlib import Path
import sys
import time


def validate_gpu_inventory(inventory, backend):
    """Require at least one enabled NVIDIA device and no enabled CPU/other GPU."""
    enabled = [device for device in inventory if device["enabled"]]
    if (backend not in ("OPTIX", "CUDA") or not enabled
            or any(device["type"] != backend for device in enabled)):
        raise RuntimeError("GPU_REQUIRED: no exclusively enabled NVIDIA GPU devices")
    return enabled


def main(argv=None):
    if argv is None:
        argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force-no-gpu", action="store_true")
    args = parser.parse_args(argv)
    # This control can follow a successful run in the same container. Preserve
    # every successful /output artifact and avoid importing Blender/the payload.
    if args.force_no_gpu:
        try:
            validate_gpu_inventory([], "OPTIX")
        except RuntimeError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        return 0
    output = Path("/output")
    output.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    evidence = {
        "schema_version": "1.0",
        "status": "blocked",
        "required_device": "NVIDIA GPU; OPTIX preferred, CUDA fallback; CPU disabled",
        "device_policy_note": (
            "For this harness only, these observations override the frozen "
            "probe-report.json CPU device_policy wording; frozen code is unchanged."
        ),
        "force_no_gpu": args.force_no_gpu,
        "runtime": {},
        "backend": None,
        "enabled_devices": [],
        "pre_render_observations": [],
        "handler_errors": [],
        "blockers": [],
        "render_completed": False,
        "phase_seconds": {},
    }

    def save():
        evidence["phase_seconds"]["total"] = round(time.monotonic() - started, 6)
        (output / "compute-evidence.json").write_text(
            json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    handler = None
    worker = None
    original_execute = None
    try:
        import bpy
        from bpy.app.handlers import persistent

        evidence["runtime"] = {
            "version": bpy.app.version_string,
            "build": bpy.app.build_hash.decode(),
        }
        sys.path.insert(0, "/input")
        import verify_scene
        import render_worker as worker

        for module in (verify_scene, worker):
            if Path(module.__file__).resolve().parent != Path("/input"):
                raise RuntimeError("FROZEN_MODULE_REQUIRED: " + module.__name__)

        prefs = bpy.context.preferences.addons["cycles"].preferences

        def devices():
            return [{"name": d.name, "id": d.id, "type": d.type,
                     "enabled": bool(d.use)} for d in prefs.devices]

        def require_gpu(select=False):
            attempts = []
            backends = ("OPTIX", "CUDA") if select else (evidence["backend"],)
            for backend in backends:
                try:
                    prefs.compute_device_type = backend
                    prefs.get_devices()
                    for device in prefs.devices:
                        device.use = device.type == backend
                    enabled = validate_gpu_inventory(devices(), backend)
                    evidence["backend"] = backend
                    evidence["enabled_devices"] = enabled
                    return enabled
                except Exception as exc:
                    attempts.append(f"{backend}: {exc}")
            raise RuntimeError("GPU_REQUIRED: " + "; ".join(attempts))

        # Blender swallows render_pre exceptions: prove availability synchronously
        # before entering the frozen code, then check handler evidence afterwards.
        require_gpu(select=True)
        evidence["phase_seconds"]["gpu_discovery"] = round(time.monotonic() - started, 6)

        @persistent
        def enforce_gpu(scene, *_):
            try:
                enabled = require_gpu()
                scene.cycles.device = "GPU"
                if scene.render.engine != "CYCLES" or scene.cycles.device != "GPU":
                    raise RuntimeError("GPU_REQUIRED: Cycles GPU setting did not persist")
                observation = {
                    "engine": scene.render.engine,
                    "device": scene.cycles.device,
                    "backend": prefs.compute_device_type,
                    "enabled_devices": enabled,
                    "all_devices": devices(),
                    "frame": scene.frame_current,
                    "width": scene.render.resolution_x,
                    "height": scene.render.resolution_y,
                    "resolution_percentage": scene.render.resolution_percentage,
                    "samples": scene.cycles.samples,
                    "seed": scene.cycles.seed,
                    "use_animated_seed": scene.cycles.use_animated_seed,
                    "use_denoising": scene.cycles.use_denoising,
                    "denoiser": scene.cycles.denoiser,
                    "color_depth": scene.render.image_settings.color_depth,
                    "color_mode": scene.render.image_settings.color_mode,
                    "file_format": scene.render.image_settings.file_format,
                    "film_transparent": scene.render.film_transparent,
                    "view_transform": scene.view_settings.view_transform,
                    "look": scene.view_settings.look,
                    "exposure": scene.view_settings.exposure,
                    "gamma": scene.view_settings.gamma,
                }
                evidence["pre_render_observations"].append(observation)
                save()
            except Exception as exc:
                evidence["handler_errors"].append(f"{type(exc).__name__}: {exc}")
                save()
                raise

        handler = enforce_gpu
        original_execute = worker.execute_render_job

        def execute_with_gpu(manifest):
            require_gpu()
            # Appended only after blender_probe installs its frozen CPU handler.
            # Both survive the renderer's second open_mainfile call.
            bpy.app.handlers.render_pre.append(handler)
            render_started = time.monotonic()
            try:
                result = original_execute(manifest)
                evidence["phase_seconds"]["render_job"] = round(
                    time.monotonic() - render_started, 6
                )
                if evidence["handler_errors"] or not evidence["pre_render_observations"]:
                    raise RuntimeError("GPU_EVIDENCE_FAILED: render_pre did not succeed")
                validate_gpu_inventory(devices(), evidence["backend"])
                if bpy.context.scene.cycles.device != "GPU":
                    raise RuntimeError("GPU_EVIDENCE_FAILED: compute settings changed")
                evidence["render_completed"] = True
                return result
            finally:
                if handler in bpy.app.handlers.render_pre:
                    bpy.app.handlers.render_pre.remove(handler)

        worker.execute_render_job = execute_with_gpu
        probe_result = verify_scene.blender_probe("reference")
        evidence["probe_exit_code"] = probe_result
        if probe_result != 0 or not evidence["render_completed"]:
            raise RuntimeError("FROZEN_PROBE_FAILED: see probe-report.json")
        if evidence["handler_errors"]:
            raise RuntimeError("GPU_EVIDENCE_FAILED: render handler error")
        evidence["status"] = "rendered"
        return 0
    except Exception as exc:
        evidence["blockers"].append(f"{type(exc).__name__}: {exc}")
        print(evidence["blockers"][-1], file=sys.stderr)
        return 1
    finally:
        if worker is not None and original_execute is not None:
            worker.execute_render_job = original_execute
        save()


if __name__ == "__main__":
    sys.exit(main())

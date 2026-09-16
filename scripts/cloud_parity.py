"""Bounded Modal proof of an accepted frozen T03 payload; not production dispatch.

Run locally with --reference-dir and --output-dir. --execute permits a live call.
The frozen verifier supplies runtime pins, metrics and thresholds unchanged.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import time
import uuid

from msp_render_cli.remote_job import MIN_SOLO_GPU_MIB, gpu_process_evidence

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ("beauty.png", "mask.png", "reopened-structure.json", "render-structure.json",
             "probe-report.json", "compute-evidence.json", "blender.log")
def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def save(path, data):
    Path(path).write_text(json.dumps(data, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def load_verifier(reference):
    spec = importlib.util.spec_from_file_location("frozen_parity", reference / "payload/verify_scene.py")
    module = importlib.util.module_from_spec(spec)
    old = sys.dont_write_bytecode
    try:
        sys.dont_write_bytecode = True
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = old
    return module


def preflight(reference):
    reference = Path(reference).resolve()
    report = json.loads((reference / "scene-parity-report.json").read_text())
    profile = json.loads((reference / "scene-parity-profile.json").read_text())
    declared = json.loads((reference / "payload/inputs.json").read_text())
    if declared != report["inputs"]:
        raise ValueError("INPUT_INVENTORY_MISMATCH")
    if {p.name for p in (reference / "payload").iterdir()} != set(declared) | {"inputs.json"}:
        raise ValueError("UNDECLARED_PAYLOAD_FILE")
    for name, expected in declared.items():
        if Path(name).name != name or name in (".", "..") or "/" in name or "\\" in name:
            raise ValueError("UNSAFE_INPUT_NAME")
        if sha(reference / "payload" / name) != expected:
            raise ValueError("INPUT_HASH_MISMATCH: " + name)
    if sha(reference / "payload/prepared.blend") != report["prepared_sha256"]:
        raise ValueError("PREPARED_HASH_MISMATCH")
    verifier = load_verifier(reference)
    runtime = report["runtime"]
    if runtime != {"version": verifier.VERSION, "build": verifier.BUILD, "archive_sha256": verifier.ARCHIVE_SHA256}:
        raise ValueError("RUNTIME_PIN_MISMATCH")
    if profile["limits"] != verifier.LIMITS:
        raise ValueError("FROZEN_LIMITS_MISMATCH")
    if "reference_composite_pixels_sha256" not in profile:
        # The profile carries the composite digest only for composited runs
        # (verify_scene writes it iff compositing is enabled; older frozen
        # profiles predate the explicit compositing flag but honor the same
        # rule), and compare() needs reference/composite.png. Refuse such a
        # reference up front instead of failing on the missing file mid-digest.
        raise ValueError("COMPOSITING_DISABLED")
    for name, field in (("beauty", "reference_pixels_sha256"), ("mask", "reference_mask_pixels_sha256"),
                        ("composite", "reference_composite_pixels_sha256")):
        if verifier.pixel_digest(reference / "reference" / (name + ".png")) != profile[field]:
            raise ValueError("REFERENCE_PIXELS_MISMATCH: " + name)
    return report, profile


def cloud_worker(request):
    """Explicit outputs only; input payload is mounted separately at /input."""
    import os
    import threading
    output = Path("/output")
    output.mkdir(exist_ok=False)
    started = time.monotonic()
    result = {"schema_version": 1, "request_id": request["request_id"], "attempt_id": request["attempt_id"],
              "runtime": request["runtime"], "status": "failed", "failures": [], "artifacts": {},
              "gpu_process_samples": [], "provider_call_id": os.environ.get("MODAL_FUNCTION_CALL_ID")}
    stop = threading.Event()

    def monitor():
        while not stop.is_set():
            try:
                probe = subprocess.run(["nvidia-smi", "--query-compute-apps=pid,process_name,used_gpu_memory",
                                        "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=5)
                if probe.returncode == 0 and probe.stdout.strip():
                    result["gpu_process_samples"].append({"seconds": round(time.monotonic()-started, 3),
                                                          "processes": probe.stdout.strip()})
            except (OSError, subprocess.TimeoutExpired):
                pass
            stop.wait(1)

    thread = threading.Thread(target=monitor, daemon=True)
    thread.start()
    command = ["/opt/blender/blender", "--background", "--factory-startup", "--disable-autoexec",
               "--python-exit-code", "20", "--python", "/harness/cloud_blender_probe.py", "--"]
    try:
        with (output / "blender.log").open("w") as log:
            run = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=1080)
        result["blender_exit_code"] = run.returncode
        missing = [name for name in ARTIFACTS if not (output / name).is_file()]
        if run.returncode or missing:
            result["failures"].append("BLENDER_FAILED_OR_MISSING_OUTPUT: " + str(missing))
        else:
            compute = json.loads((output / "compute-evidence.json").read_text())
            result["compute"] = compute
            if (compute.get("status") != "rendered" or not compute.get("render_completed")
                    or compute.get("handler_errors") or compute.get("blockers")
                    or compute.get("backend") not in ("OPTIX", "CUDA")
                    or not compute.get("pre_render_observations")
                    or compute.get("runtime") != {k: request["runtime"][k] for k in ("version", "build")}):
                result["failures"].append("INVALID_COMPUTE_EVIDENCE")
            else:
                result["status"] = "rendered"
        # A required-GPU negative control runs in a fresh Blender process.
        negative = output / "negative"
        negative.mkdir()
        with (negative / "blender.log").open("w") as log:
            run = subprocess.run(command + ["--force-no-gpu"], stdout=log, stderr=subprocess.STDOUT, timeout=60)
        negative_log = (negative / "blender.log").read_text()
        result["gpu_required_negative"] = {"exit_code": run.returncode,
            "passed": run.returncode != 0 and "GPU_REQUIRED" in negative_log}
        if not result["gpu_required_negative"]["passed"]:
            result["failures"].append("GPU_REQUIRED_NEGATIVE_FAILED")
    except Exception as exc:
        result["failures"].append(type(exc).__name__ + ": " + str(exc))
    finally:
        stop.set()
        thread.join(timeout=7)
    result["seconds"] = round(time.monotonic() - started, 3)
    result["blender_gpu_process_seen"] = gpu_process_evidence(result["gpu_process_samples"])
    if not result["blender_gpu_process_seen"]:
        result["failures"].append("NO_BLENDER_GPU_PROCESS_EVIDENCE")
    if result["failures"]:
        result["status"] = "failed"
    files = {}
    for name in (*ARTIFACTS, "negative/blender.log"):
        path = output / name
        if path.is_file():
            files[name] = path.read_bytes()
            result["artifacts"][name] = {"sha256": sha(path), "size_bytes": path.stat().st_size}
    return result, files


def compare(reference, output):
    verifier = load_verifier(reference)
    candidate = output / "cloud"
    metrics = verifier.image_metrics(reference / "reference/beauty.png", candidate / "beauty.png",
        output / "heatmap.png", reference_mask=reference / "reference/mask.png", candidate_mask=candidate / "mask.png")
    diffs = {}
    for name in ("reopened-structure.json", "render-structure.json"):
        diffs[name] = verifier.structure_differences(json.loads((reference / "reference" / name).read_text()),
                                                    json.loads((candidate / name).read_text()))
    # Use the same compositor as T03, locally, with the exact frozen manifest settings.
    sys.path.insert(0, str(ROOT))
    from composite_worker import MSPCompositor
    manifest = json.loads((reference / "payload/manifest.json").read_text())
    settings = {k: v for k, v in manifest["compositing"].items() if k not in ("enabled", "background_plate")}
    MSPCompositor.composite_asset(str(candidate / "beauty.png"), str(reference / "payload/environment.png"),
                                  str(candidate / "composite.png"), **settings)
    pixels = {name: {"reference": verifier.pixel_digest(reference / "reference" / (name+".png")),
                     "candidate": verifier.pixel_digest(candidate / (name+".png"))}
              for name in ("beauty", "mask", "composite")}
    return {"image": metrics, "structural_differences": diffs, "pixel_digests": pixels,
            "composite_execution": "local", "passed": metrics["passed"] and not any(diffs.values())}


def main():
    # Modal's progress renderer emits Unicode even when PowerShell redirects it.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    reference, output = args.reference_dir.resolve(), args.output_dir.resolve()
    report, profile = preflight(reference)
    output.mkdir(parents=True, exist_ok=False)
    runtime = report["runtime"]
    request = {"schema_version": 1, "request_id": str(uuid.uuid4()), "attempt_id": str(uuid.uuid4()),
        "runtime": runtime, "source_sha256": report["source_sha256"], "prepared_sha256": report["prepared_sha256"],
        "reference_composite_sha256": sha(reference / "reference/composite.png"), "inputs": report["inputs"],
        "resources": {"gpu": "L4", "cpu": 4, "memory_mib": 16384, "timeout_seconds": 1200,
                      "max_containers": 1, "application_retries": 0},
        "harness_sha256": sha(Path(__file__)), "probe_sha256": sha(ROOT / "scripts/cloud_blender_probe.py")}
    save(output / "request.json", request)
    save(output / "reference-profile.json", profile)
    if not args.execute:
        print("Preflight passed; no cloud call. " + str(output))
        return 0
    import modal
    version = runtime["version"]
    archive = f"blender-{version}-linux-x64.tar.xz"
    url = f"https://download.blender.org/release/Blender{'.'.join(version.split('.')[:2])}/{archive}"
    image = (modal.Image.debian_slim(python_version=f"{sys.version_info.major}.{sys.version_info.minor}")
        .apt_install("wget", "xz-utils", "libglu1-mesa", "libxi6", "libxrender1", "libxfixes3",
                     "libxcursor1", "libxinerama1", "libxkbcommon0", "libsm6", "libxxf86vm1", "libgl1")
        .run_commands(f"wget --timeout=60 --tries=2 -q {url} -O /tmp/blender.tar.xz",
                      f"echo '{runtime['archive_sha256']}  /tmp/blender.tar.xz' | sha256sum -c -",
                      "mkdir /opt/blender && tar -xf /tmp/blender.tar.xz -C /opt/blender --strip-components=1",
                      "rm /tmp/blender.tar.xz")
        .add_local_file(ROOT / "scripts/cloud_blender_probe.py", "/harness/cloud_blender_probe.py"))
    for name in sorted(set(report["inputs"]) | {"inputs.json"}):
        image = image.add_local_file(reference / "payload" / name, "/input/" + name)
    app = modal.App("studiomark-v12-cloud-parity")
    worker = app.function(image=image, gpu="L4", cpu=4, memory=16384, timeout=1200, startup_timeout=300,
                          max_containers=1, retries=0, scaledown_window=2, serialized=True)(cloud_worker)
    started = time.monotonic()
    save(output / "status.json", {"status": "submitting", "request_id": request["request_id"]})
    try:
        with modal.enable_output(), app.run():
            result, files = worker.remote(request)
        if (result["request_id"], result["attempt_id"]) != (request["request_id"], request["attempt_id"]):
            raise ValueError("RESULT_IDENTITY_MISMATCH")
        save(output / "result.json", result)
        for name, content in files.items():
            if name not in (*ARTIFACTS, "negative/blender.log"):
                raise ValueError("UNEXPECTED_OUTPUT")
            if hashlib.sha256(content).hexdigest() != result["artifacts"][name]["sha256"]:
                raise ValueError("OUTPUT_HASH_MISMATCH")
            destination = output / "cloud" / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)
        comparison = compare(reference, output) if result["status"] == "rendered" else {"passed": False}
        save(output / "comparison.json", comparison)
        status = "passed" if result["status"] == "rendered" and comparison["passed"] else "failed"
        save(output / "status.json", {"status": status, "wall_seconds": round(time.monotonic()-started, 3),
                                       "request_id": request["request_id"]})
        print(json.dumps({"status": status, "output": str(output), "image": comparison.get("image")}))
        return 0 if status == "passed" else 1
    except Exception as exc:
        save(output / "status.json", {"status": "failed_or_submission_unknown", "error": str(exc),
                                       "request_id": request["request_id"]})
        raise


if __name__ == "__main__":
    raise SystemExit(main())

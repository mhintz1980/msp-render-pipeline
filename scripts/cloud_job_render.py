"""Dispatch single frames of a job manifest to Modal; the first T-V2 cloud piece.

Per Mark's 2026-09-20 ruling (docs/cloud-smoke.md, "2026-09-20 authorization")
all render work - video frames and previews alike - runs on Modal; the local
workstation no longer renders. This script renders one azimuth of an existing
job manifest per call, downloads the artifacts, and composites locally through
the same MSPCompositor the stills pipeline uses.

What this is not: it is not the v12 parity proof (scripts/cloud_parity.py
owns that), it makes no frozen-payload or reference-acceptance claim, and it
does not dispatch sequences - T-V2's sequencer will grow from it.

One Blender process per frame is deliberate (video-pipeline-brief.md section
6.1): a 4.5% GPU-driver crash rate makes per-frame process isolation with
resumability mandatory, and section 3.1 measured the per-process overhead at
0.38 s, so nothing is lost. Frames are sequential remote calls so a failure
in one frame cannot cost the others.

Runtime pins mirror scripts/verify_scene.py (VERSION/BUILD/ARCHIVE_SHA256);
a unit test asserts the match so the pin cannot drift silently.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
import uuid

# Direct invocation (`python scripts/cloud_job_render.py`) puts scripts/, not
# the repo root, on sys.path; msp_render_cli is imported locally in main().
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Must match scripts/verify_scene.py lines 21-23 (asserted by
# tests/test_cloud_job_render.py). Same archive the v12 cloud proof pinned.
BLENDER_VERSION = "5.1.1"
BLENDER_BUILD = "b70da489d7f4"
BLENDER_ARCHIVE_SHA256 = "6f9fff89fef154ef7974d1a1c4b916ab4bc1f5618bcb48d5befee1bd0a7c7f2a"

# docs/cloud-smoke.md "Execution bounds"; all-in per second at 4 cores, 16 GiB.
GPU_RATE_PER_S = 0.000222
CPU_RATE_PER_CORE_S = 0.0000131
MEMORY_RATE_PER_GIB_S = 0.00000222
COLD_START_SECONDS = 229.0  # measured fixed cost of the recorded L4 cold run

FRAME_PREFIX = "frame-"  # frame_name() already carries the "az"; joined: frame-az42


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def save(path, data):
    Path(path).write_text(json.dumps(data, indent=2, sort_keys=True, allow_nan=False) + "\n",
                          encoding="utf-8")


def frame_name(azimuth_deg):
    return f"az{int(round(azimuth_deg))}"


def frame_manifest(manifest, azimuth_deg, container_output_dir):
    """One frame's manifest: a copy of the job with the azimuth overridden.

    Paths are rewritten to their container locations so
    render_worker.resolve_manifest_paths passes absolute paths through
    unchanged; require_gpu is forced so the worker must land on a GPU and
    writes the T04 render report (whose bytes-build_hash fix landed 2026-09-17).
    """
    frame = json.loads(json.dumps(manifest))
    frame["camera"]["azimuth_deg"] = float(azimuth_deg)
    frame["require_gpu"] = True
    frame["output"]["output_dir"] = container_output_dir
    frame["job_id"] = f"{manifest['job_id']}-{frame_name(azimuth_deg)}"
    cad = Path(manifest["cad_source"]["file_path"])
    frame["cad_source"]["file_path"] = f"/input/cad/{cad.name}"
    hdri = manifest.get("lighting", {}).get("hdri_path")
    if hdri:
        frame["lighting"]["hdri_path"] = f"/input/backgrounds/{Path(hdri).name}"
    return frame


def orbit_azimuths(count: int, start: float = 42.0) -> list[float]:
    """`count` unique azimuths, one full orbit, no repeat of the start frame."""
    if count < 2:
        raise ValueError(f"BAD_ORBIT_COUNT: {count} (must be >= 2)")
    step = 360.0 / count
    # range(count), never count + 1: the wrap-around frame is the start frame.
    return [round(start + i * step, 3) for i in range(count)]


def reject_duplicate_azimuths(azimuths) -> None:
    """Raise on any azimuth repeated modulo 360 - a duplicate billable frame."""
    seen_mod, seen_labels = {}, {}
    for azimuth in azimuths:
        # The frame label is the billing unit (frame dir, job_id, output dir),
        # so two azimuths that name the same frame are one frame however
        # different the floats look.
        key = frame_name(azimuth)
        first = seen_labels.get(key, seen_mod.get(round(azimuth % 360.0, 3)))
        if first is not None:
            raise ValueError(f"DUPLICATE_AZIMUTH: {azimuth} repeats {first} modulo 360")
        seen_labels[key] = azimuth
        seen_mod[round(azimuth % 360.0, 3)] = azimuth
    return None


def apply_overrides(manifest, overrides):
    """Apply dotted-path=value overrides in place; unknown paths are errors.

    Values parse as JSON when they can (numbers, booleans) and stay strings
    otherwise (paths). A typo'd path must fail before a billable call, not
    silently render the unmodified job.
    """
    for override in overrides or []:
        path, sep, raw = override.partition("=")
        if not sep or not path or not raw:
            raise ValueError(f"BAD_OVERRIDE (expected path=value): {override}")
        node = manifest
        keys = path.split(".")
        for key in keys[:-1]:
            if not isinstance(node, dict) or key not in node:
                raise ValueError(f"UNKNOWN_OVERRIDE_PATH: {path}")
            node = node[key]
        if not isinstance(node, dict) or keys[-1] not in node:
            raise ValueError(f"UNKNOWN_OVERRIDE_PATH: {path}")
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            value = raw
        node[keys[-1]] = value
    return manifest


def frame_plan(manifest_path, azimuths, overrides=None):
    """Everything the dispatch needs: frames, container inputs, local inputs.

    Local inputs stay local on purpose: the composite runs on the workstation
    (CPU, seconds) exactly as in T03/T05, because composite_worker is part of
    the accepted stills contract, not the render.
    """
    manifest_path = Path(manifest_path).resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    apply_overrides(manifest, overrides)
    reject_duplicate_azimuths(azimuths)
    hdri = manifest.get("lighting", {}).get("hdri_path")
    plate = manifest.get("compositing", {}).get("background_plate")
    frames = [frame_manifest(manifest, azimuth, f"/output/{FRAME_PREFIX}{frame_name(azimuth)}")
              for azimuth in azimuths]
    # Container destinations must match the paths frame_manifest rewrites into
    # the manifests; a mount anywhere else is a FileNotFoundError at 00:00.
    cad_mount = "/input/cad/" + Path(manifest["cad_source"]["file_path"]).name
    hdri_mount = f"/input/backgrounds/{Path(hdri).name}" if hdri else None
    mounts = {"/input/render_worker.py": ROOT / "render_worker.py",
              cad_mount: manifest_path.parents[1] / manifest["cad_source"]["file_path"]}
    if hdri_mount:
        mounts[hdri_mount] = manifest_path.parents[1] / hdri
    plate_path = str(manifest_path.parents[1] / plate) if plate else None
    compositing = manifest.get("compositing", {})
    # Every local input the dispatch and the local composite will open must
    # exist now, before a billable call: a typo'd --set value must fail at
    # plan time, not after the GPU has rendered a frame nothing can composite.
    missing = [str(path) for path in mounts.values() if not Path(path).is_file()]
    if plate_path and compositing.get("enabled") and not Path(plate_path).is_file():
        missing.append(plate_path)
    if missing:
        raise ValueError("MISSING_INPUT: " + ", ".join(sorted(missing)))
    return {
        "job_id": manifest["job_id"],
        "manifest_path": str(manifest_path),
        "frames": frames,
        "cad_mount": cad_mount,
        "hdri_mount": hdri_mount,
        "plate_path": plate_path,
        "compositing": compositing,
        "mounts": {dest: str(path) for dest, path in mounts.items()},
    }


def estimate_cost_usd(frame_seconds):
    """All-in estimate: one cold start plus the given per-frame seconds."""
    per_second = GPU_RATE_PER_S + 4 * CPU_RATE_PER_CORE_S + 16 * MEMORY_RATE_PER_GIB_S
    return round((COLD_START_SECONDS + sum(frame_seconds)) * per_second, 4)


def blender_command(container_manifest):
    """The flag set the v12 cloud proof ran with, unchanged."""
    return ["/opt/blender/blender", "--background", "--factory-startup", "--disable-autoexec",
            "--python-exit-code", "20", "--python", "/input/render_worker.py", "--",
            container_manifest]


def cloud_worker(request):
    """Render one frame inside the container; explicit outputs only."""
    import subprocess
    import threading
    output = Path("/output")
    output.mkdir(exist_ok=True)
    started = time.monotonic()
    result = {"schema_version": 1, "request_id": request["request_id"],
              "frame": request["frame"], "status": "failed", "failures": [],
              "artifacts": {}, "gpu_process_samples": []}
    stop = threading.Event()

    def monitor():
        while not stop.is_set():
            try:
                probe = subprocess.run(
                    ["nvidia-smi", "--query-compute-apps=pid,process_name,used_gpu_memory",
                     "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=5)
                if probe.returncode == 0 and probe.stdout.strip():
                    result["gpu_process_samples"].append(
                        {"seconds": round(time.monotonic() - started, 3),
                         "processes": probe.stdout.strip()})
            except (OSError, subprocess.TimeoutExpired):
                pass
            stop.wait(1)

    threading.Thread(target=monitor, daemon=True).start()
    log_name = f"blender-{request['frame']}.log"
    try:
        with (output / log_name).open("w") as log:
            run = subprocess.run(blender_command(request["manifest"]), stdout=log,
                                 stderr=subprocess.STDOUT, timeout=1080)
        result["blender_exit_code"] = run.returncode
        frame_dir = output / (FRAME_PREFIX + request["frame"])
        files = sorted(p for p in frame_dir.rglob("*") if p.is_file()) if frame_dir.is_dir() else []
        if run.returncode or not files:
            result["failures"].append(f"BLENDER_FAILED_OR_NO_OUTPUT: exit={run.returncode}")
        else:
            result["status"] = "rendered"
            for path in files:
                result["artifacts"][str(path.relative_to(output)).replace("\\", "/")] = {
                    "sha256": sha(path), "size_bytes": path.stat().st_size}
        report = frame_dir / "render-report.json" if frame_dir.is_dir() else None
        if report is not None and report.is_file():
            result["render_report"] = json.loads(report.read_text(encoding="utf-8"))
    except Exception as exc:
        result["failures"].append(f"{type(exc).__name__}: {exc}")
    finally:
        stop.set()
    result["seconds"] = round(time.monotonic() - started, 3)
    # GPU-process evidence is evaluated locally in main(), not here: Modal's
    # serializer (1.5.1) pickles imported functions by reference, so calling
    # msp_render_cli inside the function makes hydration fail with
    # ModuleNotFoundError in a container that cannot contain the module. The
    # samples below are the evidence; they are plain JSON.
    files_out = {}
    if result["status"] == "rendered":
        for name in result["artifacts"]:
            files_out[name] = (output / name).read_bytes()
    files_out[log_name] = (output / log_name).read_bytes()
    return result, files_out


def composite_settings(compositing):
    """The compositor's kwargs: the manifest block minus its non-kwargs keys."""
    return {key: value for key, value in compositing.items()
            if key not in ("enabled", "background_plate")}


def run_composite(frame_dir, plate, compositing):
    """Local composite with the stills pipeline's own compositor and settings."""
    from composite_worker import MSPCompositor
    beauty = str(Path(frame_dir) / "beauty.png")
    out = str(Path(frame_dir) / "composite.png")
    MSPCompositor.composite_asset(beauty, plate, out, **composite_settings(compositing))
    return out


def main():
    # Modal's progress renderer emits Unicode even when PowerShell redirects it.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=ROOT / "jobs/rl300_04_studio-white.json")
    parser.add_argument("--azimuths", default=None,
                        help="comma-separated camera azimuths; one Blender process per azimuth")
    parser.add_argument("--orbit", type=int, default=None,
                        help="render one full orbit of N unique azimuths; "
                             "mutually exclusive with --azimuths")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--gpu", default="L4")
    parser.add_argument("--set", action="append", default=[], dest="overrides",
                        metavar="PATH=VALUE",
                        help="manifest override, e.g. camera.depth_of_field.f_stop=3.2; "
                             "may repeat; recorded in request.json")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if args.orbit is not None:
        if args.azimuths is not None:
            raise SystemExit("AZIMUTH_SOURCE_CONFLICT: --orbit and --azimuths "
                             "are mutually exclusive")
        azimuths = orbit_azimuths(args.orbit)
    else:
        azimuths = [float(value) for value in
                    str(args.azimuths if args.azimuths is not None else "42").split(",")
                    if value.strip()]
    plan = frame_plan(args.manifest, azimuths, args.overrides)
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=False)

    archive = f"blender-{BLENDER_VERSION}-linux-x64.tar.xz"
    url = (f"https://download.blender.org/release/"
           f"Blender{'.'.join(BLENDER_VERSION.split('.')[:2])}/{archive}")
    request = {
        "schema_version": 1,
        "job_id": plan["job_id"],
        "orbit": ({"count": args.orbit, "step_deg": round(360.0 / args.orbit, 4)}
                  if args.orbit is not None else None),
        "runtime": {"version": BLENDER_VERSION, "build": BLENDER_BUILD,
                    "archive_sha256": BLENDER_ARCHIVE_SHA256, "archive_url": url},
        "resources": {"gpu": args.gpu, "cpu": 4, "memory_mib": 16384, "timeout_seconds": 1200,
                      "blender_timeout_seconds": 1080, "max_containers": 1,
                      "application_retries": 0},
        "frames": [{"frame": frame_name(f["camera"]["azimuth_deg"]),
                    "manifest": f"/input/manifest-{frame_name(f['camera']['azimuth_deg'])}.json"}
                   for f in plan["frames"]],
        "overrides": list(args.overrides),
        "inputs": {dest: sha(path) for dest, path in
                   [(dest, Path(path)) for dest, path in plan["mounts"].items()]},
        "compositing_execution": "local",
    }
    # Local-measured marginal render time (video-pipeline-brief.md section 3.1:
    # 101.65 s/frame mean at this resolution); the cloud figure is unknown until
    # the first measured run, exactly as brief section 4.1 states.
    request["cost_estimate_usd"] = estimate_cost_usd([101.65] * len(azimuths))
    save(output / "request.json", request)
    for frame in plan["frames"]:
        save(output / f"manifest-{frame_name(frame['camera']['azimuth_deg'])}.json", frame)
    print(json.dumps({"plan": request["frames"], "cost_estimate_usd": request["cost_estimate_usd"],
                      "output": str(output)}))
    if not args.execute:
        print("Preflight only; no cloud call.")
        return 0

    import modal
    from msp_render_cli.remote_job import gpu_process_evidence
    image = (modal.Image.debian_slim(python_version=f"{sys.version_info.major}.{sys.version_info.minor}")
             .apt_install("wget", "xz-utils", "libglu1-mesa", "libxi6", "libxrender1", "libxfixes3",
                          "libxcursor1", "libxinerama1", "libxkbcommon0", "libsm6", "libxxf86vm1",
                          "libgl1")
             .run_commands(f"wget --timeout=60 --tries=2 -q {url} -O /tmp/blender.tar.xz",
                           f"echo '{BLENDER_ARCHIVE_SHA256}  /tmp/blender.tar.xz' | sha256sum -c -",
                           "mkdir /opt/blender && tar -xf /tmp/blender.tar.xz -C /opt/blender --strip-components=1",
                           "rm /tmp/blender.tar.xz"))
    for dest, source in sorted(plan["mounts"].items()):
        image = image.add_local_file(Path(source), dest)
    for frame in plan["frames"]:
        name = frame_name(frame["camera"]["azimuth_deg"])
        image = image.add_local_file(output / f"manifest-{name}.json", f"/input/manifest-{name}.json")
    app = modal.App("studiomark-tv2-preview")
    worker = app.function(image=image, gpu=args.gpu, cpu=4, memory=16384, timeout=1200,
                          startup_timeout=300, max_containers=1, retries=0, scaledown_window=60,
                          serialized=True)(cloud_worker)
    started = time.monotonic()
    results = []
    try:
        with modal.enable_output(), app.run():
            for frame in request["frames"]:
                frame_request = dict(request, **{"request_id": str(uuid.uuid4())}, **frame)
                result, files = worker.remote(frame_request)
                if result["request_id"] != frame_request["request_id"]:
                    raise ValueError("RESULT_IDENTITY_MISMATCH: " + frame["frame"])
                result["blender_gpu_process_seen"] = gpu_process_evidence(
                    result["gpu_process_samples"])
                if not result["blender_gpu_process_seen"]:
                    result["failures"].append("NO_BLENDER_GPU_PROCESS_EVIDENCE")
                    result["status"] = "failed"
                save(output / f"result-{frame['frame']}.json", result)
                for name, content in files.items():
                    known = result["artifacts"].get(name)
                    if known and hashlib.sha256(content).hexdigest() != known["sha256"]:
                        raise ValueError("OUTPUT_HASH_MISMATCH: " + name)
                    destination = output / "cloud" / name
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    destination.write_bytes(content)
                results.append(result)
                if result["status"] != "rendered":
                    break  # a failed frame must not cost the frames after it
        composites = []
        if plan["plate_path"] and plan["compositing"].get("enabled"):
            for result in results:
                if result["status"] != "rendered":
                    continue
                composites.append(run_composite(
                    output / "cloud" / (FRAME_PREFIX + result["frame"]),
                    plan["plate_path"], plan["compositing"]))
        save(output / "status.json", {
            "status": "passed" if results and all(r["status"] == "rendered" for r in results) else "failed",
            "wall_seconds": round(time.monotonic() - started, 3),
            "frames": [{k: r[k] for k in ("frame", "status", "blender_exit_code", "seconds",
                                          "blender_gpu_process_seen")} for r in results],
            "composites": composites})
        print(json.dumps({"status": json.loads((output / "status.json").read_text())["status"],
                          "composites": composites, "output": str(output)}))
        return 0 if results and all(r["status"] == "rendered" for r in results) else 1
    except Exception as exc:
        save(output / "status.json", {"status": "failed_or_submission_unknown", "error": str(exc)})
        raise


if __name__ == "__main__":
    raise SystemExit(main())

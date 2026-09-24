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

`--resume` makes that isolation survivable: a frame counts as finished only
when its result, its GPU-process evidence and every artifact's sha are all on
disk, so a re-run of a crashed orbit renders the missing frames and nothing
else, while a plan that drifted since the first dispatch is refused instead of
being mixed into one sequence. The resume log is the record of those runs;
request.json stays the original pre-dispatch estimate and is never rewritten.

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

# A resume may only continue the sequence it interrupts, so the request keys
# below must match the saved one exactly. `inputs` is the load-bearing one: it
# holds the sha256 of every mounted file, render_worker.py and the frame
# manifests' sources included, so a worker rebuild or a re-saved CAD source
# can never be mixed silently into one orbit.
RESUME_COMPARE_KEYS = ("job_id", "orbit", "runtime", "resources", "frames",
                       "overrides", "inputs", "render_passes_per_frame")

RESUME_LOG_NAME = "resume-log.json"


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


# Schema-declared optional paths (docs/job_manifest.schema.json) that an
# explicit --set may create in an older job manifest that omits them. Every
# other absent path still raises UNKNOWN_OVERRIDE_PATH, so existing jobs keep
# their exact manifest structure unless the operator names this one path.
SCHEMA_OPTIONAL_OVERRIDE_PATHS = frozenset({
    "lighting.key_enabled",
    "lighting.fill_enabled",
    "lighting.rim_enabled",
    "lighting.rim_profile",
})

# Every schema-declared boolean lighting control (re-review finding 1:
# five top-level keys plus the nested lighting.floor.enabled) takes an exact
# JSON boolean in --set (3g review F1, widened per the 3i DeepSeek reviews'
# findings). The worker reads the top-level five truthy
# (render_worker.setup_lighting, the shadow-catcher branch) and floor mode
# strictly (`floor_mode` reads `is True`), so a string "FALSE"/"TRUE" or a
# JSON 0/null silently runs the opposite of what the author meant - it must
# fail before a billable call instead. Only the *_enabled three are also
# CREATABLE when absent; analytic_lights/shadow_catcher/floor.enabled are
# ordinary schema keys. rim_profile is NOT here: its value contract (a known
# profile-name string) is fully owned by validate_rim_profile whatever route
# the value took, so a typed guard would only relabel its existing errors.
BOOLEAN_OVERRIDE_PATHS = frozenset({
    "lighting.key_enabled",
    "lighting.fill_enabled",
    "lighting.rim_enabled",
    "lighting.analytic_lights",
    "lighting.shadow_catcher",
    "lighting.floor.enabled",
})


def apply_overrides(manifest, overrides):
    """Apply dotted-path=value overrides in place; unknown paths are errors.

    Values parse as JSON when they can (numbers, booleans) and stay strings
    otherwise (paths). A typo'd path must fail before a billable call, not
    silently render the unmodified job. Only paths listed in
    SCHEMA_OPTIONAL_OVERRIDE_PATHS may be created when absent; no default is
    ever injected without an explicit override. A BOOLEAN_OVERRIDE_PATHS value
    that is not an exact JSON boolean is a hard error: the worker reads
    *_enabled truthy, so "FALSE"/0/null would silently flip a light.
    """
    for override in overrides or []:
        path, sep, raw = override.partition("=")
        if not sep or not path or not raw:
            raise ValueError(f"BAD_OVERRIDE (expected path=value): {override}")
        node = manifest
        keys = path.split(".")
        may_create = path in SCHEMA_OPTIONAL_OVERRIDE_PATHS
        for key in keys[:-1]:
            if not isinstance(node, dict):
                raise ValueError(f"UNKNOWN_OVERRIDE_PATH: {path}")
            if may_create:
                node = node.setdefault(key, {})
            elif key not in node:
                raise ValueError(f"UNKNOWN_OVERRIDE_PATH: {path}")
            else:
                node = node[key]
        if not isinstance(node, dict) or (not may_create and keys[-1] not in node):
            raise ValueError(f"UNKNOWN_OVERRIDE_PATH: {path}")
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            value = raw
        if path in BOOLEAN_OVERRIDE_PATHS and not isinstance(value, bool):
            raise ValueError(
                f"BAD_OVERRIDE_VALUE: {override} (must be a JSON boolean)")
        node[keys[-1]] = value
    return manifest


def validate_rim_profile(manifest) -> None:
    """A rim_profile the worker would reject must fail before a billable call.

    An ABSENT key is inert and creates no key: the default is the worker's,
    not the dispatcher's. A PRESENT key is validated whatever its value. An
    explicit null is NOT inert: the worker reads a present null as a non-string
    and raises after the billable call, so it must be rejected here. Anything
    that is not a known profile name - null, a typo'd string, a number, a
    boolean, a list, an empty string - is a hard error naming the value rep and
    the valid names. RIM_PROFILES is imported lazily so importing this
    dispatcher never pulls render_worker (same pattern as the lazy
    composite_worker import inside frame_plan).
    """
    lighting = manifest.get("lighting")
    if not isinstance(lighting, dict):
        return
    if "rim_profile" not in lighting:
        return
    profile = lighting["rim_profile"]
    from render_worker import RIM_PROFILES
    if isinstance(profile, str) and profile in RIM_PROFILES:
        return
    raise ValueError(
        f"INVALID_RIM_PROFILE: {profile!r} "
        f"(valid: {sorted(RIM_PROFILES)})")


def validate_lighting_booleans(manifest) -> None:
    """A boolean lighting control that is not exactly a JSON boolean must
    fail before a billable call (3g review F1's dispatch-path assertion).

    The worker reads these controls as truthy values (render_worker's light
    rig and shadow-catcher branch) or strictly (floor_mode reads `is True`),
    so a manifest carrying "false"/"TRUE" runs the opposite of what the
    author meant. apply_overrides types the --set route; this walks each
    BOOLEAN_OVERRIDE_PATHS in the manifest (one list, dotted paths, nesting
    included) and catches values the file itself carries. An ABSENT key is
    inert and injects nothing.
    """
    lighting = manifest.get("lighting")
    if not isinstance(lighting, dict):
        return
    for path in sorted(BOOLEAN_OVERRIDE_PATHS):
        keys = path.split(".")[1:]  # every entry starts with "lighting."
        node = lighting
        for key in keys[:-1]:
            node = node.get(key) if isinstance(node, dict) else None
        if not isinstance(node, dict) or keys[-1] not in node:
            continue
        if not isinstance(node[keys[-1]], bool):
            raise ValueError(
                f"INVALID_LIGHTING_BOOLEAN: {path}={node[keys[-1]]!r} "
                f"(JSON true/false only)")


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
    # Feature-combination validation runs here, after overrides, before any
    # Modal Function object even exists: an invalid floor/film combination
    # must never reach a billable call.
    from composite_worker import floor_mode, validate_floor_config
    errors = validate_floor_config(manifest)
    if errors:
        raise ValueError("INVALID_FLOOR_CONFIG: " + "; ".join(errors))
    # A rim_profile the worker would reject must die here, before any mount or
    # file check and before --execute: no billable call for a typo.
    validate_rim_profile(manifest)
    # Same rule for the boolean light controls, whatever route the value took.
    validate_lighting_booleans(manifest)
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
        "floor_mode": floor_mode(manifest),
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


def frame_render_seconds(floor_mode=False):
    """Conservative per-frame render seconds fed to the estimate.

    Floor mode renders each frame TWICE (opaque beauty plus the floor-hidden
    product matte), so the estimate explicitly counts both passes. The local
    101.65 s/frame marginal figure is the measured basis; the +10-30% hand
    wave is not used. Actual timings come from the render report.

    Returns the per-frame seconds as a scalar; the call site repeats it once
    per frame when building the estimate list.
    """
    local_marginal_seconds = 101.65
    passes = 2.0 if floor_mode else 1.0
    return local_marginal_seconds * passes


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


def run_composite(frame_dir, plate, compositing, floor_mode=False):
    """Local composite with the stills pipeline's own compositor and settings."""
    from composite_worker import MSPCompositor
    frame_dir = Path(frame_dir)
    lens_kwargs = {key: compositing[key] for key in
                   ("lens_vignette", "lens_bloom", "lens_grain")
                   if key in compositing}
    if floor_mode:
        # Full-scene finishing: the rendered floor stays, no plate is pasted,
        # and the mask is checked against the independent beauty-matte alpha.
        result = MSPCompositor.composite_rendered_floor_asset(
            str(frame_dir / "beauty.png"),
            str(frame_dir / "mask.png"),
            str(frame_dir / "beauty-matte.png"),
            str(frame_dir / "composite.png"),
            shadow_opacity=compositing.get("shadow_opacity"), **lens_kwargs)
        print(json.dumps({"floor_composite": {
            "frame": frame_dir.name, "status": result["status"],
            "mode": result["mode"]}}))
        return result["output_path"]
    beauty = str(frame_dir / "beauty.png")
    out = str(frame_dir / "composite.png")
    MSPCompositor.composite_asset(beauty, plate, out, **composite_settings(compositing))
    return out


def utc_now():
    """ISO-8601 UTC at second precision; the resume log's clock, nothing else."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def frame_complete(output_dir, frame):
    """(complete, reason): a frame is done only when its bytes are provably on disk.

    Every clause can only make a frame incomplete, never billable again: the
    result parses, it says rendered, the GPU process was seen, it names at
    least one artifact, and every named artifact exists with the sha the
    result declared. A corrupt or half-written result is incomplete rather
    than an exception - a resume must never die on the artifact it inspects.
    """
    output_dir = Path(output_dir)
    result_path = output_dir / f"result-{frame}.json"
    if not result_path.is_file():
        return False, "missing result"
    try:
        result = json.loads(result_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False, "corrupt result"
    if not isinstance(result, dict):
        return False, "corrupt result"
    if result.get("status") != "rendered":
        return False, "status failed"
    if result.get("blender_gpu_process_seen") is not True:
        return False, "no gpu evidence"
    artifacts = result.get("artifacts")
    if not isinstance(artifacts, dict) or not artifacts:
        return False, "empty artifacts"
    for name, meta in artifacts.items():
        declared = meta.get("sha256") if isinstance(meta, dict) else None
        path = output_dir / "cloud" / name
        if not path.is_file():
            return False, f"artifact missing: {name}"
        try:
            actual = sha(path)
        except OSError:
            return False, f"artifact missing: {name}"
        if not isinstance(declared, str) or actual != declared:
            return False, f"artifact sha mismatch: {name}"
    return True, ""


def resume_mismatch(saved, request):
    """The compared request keys this invocation disagrees with the saved one on."""
    if not isinstance(saved, dict):
        return ["request.json"]
    absent = object()
    return [key for key in RESUME_COMPARE_KEYS
            if saved.get(key, absent) != request.get(key, absent)]


def check_resume_request(output, request, frames):
    """Refuse a resume whose plan drifted; runs before anything is written.

    A resumed run that silently mixed two worker builds, two CAD revisions or
    two sets of overrides into one sequence would produce a film nothing can
    defend, so every difference is a hard stop naming the keys. The saved
    request.json is the pre-dispatch estimate of record and is never rewritten
    here; the frame manifests are verified JSON-equal, not re-saved, so a
    refusal leaves the directory exactly as the crashed run left it.
    """
    request_path = Path(output) / "request.json"
    try:
        saved = json.loads(request_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        raise SystemExit("RESUME_REQUEST_MISMATCH: request.json")
    differing = resume_mismatch(saved, request)
    if differing:
        raise SystemExit("RESUME_REQUEST_MISMATCH: " + ", ".join(differing))
    for frame in frames:
        name = frame_name(frame["camera"]["azimuth_deg"])
        path = Path(output) / f"manifest-{name}.json"
        try:
            saved_frame = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            saved_frame = None
        if saved_frame != frame:
            raise SystemExit(f"RESUME_REQUEST_MISMATCH: manifest-{name}")


def append_resume_log(output, entry):
    """Append one resume invocation to the run's record (an on-disk JSON list)."""
    path = Path(output) / RESUME_LOG_NAME
    entries = []
    if path.is_file():
        try:
            entries = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            raise SystemExit(f"CORRUPT_RESUME_LOG: {path}")
        if not isinstance(entries, list):
            raise SystemExit(f"CORRUPT_RESUME_LOG: {path}")
    entries.append(entry)
    staging = path.with_name(path.name + ".tmp")
    save(staging, entries)
    staging.replace(path)


def dispatch_frames(frames, request, output, remote_call, gpu_evidence,
                    skip_complete=True):
    """Dispatch every frame that is not already complete on disk, in plan order.

    The semantics are the pre-resume loop's, unchanged: identity check, then
    GPU-process evidence (a frame without it is failed, never shippable), the
    result saved before its bytes are trusted, sha verify against the declared
    digests, and a hard stop at the first non-rendered frame so a failure
    cannot cost the frames behind it. Complete frames are skipped, so a resume
    never re-pays a rendered frame; the stale result of a frame about to be
    re-rendered is deleted first, so a torn run cannot leave an old result
    sitting next to new bytes. `skip_complete` is False for any run whose
    request was not verified against the directory: frames it did not plan
    are never adopted.
    """
    output = Path(output)
    results = []
    for frame in frames:
        name = frame["frame"]
        if skip_complete and frame_complete(output, name)[0]:
            continue
        stale = output / f"result-{name}.json"
        if stale.is_file():
            stale.unlink()
        frame_request = dict(request, **{"request_id": str(uuid.uuid4())}, **frame)
        result, files = remote_call(frame_request)
        if result["request_id"] != frame_request["request_id"]:
            raise ValueError("RESULT_IDENTITY_MISMATCH: " + name)
        result["blender_gpu_process_seen"] = gpu_evidence(result["gpu_process_samples"])
        if not result["blender_gpu_process_seen"]:
            result["failures"].append("NO_BLENDER_GPU_PROCESS_EVIDENCE")
            result["status"] = "failed"
        save(output / f"result-{name}.json", result)
        for file_name, content in files.items():
            known = result["artifacts"].get(file_name)
            if known and hashlib.sha256(content).hexdigest() != known["sha256"]:
                raise ValueError("OUTPUT_HASH_MISMATCH: " + file_name)
            destination = output / "cloud" / file_name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)
        results.append(result)
        if result["status"] != "rendered":
            break  # a failed frame must not cost the frames after it
    return results


def frames_on_disk(output, frame_names):
    """Every plan frame with a readable result, in plan order, read from disk."""
    output = Path(output)
    results = []
    for name in frame_names:
        path = output / f"result-{name}.json"
        if not path.is_file():
            continue
        try:
            results.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
    return results


def composite_frames(plan, output, results, floor_on):
    """The local composite pass, over every rendered frame of the plan."""
    composites = []
    if plan["compositing"].get("enabled") and (floor_on or plan["plate_path"]):
        for result in results:
            if result.get("status") != "rendered":
                continue
            composites.append(run_composite(
                Path(output) / "cloud" / (FRAME_PREFIX + result["frame"]),
                plan["plate_path"], plan["compositing"],
                floor_mode=floor_on))
    return composites


def write_status(output, frame_names, results, composites, wall_seconds, resumed):
    """status.json covers every plan frame on disk, not only this invocation's.

    `passed` needs the whole plan complete: a resume that renders the last
    frames of a crashed orbit must not report a passing sequence while frames
    in the middle are missing. Results are read back from disk because the
    skipped ones were never part of this invocation.
    """
    complete = [frame_complete(output, name)[0] for name in frame_names]
    passed = bool(complete) and all(complete)
    save(Path(output) / "status.json", {
        "status": "passed" if passed else "failed",
        "resumed": bool(resumed),
        "wall_seconds": wall_seconds,
        "frames": [{k: r.get(k) for k in ("frame", "status", "blender_exit_code",
                                          "seconds", "blender_gpu_process_seen")}
                   for r in results],
        "composites": composites})
    return passed


def main(argv=None, remote=None, gpu_evidence=None):
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
    parser.add_argument("--resume", action="store_true",
                        help="reuse an existing output dir: skip the frames already "
                             "rendered and verified on disk, and refuse a changed plan")
    args = parser.parse_args(argv)
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
    floor_on = bool(plan["floor_mode"])
    output = args.output_dir.resolve()
    frame_names = [frame_name(frame["camera"]["azimuth_deg"]) for frame in plan["frames"]]
    # Only a directory that already holds a request has history to continue;
    # --resume on a fresh directory is a first run, so one command serves both
    # the first attempt and every retry of it.
    resuming = bool(args.resume) and (output / "request.json").is_file()
    # Without --resume an existing directory is still an error, exactly as
    # before: a second dispatch into a live sequence would overwrite frames
    # nobody re-verified.
    output.mkdir(parents=True, exist_ok=bool(args.resume))

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
    # the first measured run, exactly as brief section 4.1 states. Floor mode
    # doubles it: the matte pass is a second full render, not a percentage.
    request["render_passes_per_frame"] = 2 if floor_on else 1
    request["cost_estimate_usd"] = estimate_cost_usd(
        [frame_render_seconds(floor_mode=floor_on)] * len(azimuths))
    if resuming:
        # Nothing is written before this check passes: a mismatched resume
        # must leave the directory as the crashed run left it.
        check_resume_request(output, request, plan["frames"])
    else:
        save(output / "request.json", request)
        for frame in plan["frames"]:
            save(output / f"manifest-{frame_name(frame['camera']['azimuth_deg'])}.json", frame)
    skipped, pending, skip_reasons = [], list(frame_names), {}
    if resuming:
        verdicts = {name: frame_complete(output, name) for name in frame_names}
        skipped = [name for name in frame_names if verdicts[name][0]]
        pending = [name for name in frame_names if not verdicts[name][0]]
        skip_reasons = {name: verdicts[name][1] for name in pending}
    if args.resume and args.execute:
        # The invocation record, written before anything billable so a retry
        # that dies at once still leaves an account of itself. An empty
        # pending list is priced at zero: rendering nothing costs nothing.
        per_frame = frame_render_seconds(floor_mode=floor_on)
        append_resume_log(output, {
            "started_utc": utc_now(), "skipped": skipped, "pending": pending,
            "skip_reasons": skip_reasons,
            "cost_estimate_usd": (estimate_cost_usd([per_frame] * len(pending))
                                  if pending else 0.0)})
    print(json.dumps({"plan": request["frames"], "cost_estimate_usd": request["cost_estimate_usd"],
                      "output": str(output)}))
    if not args.execute:
        print("Preflight only; no cloud call.")
        return 0

    started = time.monotonic()
    try:
        if resuming and not pending:
            # Every frame of the plan is already on disk: finish from disk,
            # never import modal, never spend a cloud second.
            pass
        elif remote is None:
            import modal
            from msp_render_cli.remote_job import gpu_process_evidence as evidence_fn
            gpu_evidence = evidence_fn
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
            with modal.enable_output(), app.run():
                dispatch_frames(request["frames"], request, output, worker.remote, gpu_evidence,
                                skip_complete=resuming)
        else:
            # An injected remote (tests): the same loop, no Modal in the process.
            dispatch_frames(request["frames"], request, output, remote, gpu_evidence,
                            skip_complete=resuming)
        results = frames_on_disk(output, frame_names)
        composites = composite_frames(plan, output, results, floor_on)
        passed = write_status(output, frame_names, results, composites,
                              round(time.monotonic() - started, 3), resuming)
        print(json.dumps({"status": json.loads((output / "status.json").read_text())["status"],
                          "composites": composites, "output": str(output)}))
        return 0 if passed else 1
    except Exception as exc:
        save(output / "status.json", {"status": "failed_or_submission_unknown", "error": str(exc)})
        raise


if __name__ == "__main__":
    raise SystemExit(main())

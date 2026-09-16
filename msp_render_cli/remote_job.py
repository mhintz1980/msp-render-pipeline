"""Pure-Python request/result contracts for remote Blender render jobs.

The module deliberately has no Blender dependency.  A manifest and render
settings are retained as canonical JSON documents inside closed contract
objects so the contract can pin the pipeline's full, evolving configuration
without allowing unvalidated keys at the contract level.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence


SCHEMA_VERSION = 1
MIN_SOLO_GPU_MIB = 256
FAILURE_CODES = (
    "GPU_REQUIRED",
    "MISSING_OUTPUT",
    "RENDER_NONZERO_EXIT",
    "ARTIFACT_HASH_MISMATCH",
    "CONTRACT_INVALID",
)

# These values are deliberately excluded from the digest because they identify
# an attempt to run a request, rather than the pixels the request describes.
IDENTITY_EXCLUDED_FIELDS = (
    "request_id",
    "attempt_id",
    "submission_id",
    "submitted_at",
    "output_dir",
)
IDENTITY_INCLUDED_FIELDS = (
    "manifest",
    "input_assets",
    "runtime",
    "render_settings",
    "expected_artifacts",
    "require_gpu",
)

_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_SCHEMA_DIR = Path(__file__).resolve().parents[1] / "docs"


class ContractError(ValueError):
    """A contract could not honestly be constructed."""

    def __init__(self, failure_code: str, detail: str):
        self.failure_code = failure_code
        super().__init__(f"{failure_code}: {detail}")


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ContractError("CONTRACT_INVALID", f"not canonical JSON: {exc}") from exc


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _pinned_document(value: Any) -> dict[str, str]:
    if isinstance(value, Mapping):
        payload = _canonical_json(value)
    elif isinstance(value, str):
        try:
            payload = _canonical_json(json.loads(value))
        except (json.JSONDecodeError, ContractError) as exc:
            raise ContractError("CONTRACT_INVALID", "document is not JSON") from exc
    else:
        raise ContractError("CONTRACT_INVALID", "document must be an object or JSON text")
    return {"canonical_json": payload, "sha256": _sha256_bytes(payload.encode("utf-8"))}


def _normalise_assets(input_assets: Mapping[str, str] | Sequence[Mapping[str, str]]) -> list[dict[str, str]]:
    if isinstance(input_assets, Mapping):
        records = [{"path": path, "sha256": digest} for path, digest in input_assets.items()]
    else:
        records = list(input_assets)
    result = []
    for record in records:
        if not isinstance(record, Mapping) or set(record) != {"path", "sha256"}:
            raise ContractError("CONTRACT_INVALID", "input assets must contain only path and sha256")
        path, digest = record["path"], record["sha256"]
        if not isinstance(path, str) or not path or not isinstance(digest, str) or not _HASH_RE.fullmatch(digest):
            raise ContractError("CONTRACT_INVALID", "input asset path/hash is invalid")
        result.append({"path": path, "sha256": digest})
    return sorted(result, key=lambda item: item["path"])


def _normalise_runtime(runtime: Mapping[str, Any]) -> dict[str, str]:
    if not isinstance(runtime, Mapping):
        raise ContractError("CONTRACT_INVALID", "runtime must be an object")

    def pick(*names: str) -> Any:
        for name in names:
            if name in runtime:
                return runtime[name]
        return None

    result = {
        "blender_version": pick("blender_version", "version"),
        "image": pick("image", "image_tag", "build_image"),
        "build": pick("build", "build_tag"),
        "device_requirement": pick("device_requirement", "device"),
    }
    if any(not isinstance(value, str) or not value for value in result.values()):
        raise ContractError("CONTRACT_INVALID", "runtime requires non-empty version, image, build, and device")
    return result


def _normalise_observed_runtime(runtime: Mapping[str, Any]) -> dict[str, str]:
    if not isinstance(runtime, Mapping):
        raise ContractError("CONTRACT_INVALID", "observed runtime must be an object")

    def pick(*names: str) -> Any:
        for name in names:
            if name in runtime:
                return runtime[name]
        return None

    result = {
        "blender_version": pick("blender_version", "version"),
        "image": pick("image", "image_tag", "build_image"),
        "build": pick("build", "build_tag"),
    }
    if any(not isinstance(value, str) or not value for value in result.values()):
        raise ContractError("CONTRACT_INVALID", "observed runtime requires non-empty version, image, and build")
    return result


def _normalise_artifact_names(expected_artifacts: Sequence[str]) -> list[str]:
    if isinstance(expected_artifacts, (str, bytes)):
        raise ContractError("CONTRACT_INVALID", "expected_artifacts must be an array")
    names = list(expected_artifacts)
    if not names or any(not isinstance(name, str) or not name for name in names):
        raise ContractError("CONTRACT_INVALID", "expected_artifacts must contain non-empty names")
    if len(set(names)) != len(names):
        raise ContractError("CONTRACT_INVALID", "expected_artifacts must be unique")
    return names


def _validate_against_schema(document: Any, schema_name: str) -> None:
    schema = json.loads((_SCHEMA_DIR / schema_name).read_text(encoding="utf-8"))
    _walk_schema(document, schema, schema, "$" )


class _SchemaValidationError(ValueError):
    pass


def _walk_schema(value: Any, schema: Mapping[str, Any], root: Mapping[str, Any], path: str) -> None:
    if "$ref" in schema:
        target = root
        for part in schema["$ref"].removeprefix("#/").split("/"):
            target = target[part]
        _walk_schema(value, target, root, path)
        return
    if "oneOf" in schema:
        errors = []
        for option in schema["oneOf"]:
            try:
                _walk_schema(value, option, root, path)
                return
            except _SchemaValidationError as exc:
                errors.append(str(exc))
        raise _SchemaValidationError(f"{path}: no oneOf branch matched")
    if "const" in schema and value != schema["const"]:
        raise _SchemaValidationError(f"{path}: expected const {schema['const']!r}")
    if "enum" in schema and value not in schema["enum"]:
        raise _SchemaValidationError(f"{path}: value is outside enum")
    expected = schema.get("type")
    if expected is not None:
        expected_types = expected if isinstance(expected, list) else [expected]
        if not any(_matches_type(value, item) for item in expected_types):
            raise _SchemaValidationError(f"{path}: wrong type")
    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            raise _SchemaValidationError(f"{path}: string is too short")
        if "pattern" in schema and re.fullmatch(schema["pattern"], value) is None:
            raise _SchemaValidationError(f"{path}: string pattern mismatch")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if not math.isfinite(value):
            raise _SchemaValidationError(f"{path}: number must be finite")
        if "minimum" in schema and value < schema["minimum"]:
            raise _SchemaValidationError(f"{path}: below minimum")
        if "exclusiveMinimum" in schema and value <= schema["exclusiveMinimum"]:
            raise _SchemaValidationError(f"{path}: at or below exclusive minimum")
    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            raise _SchemaValidationError(f"{path}: too few items")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            raise _SchemaValidationError(f"{path}: too many items")
        if "items" in schema:
            for index, item in enumerate(value):
                _walk_schema(item, schema["items"], root, f"{path}[{index}]")
    if isinstance(value, dict):
        required = schema.get("required", ())
        missing = [key for key in required if key not in value]
        if missing:
            raise _SchemaValidationError(f"{path}: missing required {missing}")
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            unknown = set(value) - set(properties)
            if unknown:
                raise _SchemaValidationError(f"{path}: unknown properties {sorted(unknown)}")
        for key, child in properties.items():
            if key in value:
                _walk_schema(value[key], child, root, f"{path}.{key}")


def _matches_type(value: Any, expected: str) -> bool:
    return {
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        "boolean": isinstance(value, bool),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "number": isinstance(value, (int, float)) and not isinstance(value, bool),
        "null": value is None,
    }.get(expected, False)


def validate_request(request: Mapping[str, Any]) -> bool:
    """Return whether *request* satisfies the request JSON Schema and semantics."""
    try:
        _validate_against_schema(request, "remote_job_request.schema.json")
        return True
    except (OSError, json.JSONDecodeError, _SchemaValidationError, TypeError):
        return False


def validate_result(result: Mapping[str, Any]) -> bool:
    """Return whether *result* satisfies the result JSON Schema and semantics."""
    try:
        _validate_against_schema(result, "remote_job_result.schema.json")
        if result["status"] == "passed" and result["failure_code"] is not None:
            return False
        if result["status"] == "failed" and result["failure_code"] is None:
            return False
        evidence = result["compute"]["gpu_evidence"]
        if evidence["samples"] and (evidence["peak_gpu_memory_mib"] is None
                                     or evidence["sustained_gpu_memory_mib"] is None):
            return False
        return True
    except (OSError, json.JSONDecodeError, KeyError, _SchemaValidationError, TypeError):
        return False


def job_id(request: Mapping[str, Any]) -> str:
    """Hash only pixel-affecting request pins; submission/attempt metadata is excluded."""
    identity = {field: request[field] for field in IDENTITY_INCLUDED_FIELDS}
    payload = _canonical_json(identity).encode("utf-8")
    return _sha256_bytes(payload)


def build_request(
    manifest: Mapping[str, Any] | str,
    input_assets: Mapping[str, str] | Sequence[Mapping[str, str]],
    runtime: Mapping[str, Any],
    render_settings: Mapping[str, Any] | str,
    expected_artifacts: Sequence[str],
    require_gpu: bool = False,
    *,
    request_id: Optional[str] = None,
    attempt_id: Optional[str] = None,
    submission_id: Optional[str] = None,
    submitted_at: Optional[str] = None,
    output_dir: Optional[str] = None,
) -> dict[str, Any]:
    """Construct and schema-validate a remote render request."""
    if not isinstance(require_gpu, bool):
        raise ContractError("CONTRACT_INVALID", "require_gpu must be boolean")
    request = {
        "schema_version": SCHEMA_VERSION,
        "request_id": request_id or "local-request",
        "attempt_id": attempt_id or "local-attempt",
        "manifest": _pinned_document(manifest),
        "input_assets": _normalise_assets(input_assets),
        "runtime": _normalise_runtime(runtime),
        "render_settings": _pinned_document(render_settings),
        "expected_artifacts": _normalise_artifact_names(expected_artifacts),
        "require_gpu": require_gpu,
    }
    # These fields remain available to callers for transport bookkeeping but
    # are intentionally outside IDENTITY_INCLUDED_FIELDS.
    if submission_id is not None:
        request["submission_id"] = submission_id
    if submitted_at is not None:
        request["submitted_at"] = submitted_at
    if output_dir is not None:
        request["output_dir"] = output_dir
    if not validate_request(request):
        raise ContractError("CONTRACT_INVALID", "constructed request failed its JSON Schema")
    return request


def gpu_process_evidence(samples: Sequence[Mapping[str, Any]]) -> bool:
    """Adjudicate nvidia-smi samples using the proven PID-namespace rule."""
    pids, peak = set(), 0
    for sample in samples:
        for row in sample.get("processes", "").splitlines():
            parts = [part.strip() for part in row.split(",")]
            if len(parts) != 3:
                continue
            pid, name, memory = parts
            if "blender" in name.lower():
                return True
            if pid and memory.isdigit():
                pids.add(pid)
                peak = max(peak, int(memory))
    return len(pids) == 1 and peak >= MIN_SOLO_GPU_MIB


def _normalise_compute(compute: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(compute, Mapping):
        raise ContractError("CONTRACT_INVALID", "compute must be an object")
    devices = compute.get("enabled_devices", compute.get("devices", []))
    if not isinstance(devices, Sequence) or isinstance(devices, (str, bytes)):
        raise ContractError("CONTRACT_INVALID", "enabled_devices must be an array")
    enabled = []
    for device in devices:
        if not isinstance(device, Mapping) or not isinstance(device.get("name"), str) or not isinstance(device.get("type"), str):
            raise ContractError("CONTRACT_INVALID", "each enabled device needs name and type")
        enabled.append({"name": device["name"], "type": device["type"]})
    evidence_input = compute.get("gpu_evidence", {})
    if isinstance(evidence_input, bool):
        evidence_input = {"verdict": evidence_input}
    if not isinstance(evidence_input, Mapping):
        raise ContractError("CONTRACT_INVALID", "gpu_evidence must be an object")
    samples = evidence_input.get("samples", [])
    if not isinstance(samples, list):
        raise ContractError("CONTRACT_INVALID", "GPU samples must be an array")
    verdict = (gpu_process_evidence(samples) if samples
               else bool(evidence_input.get("verdict", evidence_input.get("passed", False))))
    peak = evidence_input.get("peak_gpu_memory_mib")
    sustained = evidence_input.get("sustained_gpu_memory_mib")
    if samples:
        memories = []
        for sample in samples:
            for row in sample.get("processes", "").splitlines():
                parts = [part.strip() for part in row.split(",")]
                if len(parts) == 3 and parts[2].isdigit():
                    memories.append(int(parts[2]))
        if memories:
            peak = max(memories)
            sustained = max(memories)
    return {
        "enabled_devices": enabled,
        "cpu_in_mix": bool(compute.get("cpu_in_mix", any(device["type"] == "CPU" for device in enabled))),
        "gpu_evidence": {
            "verdict": verdict,
            "samples": samples,
            "peak_gpu_memory_mib": peak,
            "sustained_gpu_memory_mib": sustained,
        },
    }


def _collect_artifacts(output_dir: Path, report_name: str = "render-report.json") -> list[dict[str, Any]]:
    files = []
    for path in sorted(output_dir.rglob("*")):
        if not path.is_file() or path.relative_to(output_dir).as_posix() == report_name:
            continue
        relative = path.relative_to(output_dir).as_posix()
        size = path.stat().st_size
        files.append({"path": relative, "sha256": _sha256_file(path), "size_bytes": size})
    return files


def build_result(
    request: Mapping[str, Any],
    *,
    compute: Mapping[str, Any],
    runtime: Mapping[str, Any],
    timings: Mapping[str, Any],
    output_dir: str | Path,
    expected_hashes: Optional[Mapping[str, str]] = None,
    render_exit_code: int = 0,
    status: Optional[str] = None,
    failure_code: Optional[str] = None,
) -> dict[str, Any]:
    """Construct a result from observed worker evidence and output files.

    Missing or zero-byte expected outputs raise ``ContractError`` with
    ``failure_code == 'MISSING_OUTPUT'``.  This prevents callers from turning
    an incomplete output directory into a passed result by accident.
    """
    if not validate_request(request):
        raise ContractError("CONTRACT_INVALID", "request is not schema-valid")
    observed_runtime = _normalise_observed_runtime(runtime)
    normalised_compute = _normalise_compute(compute)
    timing_values = {name: timings.get(name) for name in ("prepare", "render", "total")}
    if any(not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value) or value < 0
           for value in timing_values.values()):
        raise ContractError("CONTRACT_INVALID", "prepare, render, and total timings must be non-negative numbers")
    root = Path(output_dir)
    artifacts = _collect_artifacts(root)
    by_name = {item["path"]: item for item in artifacts}
    missing = [name for name in request["expected_artifacts"]
               if name not in by_name or by_name[name]["size_bytes"] == 0]
    if missing:
        raise ContractError("MISSING_OUTPUT", ", ".join(missing))

    selected_failure = failure_code
    if render_exit_code != 0:
        selected_failure = "RENDER_NONZERO_EXIT"
    elif request["require_gpu"] and not normalised_compute["gpu_evidence"]["verdict"]:
        selected_failure = "GPU_REQUIRED"
    elif expected_hashes:
        mismatches = [name for name, expected in expected_hashes.items()
                      if name not in by_name or by_name[name]["sha256"] != expected]
        if mismatches:
            selected_failure = "ARTIFACT_HASH_MISMATCH"
    if selected_failure is not None and selected_failure not in FAILURE_CODES:
        raise ContractError("CONTRACT_INVALID", f"unknown failure code: {selected_failure}")
    selected_status = "failed" if selected_failure else (status or "passed")
    if selected_status not in ("passed", "failed"):
        raise ContractError("CONTRACT_INVALID", "status must be passed or failed")
    if selected_status == "passed" and selected_failure:
        raise ContractError("CONTRACT_INVALID", "a failed result cannot claim passed")
    result = {
        "schema_version": SCHEMA_VERSION,
        "job_id": job_id(request),
        "request_id": request["request_id"],
        "attempt_id": request["attempt_id"],
        "status": selected_status,
        "failure_code": selected_failure,
        "compute": normalised_compute,
        "runtime": observed_runtime,
        "timings": {name: float(value) for name, value in timing_values.items()},
        "artifacts": artifacts,
    }
    if not validate_result(result):
        raise ContractError("CONTRACT_INVALID", "constructed result failed its JSON Schema")
    return result

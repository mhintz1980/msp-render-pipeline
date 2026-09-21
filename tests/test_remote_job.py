import copy
import hashlib
import importlib
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

from msp_render_cli.remote_job import (
    ContractError,
    MIN_SOLO_GPU_MIB,
    build_request,
    build_result,
    gpu_process_evidence,
    job_id,
    validate_request,
    validate_result,
)

ROOT = Path(__file__).resolve().parents[1]


class RemoteJobContractTests(unittest.TestCase):
    def request(self, require_gpu=False):
        return build_request(
            manifest={"job_id": "fixture", "camera": {"preset": "P1_FRONT_ISO"}},
            input_assets={"prepared.blend": "a" * 64},
            runtime={"blender_version": "5.1.1", "image": "msp:fixture", "build": "build-a", "device": "GPU"},
            render_settings={"engine": "CYCLES", "samples": 8, "width": 16, "height": 16},
            expected_artifacts=["beauty.png"],
            require_gpu=require_gpu,
            request_id="request-a",
            attempt_id="attempt-a",
        )

    def compute(self, verdict=True, samples=None):
        return {
            "enabled_devices": [{"name": "NVIDIA L4", "type": "CUDA"}],
            "cpu_in_mix": False,
            "gpu_evidence": {"verdict": verdict, "samples": samples or []},
        }

    def write_output(self, root, content=b"pixels"):
        (root / "beauty.png").write_bytes(content)

    def test_valid_request_and_result_round_trip(self):
        request = self.request()
        self.assertTrue(validate_request(request))
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.write_output(root)
            result = build_result(
                request,
                compute=self.compute(),
                runtime={"version": "5.1.1", "image": "msp:observed", "build": "build-observed"},
                timings={"prepare": 1, "render": 2.5, "total": 3.5},
                output_dir=root,
            )
        self.assertEqual(result["status"], "passed")
        self.assertTrue(validate_result(result))

    def test_identity_changes_for_each_pinned_field(self):
        request = self.request()
        cases = []
        changed = copy.deepcopy(request)
        changed["manifest"]["canonical_json"] = '{"job_id":"other"}'
        cases.append(changed)
        changed = copy.deepcopy(request)
        changed["input_assets"][0]["sha256"] = "b" * 64
        cases.append(changed)
        changed = copy.deepcopy(request)
        changed["runtime"]["build"] = "build-b"
        cases.append(changed)
        changed = copy.deepcopy(request)
        changed["render_settings"]["canonical_json"] = '{"samples":9}'
        cases.append(changed)
        changed = copy.deepcopy(request)
        changed["expected_artifacts"] = ["mask.png"]
        cases.append(changed)
        changed = copy.deepcopy(request)
        changed["require_gpu"] = True
        cases.append(changed)
        original = job_id(request)
        for mutation in cases:
            self.assertNotEqual(original, job_id(mutation))

    def test_identity_excludes_attempt_submission_timestamp_and_output_path(self):
        request = self.request()
        original = job_id(request)
        for field, value in (
            ("request_id", "request-b"),
            ("attempt_id", "attempt-b"),
            ("submission_id", "submission-b"),
            ("submitted_at", "2026-09-15T12:00:00Z"),
            ("output_dir", "C:/different/output"),
        ):
            changed = copy.deepcopy(request)
            changed[field] = value
            self.assertEqual(original, job_id(changed), field)

    def test_schema_mutations_fail(self):
        request = self.request()
        mutations = []
        unknown = copy.deepcopy(request)
        unknown["unknown"] = True
        mutations.append(unknown)
        missing = copy.deepcopy(request)
        del missing["runtime"]
        mutations.append(missing)
        wrong_type = copy.deepcopy(request)
        wrong_type["require_gpu"] = "true"
        mutations.append(wrong_type)
        for mutation in mutations:
            self.assertFalse(validate_request(mutation))

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.write_output(root)
            result = build_result(
                request,
                compute=self.compute(),
                runtime={"version": "5.1.1", "image": "msp:observed", "build": "build-observed"},
                timings={"prepare": 1, "render": 2, "total": 3},
                output_dir=root,
            )
        bad_code = copy.deepcopy(result)
        bad_code["failure_code"] = "NOT_A_FAILURE"
        self.assertFalse(validate_result(bad_code))
        negative = copy.deepcopy(result)
        negative["timings"]["render"] = -1
        self.assertFalse(validate_result(negative))
        missing_result_field = copy.deepcopy(result)
        del missing_result_field["compute"]
        self.assertFalse(validate_result(missing_result_field))

    def test_required_gpu_without_evidence_is_failed(self):
        request = self.request(require_gpu=True)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.write_output(root)
            result = build_result(
                request,
                compute=self.compute(verdict=False),
                runtime={"version": "5.1.1", "image": "msp:observed", "build": "build-observed"},
                timings={"prepare": 1, "render": 2, "total": 3},
                output_dir=root,
            )
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["failure_code"], "GPU_REQUIRED")

    def test_sole_compute_app_memory_floor_is_honest(self):
        sample = lambda memory: [{"seconds": 1.0, "processes": f"1, /bin/dumb-init, {memory}"}]
        self.assertTrue(gpu_process_evidence(sample(814)))
        self.assertFalse(gpu_process_evidence(sample(MIN_SOLO_GPU_MIB - 156)))

    def test_required_gpu_sole_compute_app_814_mib_passes(self):
        request = self.request(require_gpu=True)
        samples = [{"seconds": 1.0, "processes": "1, /bin/dumb-init, 814"}]
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.write_output(root)
            result = build_result(
                request,
                compute=self.compute(verdict=False, samples=samples),
                runtime={"version": "5.1.1", "image": "msp:observed", "build": "build-observed"},
                timings={"prepare": 1, "render": 2, "total": 3},
                output_dir=root,
            )
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["compute"]["gpu_evidence"]["peak_gpu_memory_mib"], 814)

    def test_required_gpu_sole_compute_app_100_mib_fails(self):
        request = self.request(require_gpu=True)
        samples = [{"seconds": 1.0, "processes": "1, /bin/dumb-init, 100"}]
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.write_output(root)
            result = build_result(
                request,
                compute=self.compute(verdict=False, samples=samples),
                runtime={"version": "5.1.1", "image": "msp:observed", "build": "build-observed"},
                timings={"prepare": 1, "render": 2, "total": 3},
                output_dir=root,
            )
        self.assertEqual(result["failure_code"], "GPU_REQUIRED")

    def test_empty_enabled_devices_without_key_report_cpu_in_mix(self):
        # An empty enabled list is the silent CPU fallback; an omitted key must
        # not be normalised into an honest-looking GPU-only mix.
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.write_output(root)
            result = build_result(
                self.request(),
                compute={"enabled_devices": []},
                runtime={"version": "5.1.1", "image": "msp:observed", "build": "build-observed"},
                timings={"prepare": 1, "render": 2, "total": 3},
                output_dir=root,
            )
        self.assertIs(result["compute"]["cpu_in_mix"], True)

    def test_explicit_cpu_in_mix_false_override_still_honored(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.write_output(root)
            result = build_result(
                self.request(),
                compute={"enabled_devices": [{"name": "NVIDIA L4", "type": "CUDA"}],
                         "cpu_in_mix": False},
                runtime={"version": "5.1.1", "image": "msp:observed", "build": "build-observed"},
                timings={"prepare": 1, "render": 2, "total": 3},
                output_dir=root,
            )
        self.assertIs(result["compute"]["cpu_in_mix"], False)

    def test_sustained_is_window_minimum_and_peak_is_maximum(self):
        # 814 MiB held across the window; 1.6 GiB seen only during BVH build.
        samples = [{"seconds": 1.0, "processes": "1, /bin/dumb-init, 814"},
                   {"seconds": 2.0, "processes": "1, /bin/dumb-init, 1660"}]
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.write_output(root)
            result = build_result(
                self.request(require_gpu=True),
                compute=self.compute(verdict=False, samples=samples),
                runtime={"version": "5.1.1", "image": "msp:observed", "build": "build-observed"},
                timings={"prepare": 1, "render": 2, "total": 3},
                output_dir=root,
            )
        evidence = result["compute"]["gpu_evidence"]
        self.assertEqual(evidence["peak_gpu_memory_mib"], 1660)
        self.assertEqual(evidence["sustained_gpu_memory_mib"], 814)

    def test_missing_output_raises(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ContractError, "MISSING_OUTPUT"):
                build_result(
                    self.request(),
                    compute=self.compute(),
                    runtime={"version": "5.1.1", "image": "msp:observed", "build": "build-observed"},
                    timings={"prepare": 1, "render": 2, "total": 3},
                    output_dir=temp,
                )

    def test_zero_length_output_raises(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.write_output(root, b"")
            with self.assertRaisesRegex(ContractError, "MISSING_OUTPUT"):
                build_result(
                    self.request(),
                    compute=self.compute(),
                    runtime={"version": "5.1.1", "image": "msp:observed", "build": "build-observed"},
                    timings={"prepare": 1, "render": 2, "total": 3},
                    output_dir=root,
                )

    def test_artifact_hash_mismatch_is_failed_result(self):
        request = self.request()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.write_output(root)
            result = build_result(
                request,
                compute=self.compute(),
                runtime={"version": "5.1.1", "image": "msp:observed", "build": "build-observed"},
                timings={"prepare": 1, "render": 2, "total": 3},
                output_dir=root,
                expected_hashes={"beauty.png": "0" * 64},
            )
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["failure_code"], "ARTIFACT_HASH_MISMATCH")

    def test_nonzero_render_exit_is_failed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.write_output(root)
            result = build_result(
                self.request(),
                compute=self.compute(),
                runtime={"version": "5.1.1", "image": "msp:observed", "build": "build-observed"},
                timings={"prepare": 1, "render": 2, "total": 3},
                output_dir=root,
                render_exit_code=7,
            )
        self.assertEqual(result["failure_code"], "RENDER_NONZERO_EXIT")

    def test_nan_in_document_is_rejected(self):
        with self.assertRaisesRegex(ContractError, "CONTRACT_INVALID"):
            build_request(
                manifest={"nan": float("nan")},
                input_assets={"asset": "a" * 64},
                runtime={"version": "5.1.1", "image": "msp", "build": "b", "device": "GPU"},
                render_settings={},
                expected_artifacts=["beauty.png"],
            )


class RenderWorkerReportShape(unittest.TestCase):
    """render_worker.py writes render-report.json with no `gpu_evidence` key at all —
    it cannot sample nvidia-smi for itself. These pin the contract side of that."""

    request = RemoteJobContractTests.request
    write_output = RemoteJobContractTests.write_output

    def worker_compute(self, cpu_in_mix=False):
        return {"enabled_devices": [{"name": "NVIDIA L4", "type": "OPTIX"}], "cpu_in_mix": cpu_in_mix}

    def test_a_required_gpu_job_cannot_pass_on_the_worker_report_alone(self):
        request = self.request(require_gpu=True)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.write_output(root)
            result = build_result(
                request,
                compute=self.worker_compute(),
                runtime={"version": "5.1.1", "image": "msp:observed", "build": "build-observed"},
                timings={"prepare": 1, "render": 2, "total": 3},
                output_dir=root,
            )
        # An enabled OPTIX device is what was asked for, not proof that it rendered.
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["failure_code"], "GPU_REQUIRED")

    def test_worker_report_without_gpu_evidence_still_validates(self):
        request = self.request(require_gpu=False)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.write_output(root)
            result = build_result(
                request,
                compute=self.worker_compute(cpu_in_mix=True),
                runtime={"version": "5.1.1", "image": "msp:observed", "build": "build-observed"},
                timings={"prepare": 1, "render": 2, "total": 3},
                output_dir=root,
            )
        self.assertEqual(result["status"], "passed")
        self.assertTrue(validate_result(result))
        self.assertFalse(result["compute"]["gpu_evidence"]["verdict"])


class _StubDevicePreferences:
    """No backend exposes a device, so Cycles finds nothing to enable."""

    def __init__(self):
        self.compute_device_type = None
        self.devices = []

    def get_devices(self):
        return []


class RenderWorkerGpuRequiredTests(unittest.TestCase):
    """execute_render_job normally runs inside Blender; against a stubbed bpy it
    still exercises the GPU_REQUIRED raise and the render-report construction."""

    @classmethod
    def setUpClass(cls):
        cls._module_state = {name: sys.modules.get(name) for name in ("bpy", "mathutils")}
        # A module-level render_worker import from another test class (e.g.
        # test_floor_mode) ran before this stub existed and froze bpy=None.
        # Re-import under the stub so the class always tests stubbed Blender.
        sys.modules.pop("render_worker", None)
        scene = types.SimpleNamespace(
            objects=[],
            world=None,
            render=types.SimpleNamespace(
                engine="", filepath="", resolution_x=0, resolution_y=0,
                film_transparent=False,
                image_settings=types.SimpleNamespace(file_format="", color_mode="")),
            cycles=types.SimpleNamespace(samples=0, use_denoising=False,
                                         device="CPU", denoiser=None),
        )
        bpy_stub = types.SimpleNamespace(
            context=types.SimpleNamespace(
                scene=scene,
                preferences=types.SimpleNamespace(
                    addons={"cycles": types.SimpleNamespace(preferences=_StubDevicePreferences())})),
            # bytes, because that is what Blender hands back. The previous `str`
            # stub was the only thing that ever exercised _render_report, which
            # is why a TypeError on every real render slipped past 106 tests.
            app=types.SimpleNamespace(version_string="5.1.1",
                                      build_hash=b"b70da489d7f4",
                                      version=(5, 1, 1)),
            ops=types.SimpleNamespace(
                wm=types.SimpleNamespace(open_mainfile=lambda filepath: None)),
            data=types.SimpleNamespace(objects=[]),
        )
        sys.modules["bpy"] = bpy_stub
        sys.modules["mathutils"] = types.ModuleType("mathutils")
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        cls.render_worker = importlib.import_module("render_worker")

    @classmethod
    def tearDownClass(cls):
        for name, module in cls._module_state.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module
        # Drop the stub-bound re-import so later importers see bpy=None again.
        sys.modules.pop("render_worker", None)

    def stub_render_op(self, worker):
        """Give the shared bpy stub a no-op render operator for this test only.

        The stub is built once in setUpClass, so assigning to it directly would
        leak into every later test in the class.
        """
        patcher = patch.object(worker.bpy.ops, "render",
                               types.SimpleNamespace(render=lambda **kwargs: None),
                               create=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def manifest(self, root, require_gpu):
        blend = root / "fixture.blend"
        blend.write_bytes(b"BLENDER" + b"\x00" * 24)
        return {
            "job_id": "render-worker-stub",
            "cad_source": {"file_path": str(blend), "format": "blend"},
            "camera": {"preset": "P1_FRONT_ISO"},
            "livery": {"preset": "preserve_existing"},
            "lighting": {"preset": "studio_dark"},
            "output": {"engine": "CYCLES", "width": 8, "height": 8,
                       "output_dir": str(root / "out")},
            "require_gpu": require_gpu,
        }

    def test_require_gpu_without_enabled_gpu_raises_before_report_write(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            manifest = self.manifest(root, require_gpu=True)
            worker = self.render_worker
            with patch.object(worker, "get_scene_bounds", lambda: (None, 1.0)), \
                 patch.object(worker, "setup_camera", lambda *args, **kwargs: None), \
                 patch.object(worker, "setup_lighting", lambda *args, **kwargs: None):
                with self.assertRaises(RuntimeError) as ctx:
                    worker.execute_render_job(manifest)
            # The for-else raise must reach the caller with a single prefix, not
            # the "GPU_REQUIRED: GPU_REQUIRED: ..." double-wrap.
            message = str(ctx.exception)
            self.assertTrue(message.startswith("GPU_REQUIRED"), message)
            self.assertFalse(message.startswith("GPU_REQUIRED: GPU_REQUIRED"), message)
            self.assertFalse((root / "out" / "render-report.json").exists())

    def test_render_report_helper_with_no_gpu_devices_reports_cpu_in_mix(self):
        report = self.render_worker._render_report([], True, 0.5, 2.0, 2.5)
        self.assertEqual(report["compute"]["enabled_devices"], [])
        self.assertIs(report["compute"]["cpu_in_mix"], True)
        self.assertNotIn("gpu_evidence", report["compute"])
        self.assertEqual(report["timings"], {"prepare": 0.5, "render": 2.0, "total": 2.5})

    def test_render_report_is_json_serialisable_with_a_bytes_build_hash(self):
        """Blender's bpy.app.build_hash is bytes. Undecoded it raised TypeError
        mid-write and left render-report.json truncated at 158 bytes."""
        report = self.render_worker._render_report([], True, 0.5, 2.0, 2.5)
        self.assertEqual(report["runtime"]["build"], "b70da489d7f4")
        self.assertIsInstance(report["runtime"]["build"], str)
        # The exact call the worker makes. It must not raise.
        payload = json.dumps(report, sort_keys=True, allow_nan=False)
        self.assertEqual(json.loads(payload), report)

    def test_written_render_report_round_trips_through_json_load(self):
        """The file the dispatching harness opens must parse, not just the dict."""
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            manifest = self.manifest(root, require_gpu=False)
            worker = self.render_worker
            with patch.object(worker, "get_scene_bounds", lambda: (None, 1.0)), \
                 patch.object(worker, "setup_camera", lambda *args, **kwargs: None), \
                 patch.object(worker, "setup_lighting", lambda *args, **kwargs: None), \
                 patch.object(worker, "apply_photoreal_pass", lambda *a, **k: None), \
                 patch.object(worker, "write_matte_pass", lambda *a, **k: None):
                self.stub_render_op(worker)
                worker.execute_render_job(manifest)

            written = root / "out" / "render-report.json"
            self.assertTrue(written.is_file(), "no render-report.json was written")
            loaded = json.loads(written.read_text(encoding="utf-8"))
            self.assertEqual(loaded["runtime"]["build"], "b70da489d7f4")
            self.assertEqual(loaded["runtime"]["blender_version"], "5.1.1")
            self.assertIn("timings", loaded)

    def test_build_hash_text_tolerates_str_and_missing_values(self):
        decode = self.render_worker._build_hash_text
        self.assertEqual(decode(b"b70da489d7f4"), "b70da489d7f4")
        self.assertEqual(decode("already-text"), "already-text")
        self.assertEqual(decode(None), "unknown")
        self.assertEqual(decode(b""), "unknown")

    def test_an_unserialisable_report_leaves_no_truncated_file(self):
        """The original defect wrote 158 valid bytes and then raised. A partial
        report is worse than none: _collect_artifacts excludes render-report.json
        from artifact hashing, so nothing downstream would catch the truncation."""
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            manifest = self.manifest(root, require_gpu=False)
            worker = self.render_worker
            poisoned = dict(worker._render_report([], True, 0.5, 2.0, 2.5))
            poisoned["runtime"] = {"build": object()}  # not JSON-serialisable
            with patch.object(worker, "get_scene_bounds", lambda: (None, 1.0)), \
                 patch.object(worker, "setup_camera", lambda *args, **kwargs: None), \
                 patch.object(worker, "setup_lighting", lambda *args, **kwargs: None), \
                 patch.object(worker, "apply_photoreal_pass", lambda *a, **k: None), \
                 patch.object(worker, "write_matte_pass", lambda *a, **k: None), \
                 patch.object(worker, "_render_report", lambda *a, **k: poisoned):
                self.stub_render_op(worker)
                with self.assertRaises(TypeError):
                    worker.execute_render_job(manifest)
            # It must fail loudly AND leave nothing corrupt behind.
            self.assertFalse((root / "out" / "render-report.json").exists())


if __name__ == "__main__":
    unittest.main()

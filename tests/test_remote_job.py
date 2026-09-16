import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

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


if __name__ == "__main__":
    unittest.main()


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

"""Transport preflight must fail locally before a billable function is created."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("cloud_parity", ROOT / "scripts/cloud_parity.py")
cloud = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cloud)


class PreflightTests(unittest.TestCase):
    def fixture(self, root, inputs):
        (root / "payload").mkdir()
        (root / "payload/inputs.json").write_text(json.dumps(inputs))
        (root / "scene-parity-report.json").write_text(json.dumps({"inputs": inputs}))
        (root / "scene-parity-profile.json").write_text("{}")

    def test_unlisted_file_cannot_be_uploaded(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.fixture(root, {})
            (root / "payload/secret.txt").write_text("never upload")
            with self.assertRaisesRegex(ValueError, "UNDECLARED_PAYLOAD_FILE"):
                cloud.preflight(root)

    def test_tampered_input_rejected_before_import(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.fixture(root, {"prepared.blend": "0" * 64})
            (root / "payload/prepared.blend").write_bytes(b"tampered")
            with patch.object(cloud, "load_verifier") as load:
                with self.assertRaisesRegex(ValueError, "INPUT_HASH_MISMATCH"):
                    cloud.preflight(root)
                load.assert_not_called()

    def test_inventory_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.fixture(root, {})
            (root / "payload/inputs.json").write_text('{"unexpected": "abc"}')
            with self.assertRaisesRegex(ValueError, "INPUT_INVENTORY_MISMATCH"):
                cloud.preflight(root)


class GpuProcessEvidenceTests(unittest.TestCase):
    def sample(self, processes):
        return {"seconds": 1.0, "processes": processes}

    def test_named_blender_process_accepted(self):
        self.assertTrue(cloud.gpu_process_evidence(
            [self.sample("4212, blender, 512")]))

    def test_pid_namespace_init_binary_accepted_with_substantial_memory(self):
        samples = [self.sample("1, /bin/dumb-init, 10"), self.sample("1, /bin/dumb-init, 814")]
        self.assertTrue(cloud.gpu_process_evidence(samples))

    def test_sole_app_below_memory_floor_rejected(self):
        self.assertFalse(cloud.gpu_process_evidence(
            [self.sample("1, /bin/dumb-init, 10")]))

    def test_second_compute_app_rejected(self):
        samples = [self.sample("1, /bin/dumb-init, 814"), self.sample("1, /bin/dumb-init, 814\n9, Xorg, 96")]
        self.assertFalse(cloud.gpu_process_evidence(samples))

    def test_unreadable_memory_and_no_samples_rejected(self):
        self.assertFalse(cloud.gpu_process_evidence([self.sample("1, /bin/dumb-init, [N/A]")]))
        self.assertFalse(cloud.gpu_process_evidence([]))


if __name__ == "__main__":
    unittest.main()

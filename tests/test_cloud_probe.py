"""Pure device-policy checks; no Blender or cloud account required."""

import contextlib
import importlib.util
import io
from pathlib import Path
import unittest
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location(
    "cloud_blender_probe", Path(__file__).resolve().parents[1] / "scripts/cloud_blender_probe.py"
)
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)


def device(kind, enabled=True):
    return {"name": kind, "id": kind + "-0", "type": kind, "enabled": enabled}


class GpuInventoryTests(unittest.TestCase):
    def test_empty_inventory_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "GPU_REQUIRED"):
            probe.validate_gpu_inventory([], "OPTIX")

    def test_cpu_only_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "GPU_REQUIRED"):
            probe.validate_gpu_inventory([device("CPU")], "CUDA")

    def test_mixed_gpu_cpu_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "GPU_REQUIRED"):
            probe.validate_gpu_inventory([device("OPTIX"), device("CPU")], "OPTIX")

    def test_supported_gpu_with_disabled_cpu_passes(self):
        for backend in ("OPTIX", "CUDA"):
            with self.subTest(backend=backend):
                gpu = device(backend)
                self.assertEqual(probe.validate_gpu_inventory(
                    [gpu, device("CPU", enabled=False)], backend), [gpu])

    def test_mismatched_or_disabled_gpu_rejected(self):
        for inventory, backend in (([device("CUDA")], "OPTIX"),
                                   ([device("OPTIX", enabled=False)], "OPTIX"),
                                   ([device("HIP")], "HIP")):
            with self.subTest(inventory=inventory, backend=backend):
                with self.assertRaisesRegex(RuntimeError, "GPU_REQUIRED"):
                    probe.validate_gpu_inventory(inventory, backend)

    def test_negative_control_uses_guard_without_output_access(self):
        stderr = io.StringIO()
        with patch.object(probe, "validate_gpu_inventory",
                          wraps=probe.validate_gpu_inventory) as guard:
            with patch.object(probe, "Path", side_effect=AssertionError("output accessed")):
                with contextlib.redirect_stderr(stderr):
                    self.assertEqual(probe.main(["--force-no-gpu"]), 1)
            guard.assert_called_once_with([], "OPTIX")
        self.assertIn("GPU_REQUIRED", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()

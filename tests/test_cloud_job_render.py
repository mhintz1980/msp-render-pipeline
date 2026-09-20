"""The preview dispatcher must build honest frames before any billable call."""
import importlib.util
import json
from pathlib import Path
import re
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("cloud_job_render", ROOT / "scripts/cloud_job_render.py")
cloud = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cloud)


def job_fixture(root):
    """A minimal jobs/-shaped tree so frame_plan resolves paths like production."""
    (root / "jobs").mkdir()
    (root / "cad").mkdir()
    (root / "backgrounds").mkdir()
    (root / "cad/machine.blend").write_bytes(b"blend")
    (root / "backgrounds/env_softbox.png").write_bytes(b"env")
    (root / "backgrounds/env_white.png").write_bytes(b"plate")
    manifest = {
        "job_id": "fixture_job",
        "cad_source": {"file_path": "cad/machine.blend"},
        "camera": {"azimuth_deg": 42.0},
        "lighting": {"hdri_path": "backgrounds/env_softbox.png"},
        "compositing": {"enabled": True, "background_plate": "backgrounds/env_white.png",
                        "shadow_opacity": 0.0, "product_offset_pct": [0.0, -0.02]},
        "output": {"output_dir": "./output/fixture"},
    }
    manifest_path = root / "jobs/fixture_job.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return manifest, manifest_path


class FrameManifestTests(unittest.TestCase):
    def test_override_leaves_the_source_manifest_untouched(self):
        manifest, _ = job_fixture(Path(tempfile.mkdtemp()))
        frame = cloud.frame_manifest(manifest, 222, "/output/frame-az222")
        self.assertEqual(frame["camera"]["azimuth_deg"], 222.0)
        self.assertEqual(manifest["camera"]["azimuth_deg"], 42.0)
        self.assertEqual(manifest.get("require_gpu"), None)

    def test_frame_is_gpu_required_with_absolute_container_paths(self):
        manifest, _ = job_fixture(Path(tempfile.mkdtemp()))
        frame = cloud.frame_manifest(manifest, 222, "/output/frame-az222")
        self.assertTrue(frame["require_gpu"])
        self.assertEqual(frame["output"]["output_dir"], "/output/frame-az222")
        self.assertEqual(frame["cad_source"]["file_path"], "/input/cad/machine.blend")
        self.assertEqual(frame["lighting"]["hdri_path"],
                         "/input/backgrounds/env_softbox.png")
        self.assertEqual(frame["job_id"], "fixture_job-az222")


class FramePlanTests(unittest.TestCase):
    def test_plan_mounts_worker_cad_and_hdri_and_keeps_compositing_local(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            manifest, manifest_path = job_fixture(root)
            plan = cloud.frame_plan(manifest_path, [42.0, 222.0])
            self.assertEqual(plan["job_id"], "fixture_job")
            self.assertEqual([f["camera"]["azimuth_deg"] for f in plan["frames"]],
                             [42.0, 222.0])
            # Worker, CAD and HDRI go to the container; the plate stays local.
            self.assertEqual(plan["mounts"]["render_worker.py"],
                             str(ROOT / "render_worker.py"))
            self.assertEqual(plan["cad_mount"], "/input/cad/machine.blend")
            self.assertEqual(plan["hdri_mount"], "/input/backgrounds/env_softbox.png")
            self.assertEqual(plan["plate_path"], str(root / "backgrounds/env_white.png"))
            self.assertEqual(plan["compositing"]["product_offset_pct"], [0.0, -0.02])


class PinTests(unittest.TestCase):
    def test_runtime_pins_match_the_frozen_verifier(self):
        source = (ROOT / "scripts/verify_scene.py").read_text(encoding="utf-8")
        for constant, module_value in (("VERSION", cloud.BLENDER_VERSION),
                                       ("BUILD", cloud.BLENDER_BUILD),
                                       ("ARCHIVE_SHA256", cloud.BLENDER_ARCHIVE_SHA256)):
            frozen = re.search(rf'^{constant} = "([^"]+)"', source, re.MULTILINE).group(1)
            self.assertEqual(module_value, frozen, constant)


class EstimateTests(unittest.TestCase):
    def test_estimate_is_one_cold_start_plus_frames_at_recorded_rates(self):
        per_second = (cloud.GPU_RATE_PER_S + 4 * cloud.CPU_RATE_PER_CORE_S
                      + 16 * cloud.MEMORY_RATE_PER_GIB_S)
        self.assertAlmostEqual(per_second, 0.00030992, places=8)
        self.assertEqual(cloud.estimate_cost_usd([101.65, 101.65]),
                         round((cloud.COLD_START_SECONDS + 203.3) * per_second, 4))


class CommandTests(unittest.TestCase):
    def test_blender_command_carries_the_proven_flag_set(self):
        command = cloud.blender_command("/input/manifest-az42.json")
        self.assertEqual(command[:5], ["/opt/blender/blender", "--background",
                                       "--factory-startup", "--disable-autoexec",
                                       "--python-exit-code"])
        self.assertEqual(command[-2:], ["--", "/input/manifest-az42.json"])


class CompositeSettingsTests(unittest.TestCase):
    def test_settings_drop_exactly_the_non_kwargs(self):
        settings = cloud.composite_settings({"enabled": True,
                                             "background_plate": "backgrounds/x.png",
                                             "shadow_opacity": 0.0,
                                             "product_scale": 1.0})
        self.assertEqual(settings, {"shadow_opacity": 0.0, "product_scale": 1.0})


if __name__ == "__main__":
    unittest.main()

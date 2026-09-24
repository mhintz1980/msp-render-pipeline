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
            # The mounts must carry exactly the container destinations the
            # frame manifests reference - anything else is a FileNotFoundError
            # at container start (the 2026-09-20 run2 failure).
            self.assertEqual(plan["mounts"]["/input/render_worker.py"],
                             str(ROOT / "render_worker.py"))
            self.assertEqual(plan["mounts"][plan["cad_mount"]],
                             str(root / "cad/machine.blend"))
            self.assertEqual(plan["mounts"][plan["hdri_mount"]],
                             str(root / "backgrounds/env_softbox.png"))
            self.assertEqual(plan["cad_mount"], "/input/cad/machine.blend")
            self.assertEqual(plan["hdri_mount"], "/input/backgrounds/env_softbox.png")
            self.assertEqual(plan["plate_path"], str(root / "backgrounds/env_white.png"))
            self.assertEqual(plan["compositing"]["product_offset_pct"], [0.0, -0.02])


    def test_a_missing_local_input_fails_at_plan_time(self):
        # A typo'd --set value (e.g. .json for the plate) must fail before a
        # billable call, not after the GPU has rendered an uncompositable frame.
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            manifest, manifest_path = job_fixture(root)
            (root / "backgrounds/env_white.png").unlink()
            with self.assertRaisesRegex(ValueError, "MISSING_INPUT"):
                cloud.frame_plan(manifest_path, [42.0],
                                 ["compositing.background_plate=backgrounds/env_white.png"])


class PinTests(unittest.TestCase):
    def test_runtime_pins_match_the_frozen_verifier(self):
        source = (ROOT / "scripts/verify_scene.py").read_text(encoding="utf-8")
        for constant, module_value in (("VERSION", cloud.BLENDER_VERSION),
                                       ("BUILD", cloud.BLENDER_BUILD),
                                       ("ARCHIVE_SHA256", cloud.BLENDER_ARCHIVE_SHA256)):
            frozen = re.search(rf'^{constant} = "([^"]+)"', source, re.MULTILINE).group(1)
            self.assertEqual(module_value, frozen, constant)


class OverrideTests(unittest.TestCase):
    def test_nested_override_parses_numbers_and_keeps_paths_as_strings(self):
        manifest = {"camera": {"depth_of_field": {"f_stop": 11.0}},
                    "compositing": {"background_plate": "backgrounds/a.png",
                                    "shadow_opacity": 0.0},
                    "require_gpu": True}
        cloud.apply_overrides(manifest, ["camera.depth_of_field.f_stop=3.2",
                                         "compositing.shadow_opacity=0.35",
                                         "compositing.background_plate=backgrounds/b.png",
                                         "require_gpu=false"])
        self.assertEqual(manifest["camera"]["depth_of_field"]["f_stop"], 3.2)
        self.assertEqual(manifest["compositing"]["shadow_opacity"], 0.35)
        self.assertEqual(manifest["compositing"]["background_plate"],
                         "backgrounds/b.png")
        self.assertIs(manifest["require_gpu"], False)

    def test_a_key_the_manifest_does_not_have_is_rejected(self):
        # Strict on purpose: a typo'd --set must fail locally, not silently
        # render the unmodified job on a billable GPU.
        manifest = {"camera": {"azimuth_deg": 42.0}}
        with self.assertRaisesRegex(ValueError, "UNKNOWN_OVERRIDE_PATH"):
            cloud.apply_overrides(manifest, ["require_gpu=false"])

    def test_unknown_or_malformed_override_fails_before_any_dispatch(self):
        manifest = {"camera": {"azimuth_deg": 42.0}}
        for bad in ("camera.f_stop=3.2", "camera", "=3.2", "camera.azimuth_deg="):
            with self.assertRaises(ValueError):
                cloud.apply_overrides(manifest, [bad])

    def test_boolean_control_overrides_reject_every_non_boolean_value(self):
        # 3g review F1 (widened per the 3i DeepSeek review's finding 2): the
        # worker reads these controls truthy, so "FALSE" keeps one on and
        # 0/null silently disables it; every non-boolean dies at override
        # time, before a billable call. analytic_lights/shadow_catcher are
        # not creatable-optional, so the fixture carries them present.
        good = {"key_enabled": True, "fill_enabled": True, "rim_enabled": True,
                "analytic_lights": True, "shadow_catcher": True,
                "floor": {"enabled": True}}
        for path in sorted(cloud.BOOLEAN_OVERRIDE_PATHS):
            for raw in ("FALSE", "True", "0", "1", "null"):
                with self.subTest(override=f"{path}={raw}"):
                    manifest = {"lighting": json.loads(json.dumps(good))}
                    with self.assertRaisesRegex(ValueError, "BAD_OVERRIDE_VALUE"):
                        cloud.apply_overrides(manifest, [f"{path}={raw}"])
                    self.assertEqual(manifest, {"lighting": good})

    def test_boolean_control_overrides_accept_exact_json_booleans(self):
        manifest = {"lighting": {"analytic_lights": True,
                                 "shadow_catcher": False,
                                 "floor": {"enabled": True}}}
        cloud.apply_overrides(manifest, ["lighting.key_enabled=false",
                                         "lighting.fill_enabled=true",
                                         "lighting.rim_enabled=false",
                                         "lighting.analytic_lights=false",
                                         "lighting.shadow_catcher=true",
                                         "lighting.floor.enabled=false"])
        self.assertEqual(manifest["lighting"],
                         {"key_enabled": False, "fill_enabled": True,
                          "rim_enabled": False, "analytic_lights": False,
                          "shadow_catcher": True,
                          "floor": {"enabled": False}})

    def test_boolean_control_guard_leaves_other_paths_parsing_as_before(self):
        # Non-optional paths keep the JSON-when-possible, string-otherwise
        # parse: numbers, booleans and path strings all still land (F1 must
        # not narrow the general override grammar).
        manifest = {"camera": {"depth_of_field": {"f_stop": 11.0}},
                    "require_gpu": True}
        cloud.apply_overrides(manifest, ["camera.depth_of_field.f_stop=3.2",
                                         "require_gpu=false"])
        self.assertEqual(manifest["camera"]["depth_of_field"]["f_stop"], 3.2)
        self.assertIs(manifest["require_gpu"], False)

    def test_overrides_reach_the_frame_manifests(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            manifest, manifest_path = job_fixture(root)
            plan = cloud.frame_plan(manifest_path, [42.0],
                                    ["compositing.shadow_opacity=0.35"])
            self.assertEqual(plan["compositing"]["shadow_opacity"], 0.35)
            # The source job file on disk is untouched.
            self.assertEqual(json.loads(manifest_path.read_text())["compositing"]
                             ["shadow_opacity"], manifest["compositing"]["shadow_opacity"])


class EstimateTests(unittest.TestCase):
    def test_estimate_is_one_cold_start_plus_frames_at_recorded_rates(self):
        per_second = (cloud.GPU_RATE_PER_S + 4 * cloud.CPU_RATE_PER_CORE_S
                      + 16 * cloud.MEMORY_RATE_PER_GIB_S)
        self.assertAlmostEqual(per_second, 0.00030992, places=8)
        self.assertEqual(cloud.estimate_cost_usd([101.65, 101.65]),
                         round((cloud.COLD_START_SECONDS + 203.3) * per_second, 4))


class OrbitTests(unittest.TestCase):
    def test_orbit_is_count_unique_azimuths_without_the_wrap_repeat(self):
        for count in (2, 3, 30, 100, 300):
            with self.subTest(count=count):
                azimuths = cloud.orbit_azimuths(count)
                self.assertEqual(len(azimuths), count)
                keys = [round(a % 360.0, 3) for a in azimuths]
                self.assertEqual(len(set(keys)), count)
                self.assertNotEqual(keys[-1], keys[0])

    def test_orbit_starts_at_the_declared_azimuth_with_uniform_steps(self):
        azimuths = cloud.orbit_azimuths(30)
        self.assertEqual(azimuths[0], 42.0)
        steps = [round(b - a, 3) for a, b in zip(azimuths, azimuths[1:])]
        self.assertEqual(set(steps), {round(360.0 / 30, 3)})

    def test_counts_below_two_are_rejected(self):
        for count in (0, 1, -3):
            with self.subTest(count=count):
                with self.assertRaisesRegex(ValueError, "^BAD_ORBIT_COUNT:"):
                    cloud.orbit_azimuths(count)


class RejectDuplicateAzimuthTests(unittest.TestCase):
    def test_exact_repeat_raises(self):
        with self.assertRaisesRegex(ValueError, "^DUPLICATE_AZIMUTH:"):
            cloud.reject_duplicate_azimuths([42.0, 222.0, 42.0])

    def test_modulo_repeat_raises(self):
        with self.assertRaisesRegex(ValueError, "^DUPLICATE_AZIMUTH:"):
            cloud.reject_duplicate_azimuths([42, 402])

    def test_clean_list_returns_none(self):
        self.assertIsNone(
            cloud.reject_duplicate_azimuths(cloud.orbit_azimuths(30)))

    def test_frame_plan_refuses_a_duplicate_before_any_billable_call(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _, manifest_path = job_fixture(root)
            with self.assertRaisesRegex(ValueError, "^DUPLICATE_AZIMUTH:"):
                cloud.frame_plan(manifest_path, [42.0, 42.0])

    def test_two_azimuths_that_name_one_frame_are_a_duplicate(self):
        # 42.0 and 42.4 both label frame-az42: the label is the billing unit,
        # so the gate must key on it, not on the raw floats.
        self.assertTrue(cloud.frame_name(42.0) == cloud.frame_name(42.4))
        with self.assertRaisesRegex(ValueError, "^DUPLICATE_AZIMUTH:"):
            cloud.reject_duplicate_azimuths([42.0, 42.4])
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _, manifest_path = job_fixture(root)
            with self.assertRaisesRegex(ValueError, "^DUPLICATE_AZIMUTH:"):
                cloud.frame_plan(manifest_path, [42.0, 42.4])

    def test_genuinely_distinct_azimuths_still_pass(self):
        self.assertIsNone(cloud.reject_duplicate_azimuths([42.0, 43.0]))

    def test_whole_orbits_survive_the_validator_except_overfull_ones(self):
        for count in (30, 100, 300, 360):
            with self.subTest(count=count):
                self.assertIsNone(
                    cloud.reject_duplicate_azimuths(cloud.orbit_azimuths(count)))
        # 400 frames cannot have unique integer labels: collisions are real.
        with self.assertRaisesRegex(ValueError, "^DUPLICATE_AZIMUTH:"):
            cloud.reject_duplicate_azimuths(cloud.orbit_azimuths(400))


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

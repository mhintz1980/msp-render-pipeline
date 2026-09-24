"""The preview dispatcher must build honest frames before any billable call."""
import hashlib
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


# --- T-V2a: resumable frame dispatch (output/tv2a-resume-spec.md) -----------
#
# A 4.5% GPU-driver crash rate (video-pipeline-brief.md section 6.1) makes a
# 360-frame orbit a coin flip, so a crash must not re-pay the frames already on
# disk. Every resume test below drives main() itself through an injected
# remote, so the code under test is the production path and not a parallel one.


def _png(color, size=(16, 16)):
    """Deterministic PNG bytes - the local compositor needs a real image."""
    import io
    from PIL import Image
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format="PNG")
    return buffer.getvalue()


def _gpu_seen(samples):
    """Stand-in for msp_render_cli.remote_job.gpu_process_evidence."""
    return True


def _frame_result(frame, artifacts, *, status="rendered", gpu_seen=True,
                  request_id="req-1"):
    """The body a successful run leaves in result-<frame>.json."""
    return {"schema_version": 1, "request_id": request_id, "frame": frame,
            "status": status, "failures": [], "gpu_process_samples": [],
            "blender_exit_code": 0, "seconds": 1.0,
            "blender_gpu_process_seen": gpu_seen, "artifacts": artifacts}


def _artifact(name, payload):
    return {name: {"sha256": hashlib.sha256(payload).hexdigest(),
                   "size_bytes": len(payload)}}


def _put_artifact(output, name, payload):
    path = Path(output) / "cloud" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


def _complete_frame(output, frame, payload=b"beauty-bytes", **kwargs):
    """Leave one frame on disk exactly as a finished render leaves it."""
    name = f"frame-{frame}/beauty.png"
    _put_artifact(output, name, payload)
    result = _frame_result(frame, _artifact(name, payload), **kwargs)
    cloud.save(Path(output) / f"result-{frame}.json", result)
    return result


def _plan_frames(count):
    return [{"frame": f"az{index}", "manifest": f"/input/manifest-az{index}.json"}
            for index in range(1, count + 1)]


def _tree_snapshot(root):
    """Every file under root as (mtime_ns, sha) - the no-write assertion."""
    root = Path(root)
    return {str(path.relative_to(root)): (path.stat().st_mtime_ns,
                                          hashlib.sha256(path.read_bytes()).hexdigest())
            for path in sorted(root.rglob("*")) if path.is_file()}


def _cloud_snapshot(root):
    """The downloaded byte tree, path -> digest, for a whole-sequence compare."""
    cloud_dir = Path(root) / "cloud"
    return {str(path.relative_to(cloud_dir)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(cloud_dir.rglob("*")) if path.is_file()}


def _result_artifacts(root):
    artifacts = {}
    for path in sorted(Path(root).glob("result-*.json")):
        result = json.loads(path.read_text(encoding="utf-8"))
        artifacts[result["frame"]] = result["artifacts"]
    return artifacts


def _rendering_remote(calls, fail_at_call=None):
    """worker.remote stand-in: deterministic bytes per frame, optional crash."""
    def remote(frame_request):
        frame = frame_request["frame"]
        calls.append(frame)
        if fail_at_call is not None and len(calls) == fail_at_call:
            raise RuntimeError("simulated GPU driver crash")
        payload = _png((40 + int(frame[2:]), 60, 90))
        name = f"frame-{frame}/beauty.png"
        result = _frame_result(frame, _artifact(name, payload),
                               request_id=frame_request["request_id"])
        return result, {name: payload}
    return remote


def _run(manifest_path, output, remote, *, azimuths="1,2,3,4,5", resume=False,
         overrides=()):
    """main() with the cloud remote replaced: same code path, no Modal."""
    argv = ["--manifest", str(manifest_path),
            "--azimuths", azimuths, "--output-dir", str(output), "--execute"]
    if resume:
        argv.append("--resume")
    for override in overrides:
        argv += ["--set", override]
    # The fixture plate is placeholder bytes; compositing has its own tests.
    real_composite = cloud.run_composite
    cloud.run_composite = lambda frame_dir, *a, **k: str(Path(frame_dir) / "composite.png")
    try:
        return cloud.main(argv, remote, _gpu_seen)
    finally:
        cloud.run_composite = real_composite


class FrameCompleteTests(unittest.TestCase):
    """A frame is done only when its bytes are provably on disk."""

    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.output = Path(self._temp.name)

    def test_a_missing_result_is_incomplete(self):
        complete, reason = cloud.frame_complete(self.output, "az1")
        self.assertFalse(complete)
        self.assertEqual(reason, "missing result")

    def test_corrupt_json_is_incomplete_never_an_exception(self):
        (self.output / "result-az1.json").write_text("{not json", encoding="utf-8")
        complete, reason = cloud.frame_complete(self.output, "az1")
        self.assertFalse(complete)
        self.assertTrue(reason)

    def test_a_failed_status_is_incomplete(self):
        _complete_frame(self.output, "az1", status="failed")
        complete, reason = cloud.frame_complete(self.output, "az1")
        self.assertFalse(complete)
        self.assertEqual(reason, "status failed")

    def test_a_frame_without_gpu_evidence_is_incomplete(self):
        _complete_frame(self.output, "az1", gpu_seen=False)
        complete, reason = cloud.frame_complete(self.output, "az1")
        self.assertFalse(complete)
        self.assertEqual(reason, "no gpu evidence")

    def test_empty_artifacts_is_incomplete(self):
        cloud.save(self.output / "result-az1.json", _frame_result("az1", {}))
        complete, reason = cloud.frame_complete(self.output, "az1")
        self.assertFalse(complete)
        self.assertEqual(reason, "empty artifacts")

    def test_a_missing_artifact_is_incomplete(self):
        _complete_frame(self.output, "az1")
        (self.output / "cloud/frame-az1/beauty.png").unlink()
        complete, reason = cloud.frame_complete(self.output, "az1")
        self.assertFalse(complete)
        self.assertEqual(reason, "artifact missing: frame-az1/beauty.png")

    def test_an_artifact_sha_mismatch_is_incomplete(self):
        _complete_frame(self.output, "az1")
        _put_artifact(self.output, "frame-az1/beauty.png", b"tampered")
        complete, reason = cloud.frame_complete(self.output, "az1")
        self.assertFalse(complete)
        self.assertEqual(reason, "artifact sha mismatch: frame-az1/beauty.png")

    def test_a_verified_frame_is_complete(self):
        _complete_frame(self.output, "az1")
        self.assertEqual(cloud.frame_complete(self.output, "az1"), (True, ""))


class DispatchFramesTests(unittest.TestCase):
    """The per-frame loop, drivable without Modal and unchanged in semantics."""

    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.output = Path(self._temp.name)

    def _remote(self, calls, *, status_for=None, declare_shas=True, identity=True):
        def remote(frame_request):
            frame = frame_request["frame"]
            calls.append(frame)
            payload = b"bytes-" + frame.encode()
            name = f"frame-{frame}/beauty.png"
            declared = (_artifact(name, payload) if declare_shas
                        else _artifact(name, b"some other bytes"))
            result = _frame_result(
                frame, declared,
                status=(status_for or (lambda name: "rendered"))(frame),
                request_id=(frame_request["request_id"] if identity else "not-me"))
            return result, {name: payload}
        return remote

    def test_every_rendered_frame_is_saved_with_its_bytes(self):
        calls = []
        results = cloud.dispatch_frames(_plan_frames(3), {}, self.output,
                                        self._remote(calls), _gpu_seen)
        self.assertEqual(calls, ["az1", "az2", "az3"])
        self.assertEqual([result["frame"] for result in results],
                         ["az1", "az2", "az3"])
        for frame in calls:
            self.assertTrue(
                (self.output / "cloud" / f"frame-{frame}/beauty.png").is_file())
            self.assertEqual(cloud.frame_complete(self.output, frame), (True, ""))

    def test_the_loop_stops_after_the_first_failed_frame(self):
        calls = []
        remote = self._remote(
            calls, status_for=lambda name: "failed" if name == "az2" else "rendered")
        results = cloud.dispatch_frames(_plan_frames(3), {}, self.output, remote,
                                        _gpu_seen)
        self.assertEqual(calls, ["az1", "az2"],
                         "a failed frame must not cost the frames after it")
        self.assertEqual([result["frame"] for result in results], ["az1", "az2"])
        self.assertFalse((self.output / "result-az3.json").exists())

    def test_a_result_from_another_request_raises_identity_mismatch(self):
        calls = []
        with self.assertRaisesRegex(ValueError, "^RESULT_IDENTITY_MISMATCH: az1"):
            cloud.dispatch_frames(_plan_frames(2), {}, self.output,
                                  self._remote(calls, identity=False), _gpu_seen)

    def test_bytes_that_do_not_match_their_declared_sha_raise(self):
        calls = []
        with self.assertRaisesRegex(ValueError,
                                    "^OUTPUT_HASH_MISMATCH: frame-az1/beauty.png"):
            cloud.dispatch_frames(_plan_frames(1), {}, self.output,
                                  self._remote(calls, declare_shas=False), _gpu_seen)

    def test_missing_gpu_evidence_fails_the_frame_instead_of_shipping_it(self):
        calls = []
        results = cloud.dispatch_frames(_plan_frames(1), {}, self.output,
                                        self._remote(calls), lambda samples: False)
        self.assertEqual(results[0]["status"], "failed")
        self.assertIn("NO_BLENDER_GPU_PROCESS_EVIDENCE", results[0]["failures"])
        self.assertFalse(cloud.frame_complete(self.output, "az1")[0])

    def test_a_complete_frame_is_never_dispatched_again(self):
        _complete_frame(self.output, "az1")
        calls = []
        results = cloud.dispatch_frames(_plan_frames(3), {}, self.output,
                                        self._remote(calls), _gpu_seen)
        self.assertEqual(calls, ["az2", "az3"])
        self.assertEqual([result["frame"] for result in results], ["az2", "az3"])


class ResumeTests(unittest.TestCase):
    """Brief section 9 criterion 7: resume works, proven adversarially."""

    def test_a_crash_at_frame_three_costs_only_frames_three_to_five(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _, manifest_path = job_fixture(root)
            crashed = root / "crashed"
            calls = []
            with self.assertRaises(RuntimeError):
                _run(manifest_path, crashed, _rendering_remote(calls, fail_at_call=3))
            self.assertEqual(calls, ["az1", "az2", "az3"])
            self.assertEqual([frame for frame in ("az1", "az2", "az3", "az4", "az5")
                              if cloud.frame_complete(crashed, frame)[0]],
                             ["az1", "az2"])
            resumed_calls = []
            self.assertEqual(
                _run(manifest_path, crashed, _rendering_remote(resumed_calls),
                     resume=True), 0)
            self.assertEqual(resumed_calls, ["az3", "az4", "az5"])
            # The finished sequence is identical to an uninterrupted one.
            whole_calls = []
            whole = root / "whole"
            self.assertEqual(
                _run(manifest_path, whole, _rendering_remote(whole_calls)), 0)
            self.assertEqual(whole_calls, ["az1", "az2", "az3", "az4", "az5"])
            self.assertEqual(_cloud_snapshot(crashed), _cloud_snapshot(whole))
            self.assertEqual(_result_artifacts(crashed), _result_artifacts(whole))
            resumed_status = json.loads(
                (crashed / "status.json").read_text(encoding="utf-8"))
            self.assertEqual(resumed_status["status"], "passed")
            self.assertIs(resumed_status["resumed"], True)
            whole_status = json.loads(
                (whole / "status.json").read_text(encoding="utf-8"))
            self.assertIs(whole_status["resumed"], False)

    def test_the_resume_log_records_skips_pendings_and_a_cost_estimate(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _, manifest_path = job_fixture(root)
            output = root / "out"
            calls = []
            with self.assertRaises(RuntimeError):
                _run(manifest_path, output,
                     _rendering_remote(calls, fail_at_call=2), azimuths="1,2,3")
            self.assertEqual(calls, ["az1", "az2"])
            resumed_calls = []
            _run(manifest_path, output, _rendering_remote(resumed_calls),
                 azimuths="1,2,3", resume=True)
            self.assertEqual(resumed_calls, ["az2", "az3"])
            log = json.loads((output / "resume-log.json").read_text(encoding="utf-8"))
            self.assertEqual(len(log), 1)
            self.assertEqual(log[0]["skipped"], ["az1"])
            self.assertEqual(log[0]["pending"], ["az2", "az3"])
            self.assertEqual(log[0]["skip_reasons"],
                             {"az2": "missing result", "az3": "missing result"})
            self.assertEqual(
                log[0]["cost_estimate_usd"],
                cloud.estimate_cost_usd(
                    [cloud.frame_render_seconds(floor_mode=False)] * 2))
            self.assertTrue(log[0]["started_utc"])

    def test_the_resume_log_is_written_before_the_dispatch(self):
        # The record of the invocation must exist even if the retry dies too.
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _, manifest_path = job_fixture(root)
            output = root / "out"
            with self.assertRaises(RuntimeError):
                _run(manifest_path, output,
                     _rendering_remote([], fail_at_call=2), azimuths="1,2,3")
            with self.assertRaises(RuntimeError):
                _run(manifest_path, output,
                     _rendering_remote([], fail_at_call=1), azimuths="1,2,3",
                     resume=True)
            log = json.loads((output / "resume-log.json").read_text(encoding="utf-8"))
            self.assertEqual(len(log), 1)
            self.assertEqual(log[0]["skipped"], ["az1"])
            self.assertEqual(log[0]["pending"], ["az2", "az3"])

    def test_an_all_complete_resume_dispatches_nothing_and_logs_zero(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _, manifest_path = job_fixture(root)
            output = root / "out"
            self.assertEqual(
                _run(manifest_path, output, _rendering_remote([]), azimuths="1,2"), 0)
            calls = []
            self.assertEqual(
                _run(manifest_path, output, _rendering_remote(calls),
                     azimuths="1,2", resume=True), 0)
            self.assertEqual(calls, [])
            log = json.loads((output / "resume-log.json").read_text(encoding="utf-8"))
            self.assertEqual(len(log), 1)
            self.assertEqual(log[0]["skipped"], ["az1", "az2"])
            self.assertEqual(log[0]["pending"], [])
            self.assertEqual(log[0]["skip_reasons"], {})
            self.assertEqual(log[0]["cost_estimate_usd"], 0.0)

    def test_a_resume_on_a_fresh_dir_runs_like_a_first_run(self):
        # One command must serve the first run and every retry of it.
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _, manifest_path = job_fixture(root)
            output = root / "out"
            calls = []
            self.assertEqual(
                _run(manifest_path, output, _rendering_remote(calls),
                     azimuths="1,2", resume=True), 0)
            self.assertEqual(calls, ["az1", "az2"])
            self.assertTrue((output / "request.json").is_file())

    def test_frames_without_a_verified_request_are_never_adopted(self):
        # A dir holding complete-looking frames but no request.json is a fresh
        # run: nothing on disk was planned by this request, so all re-render.
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _, manifest_path = job_fixture(root)
            output = root / "out"
            output.mkdir()
            _complete_frame(output, "az1", payload=b"foreign-build")
            self.assertTrue(cloud.frame_complete(output, "az1")[0])
            calls = []
            self.assertEqual(
                _run(manifest_path, output, _rendering_remote(calls),
                     azimuths="1,2", resume=True), 0)
            self.assertEqual(calls, ["az1", "az2"])
            self.assertNotEqual(
                (output / "cloud/frame-az1/beauty.png").read_bytes(), b"foreign-build")

    def test_a_resume_preflight_writes_no_resume_log(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _, manifest_path = job_fixture(root)
            output = root / "out"
            _run(manifest_path, output, _rendering_remote([]), azimuths="1,2")
            cloud.main(["--manifest", str(manifest_path), "--azimuths", "1,2",
                        "--output-dir", str(output), "--resume"])
            self.assertFalse((output / cloud.RESUME_LOG_NAME).exists())

    def test_the_resume_log_is_replaced_whole_never_left_torn(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            cloud.append_resume_log(output, {"n": 1})
            cloud.append_resume_log(output, {"n": 2})
            self.assertEqual(json.loads((output / cloud.RESUME_LOG_NAME)
                                        .read_text(encoding="utf-8")), [{"n": 1}, {"n": 2}])
            self.assertEqual([p.name for p in output.iterdir()], [cloud.RESUME_LOG_NAME])

    def test_without_resume_an_existing_output_dir_still_errors(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _, manifest_path = job_fixture(root)
            output = root / "out"
            _run(manifest_path, output, _rendering_remote([]), azimuths="1")
            before = _tree_snapshot(output)
            with self.assertRaises(FileExistsError):
                _run(manifest_path, output, _rendering_remote([]), azimuths="1")
            self.assertEqual(_tree_snapshot(output), before)

    def test_a_changed_override_is_a_resume_mismatch_with_no_writes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _, manifest_path = job_fixture(root)
            output = root / "out"
            _run(manifest_path, output, _rendering_remote([]), azimuths="1,2")
            before = _tree_snapshot(output)
            with self.assertRaisesRegex(SystemExit,
                                        "RESUME_REQUEST_MISMATCH: overrides"):
                _run(manifest_path, output, _rendering_remote([]), azimuths="1,2",
                     resume=True, overrides=["compositing.shadow_opacity=0.35"])
            self.assertEqual(_tree_snapshot(output), before)

    def test_a_changed_input_sha_is_a_resume_mismatch_with_no_writes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _, manifest_path = job_fixture(root)
            output = root / "out"
            _run(manifest_path, output, _rendering_remote([]), azimuths="1,2")
            before = _tree_snapshot(output)
            (root / "cad/machine.blend").write_bytes(b"a different CAD revision")
            with self.assertRaisesRegex(SystemExit, "RESUME_REQUEST_MISMATCH: inputs"):
                _run(manifest_path, output, _rendering_remote([]), azimuths="1,2",
                     resume=True)
            self.assertEqual(_tree_snapshot(output), before)

    def test_a_rebuilt_worker_is_a_resume_mismatch(self):
        # inputs carries the sha of every mounted file, render_worker.py
        # included: a worker rebuilt mid-sequence must not be mixed in silently.
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _, manifest_path = job_fixture(root)
            output = root / "out"
            worker_root = root / "worker"
            worker_root.mkdir()
            (worker_root / "render_worker.py").write_bytes(b"build one")
            original = cloud.ROOT
            cloud.ROOT = worker_root
            try:
                _run(manifest_path, output, _rendering_remote([]), azimuths="1,2")
                before = _tree_snapshot(output)
                (worker_root / "render_worker.py").write_bytes(b"build two")
                with self.assertRaisesRegex(SystemExit,
                                            "RESUME_REQUEST_MISMATCH: inputs"):
                    _run(manifest_path, output, _rendering_remote([]),
                         azimuths="1,2", resume=True)
                self.assertEqual(_tree_snapshot(output), before)
            finally:
                cloud.ROOT = original

    def test_a_changed_frame_manifest_is_a_resume_mismatch(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _, manifest_path = job_fixture(root)
            output = root / "out"
            _run(manifest_path, output, _rendering_remote([]), azimuths="1,2")
            (output / "manifest-az2.json").write_text("{}\n", encoding="utf-8")
            edited = _tree_snapshot(output)
            with self.assertRaisesRegex(SystemExit,
                                        "RESUME_REQUEST_MISMATCH: manifest-az2"):
                _run(manifest_path, output, _rendering_remote([]), azimuths="1,2",
                     resume=True)
            self.assertEqual(_tree_snapshot(output), edited)


if __name__ == "__main__":
    unittest.main()

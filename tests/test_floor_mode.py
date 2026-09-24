"""Regression tests for the opt-in rendered studio floor (batch 3b).

The floor mode bakes a real floor into an opaque beauty pass and recovers the
product cutout from a second, floor-hidden transparent render. Every test here
pins behaviour, not source strings: gates run on saved bytes, restoration runs
against stubbed Blender state, and routing is observed through the public
compositor entry points.
"""

import argparse
import importlib.util
import io
import json
import math
import os
import sys
import tempfile
import unittest
import unittest.mock as mock
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from composite_worker import MSPCompositor, floor_mode, validate_floor_config


def _floor_manifest(**lighting_floor):
    return {
        "job_id": "floor_job",
        "output": {"film_transparent": False},
        "lighting": {"preset": "studio_white", "floor": lighting_floor},
        "compositing": {"enabled": True, "product_scale": 1.0,
                        "product_offset_px": [0, 0]},
    }


class FloorConfigValidationTests(unittest.TestCase):
    def test_floor_mode_requires_explicit_flag(self):
        self.assertFalse(floor_mode({"lighting": {}}))
        self.assertFalse(floor_mode({"lighting": {"floor": {"enabled": False}}}))
        self.assertFalse(floor_mode({"lighting": {"floor": {"enabled": "yes"}}}))
        self.assertTrue(floor_mode({"lighting": {"floor": {"enabled": True}}}))

    def test_compositing_disabled_alone_never_implies_floor(self):
        manifest = {"lighting": {},
                    "compositing": {"enabled": False}}
        self.assertFalse(floor_mode(manifest))
        self.assertEqual(validate_floor_config(manifest), [])

    def test_valid_floor_manifest_has_no_errors(self):
        self.assertEqual(validate_floor_config(_floor_manifest(enabled=True)), [])

    def test_floor_with_transparent_film_is_rejected(self):
        manifest = _floor_manifest(enabled=True)
        manifest["output"]["film_transparent"] = True
        errors = validate_floor_config(manifest)
        self.assertTrue(any("FLOOR_REQUIRES_OPAQUE_FILM" in e for e in errors))

    def test_opaque_non_floor_is_rejected(self):
        errors = validate_floor_config({"lighting": {},
                                        "output": {"film_transparent": False}})
        self.assertTrue(any("OPAQUE_NON_FLOOR_UNSUPPORTED" in e for e in errors))

    def test_floor_with_rescale_or_offset_is_rejected(self):
        for comp in ({"product_scale": 0.8},
                     {"product_offset_px": [10, 0]},
                     {"product_offset_pct": [0.0, -0.02]}):
            with self.subTest(comp=comp):
                manifest = _floor_manifest(enabled=True)
                manifest["compositing"].update(comp)
                errors = validate_floor_config(manifest)
                self.assertTrue(errors)

    def test_nonboolean_and_nonnumeric_new_fields_are_rejected(self):
        bad = _floor_manifest(enabled="true")
        self.assertTrue(validate_floor_config(bad))
        bad["output"]["film_transparent"] = "false"
        self.assertTrue(validate_floor_config(bad))

    def test_floor_with_alpha_mask_disabled_is_rejected(self):
        manifest = _floor_manifest(enabled=True)
        manifest["output"]["passes"] = {"alpha_mask": False}
        errors = validate_floor_config(manifest)
        self.assertTrue(any("FLOOR_REQUIRES_ALPHA_MASK" in e for e in errors))
        import render_worker
        with self.assertRaisesRegex(ValueError, "FLOOR_REQUIRES_ALPHA_MASK"):
            render_worker.validate_output_config(manifest)

    def test_floor_with_alpha_mask_default_or_true_stays_valid(self):
        for passes in (None, {"alpha_mask": True}):
            manifest = _floor_manifest(enabled=True)
            if passes is not None:
                manifest["output"]["passes"] = passes
            self.assertEqual(validate_floor_config(manifest), [])


def _write_floor_frame(frame, w=80, h=60):
    rng = np.random.default_rng(3)
    beauty = rng.integers(120, 160, (h, w, 3), dtype=np.uint8)
    beauty[20:40, 30:50] = (247, 181, 0)
    beauty_path = frame / "beauty.png"
    Image.fromarray(beauty).save(beauty_path)
    alpha = np.zeros((h, w), dtype=np.uint8)
    alpha[20:40, 30:50] = 255
    Image.fromarray(alpha).save(frame / "mask.png")
    matte = np.dstack([alpha] * 3 + [alpha])
    Image.fromarray(matte).save(frame / "beauty-matte.png")
    return beauty_path, alpha


class FloorCompositorTests(unittest.TestCase):
    """Gates run against saved bytes; the full rendered floor must survive."""

    W, H = 320, 240
    BOX = (110, 80, 210, 180)  # product block inside a rendered floor scene

    def _fixtures(self, tmpdir):
        rng = np.random.default_rng(7)
        floor_rgb = rng.integers(120, 160, (self.H, self.W, 3), dtype=np.uint8)
        beauty = floor_rgb.copy()
        left, top, right, bottom = self.BOX
        beauty[top:bottom, left:right] = (247, 181, 0)  # the machine
        beauty_path = os.path.join(tmpdir, "beauty.png")
        Image.fromarray(beauty).save(beauty_path)

        matte_alpha = np.zeros((self.H, self.W), dtype=np.uint8)
        matte_alpha[top:bottom, left:right] = 255
        matte = np.dstack([matte_alpha] * 3 + [matte_alpha]).astype(np.uint8)
        matte_path = os.path.join(tmpdir, "beauty-matte.png")
        Image.fromarray(matte).save(matte_path)

        mask_path = os.path.join(tmpdir, "mask.png")
        Image.fromarray(matte_alpha).save(mask_path)
        return beauty_path, mask_path, matte_path, beauty, matte_alpha

    def test_full_floor_rgb_is_preserved_exactly(self):
        with tempfile.TemporaryDirectory() as tmp:
            beauty_path, mask_path, matte_path, beauty, _ = self._fixtures(tmp)
            out = os.path.join(tmp, "composite.png")
            res = MSPCompositor.composite_rendered_floor_asset(
                beauty_path, mask_path, matte_path, out)
            self.assertEqual(res["mode"], "rendered_floor")
            self.assertEqual(res["status"], "success")
            self.assertTrue(res["fidelity_gate_pass"])
            self.assertEqual(res["max_pixel_drift"], 0)
            saved = np.array(Image.open(res["output_path"]).convert("RGB"))
            self.assertTrue(np.array_equal(saved, beauty),
                            "A rendered-floor composite altered scene pixels.")

    def test_product_and_floor_tamper_are_detected_on_saved_bytes(self):
        real_save = MSPCompositor._save_robustly
        left, top, right, bottom = self.BOX

        def tampered_save(image, path, **kwargs):
            arr = np.array(image.convert("RGB"))
            arr[top + 10:bottom - 10, left + 10:right - 10] = (0, 255, 0)
            return real_save(Image.fromarray(arr), path, **kwargs)

        with tempfile.TemporaryDirectory() as tmp:
            beauty_path, mask_path, matte_path, _, _ = self._fixtures(tmp)
            with mock.patch.object(MSPCompositor, "_save_robustly",
                                   side_effect=tampered_save):
                res = MSPCompositor.composite_rendered_floor_asset(
                    beauty_path, mask_path, matte_path, os.path.join(tmp, "c.png"))
            self.assertFalse(res["fidelity_gate_pass"])
            self.assertEqual(res["status"], "failed")

        def floor_tamper_save(image, path, **kwargs):
            arr = np.array(image.convert("RGB"))
            arr[:10, :] = (255, 0, 255)  # floor only: the machine is untouched
            return real_save(Image.fromarray(arr), path, **kwargs)

        with tempfile.TemporaryDirectory() as tmp:
            beauty_path, mask_path, matte_path, _, _ = self._fixtures(tmp)
            with mock.patch.object(MSPCompositor, "_save_robustly",
                                   side_effect=floor_tamper_save):
                res = MSPCompositor.composite_rendered_floor_asset(
                    beauty_path, mask_path, matte_path, os.path.join(tmp, "c.png"))
            self.assertFalse(res["fidelity_gate_pass"],
                             "Floor tampering must fail the whole-frame gate.")
            self.assertEqual(res["product_fidelity"]["max_pixel_drift"], 0,
                             "Product pixels were fine; the drift is floor-only.")

    def test_mask_rejections(self):
        with tempfile.TemporaryDirectory() as tmp:
            beauty_path, mask_path, matte_path, _, matte_alpha = self._fixtures(tmp)
            out = os.path.join(tmp, "composite.png")

            zero = os.path.join(tmp, "mask_zero.png")
            Image.fromarray(np.zeros_like(matte_alpha)).save(zero)
            res = MSPCompositor.composite_rendered_floor_asset(
                beauty_path, zero, matte_path, out)
            self.assertFalse(res["matte_plausibility_pass"])
            self.assertEqual(res["status"], "failed")

            full = os.path.join(tmp, "mask_full.png")
            Image.fromarray(np.full_like(matte_alpha, 255)).save(full)
            res = MSPCompositor.composite_rendered_floor_asset(
                beauty_path, full, matte_path, out)
            self.assertFalse(res["matte_plausibility_pass"])

            shifted = np.zeros_like(matte_alpha)
            shifted[:, 20:] = matte_alpha[:, :-20]
            mis = os.path.join(tmp, "mask_mis.png")
            Image.fromarray(shifted).save(mis)
            res = MSPCompositor.composite_rendered_floor_asset(
                beauty_path, mis, matte_path, out)
            self.assertFalse(res["mask_gate_pass"])
            self.assertEqual(res["status"], "failed")

            small = os.path.join(tmp, "mask_small.png")
            Image.fromarray(matte_alpha[: self.H // 2]).save(small)
            with self.assertRaises(ValueError):
                MSPCompositor.composite_rendered_floor_asset(
                    beauty_path, small, matte_path, out)

            for missing in ("beauty.png", "mask.png", "beauty-matte.png"):
                with self.subTest(missing=missing):
                    paths = {"beauty.png": beauty_path, "mask.png": mask_path,
                             "beauty-matte.png": matte_path}
                    paths[missing] = os.path.join(tmp, "nope.png")
                    with self.assertRaises(FileNotFoundError):
                        MSPCompositor.composite_rendered_floor_asset(
                            paths["beauty.png"], paths["mask.png"],
                            paths["beauty-matte.png"], out)

    def test_mask_consistency_compares_against_matte_alpha_not_beauty(self):
        """A mask that matches the opaque beauty alpha (everything opaque)
        but not the product matte must fail - the old comparison target."""
        with tempfile.TemporaryDirectory() as tmp:
            _, _, matte_path, _, matte_alpha = self._fixtures(tmp)
            beauty_alpha = np.full_like(matte_alpha, 255)
            beauty_rgba = np.dstack(
                [np.full_like(matte_alpha, 90)] * 3 + [beauty_alpha])
            beauty_full = os.path.join(tmp, "beauty_opaque.png")
            Image.fromarray(beauty_rgba).save(beauty_full)
            wrong_mask = os.path.join(tmp, "mask_beauty_alpha.png")
            Image.fromarray(beauty_alpha).save(wrong_mask)
            res = MSPCompositor.composite_rendered_floor_asset(
                beauty_full, wrong_mask, matte_path, os.path.join(tmp, "c.png"))
            self.assertFalse(res["mask_gate_pass"])
            self.assertIn("beauty-matte", res["mask_consistency_source"])

    def test_transparent_beauty_is_rejected(self):
        """A floor-mode beauty must be opaque: a transparent one means the
        floor was never baked in, and finishing it would seat a cut-out on
        nothing."""
        with tempfile.TemporaryDirectory() as tmp:
            beauty_path, mask_path, matte_path, beauty, _ = self._fixtures(tmp)
            rgba = np.dstack([beauty, np.full(beauty.shape[:2], 120,
                                              dtype=np.uint8)])
            rgba[0:5, 0:5, 3] = 0  # a hole: not opaque
            Image.fromarray(rgba).save(beauty_path)
            res = MSPCompositor.composite_rendered_floor_asset(
                beauty_path, mask_path, matte_path,
                os.path.join(tmp, "c.png"))
            self.assertFalse(res["beauty_opaque_pass"])
            self.assertEqual(res["status"], "failed")

    def test_opaque_rgba_beauty_passes_the_opaque_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            beauty_path, mask_path, matte_path, beauty, _ = self._fixtures(tmp)
            rgba = np.dstack([beauty, np.full(beauty.shape[:2], 255,
                                              dtype=np.uint8)])
            Image.fromarray(rgba).save(beauty_path)
            res = MSPCompositor.composite_rendered_floor_asset(
                beauty_path, mask_path, matte_path,
                os.path.join(tmp, "c.png"))
            self.assertTrue(res["beauty_opaque_pass"])
            self.assertEqual(res["status"], "success")

    def test_lens_pass_is_applied_exactly_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            beauty_path, mask_path, matte_path, beauty, _ = self._fixtures(tmp)
            out = os.path.join(tmp, "composite.png")
            res = MSPCompositor.composite_rendered_floor_asset(
                beauty_path, mask_path, matte_path, out,
                lens_vignette=0.45, lens_bloom=0.3, lens_grain=2.2,
                frame_index=0)
            self.assertTrue(res["lens_applied"])
            lensed = np.array(Image.open(res["output_path"]).convert("RGB"))
            self.assertFalse(np.array_equal(lensed, beauty),
                             "Lens params produced no change.")
            expected = MSPCompositor.apply_lens_pass(
                Image.open(beauty_path).convert("RGB"),
                vignette=0.45, bloom=0.3, grain=2.2, frame_index=0)
            self.assertTrue(np.array_equal(
                lensed, np.array(expected)), "Lens pass ran zero or two times.")

    def test_shadow_opacity_zero_and_035_produce_identical_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            beauty_path, mask_path, matte_path, _, _ = self._fixtures(tmp)
            res_a = MSPCompositor.composite_rendered_floor_asset(
                beauty_path, mask_path, matte_path,
                os.path.join(tmp, "a.png"), shadow_opacity=0.0)
            res_b = MSPCompositor.composite_rendered_floor_asset(
                beauty_path, mask_path, matte_path,
                os.path.join(tmp, "b.png"), shadow_opacity=0.35)
            with open(res_a["output_path"], "rb") as fa:
                with open(res_b["output_path"], "rb") as fb:
                    self.assertEqual(fa.read(), fb.read(),
                                     "The synthetic shadow leaked into floor mode.")
        for res, configured in ((res_a, 0.0), (res_b, 0.35)):
            self.assertFalse(res["synthetic_shadow_applied"])
            self.assertEqual(res["effective_shadow_opacity"], 0.0)
            self.assertEqual(res["configured_shadow_opacity"], configured)


class SharedFinishingRouteTests(unittest.TestCase):
    def test_dispatcher_routes_floor_frames_to_the_shared_finishing(self):
        spec = importlib.util.spec_from_file_location(
            "cloud_job_render", ROOT / "scripts/cloud_job_render.py")
        cloud = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cloud)
        with tempfile.TemporaryDirectory() as tmp:
            frame = Path(tmp)
            beauty, _ = _write_floor_frame(frame)
            out = cloud.run_composite(frame, None,
                                      {"enabled": True, "shadow_opacity": 0.35},
                                      floor_mode=True)
            saved = np.array(Image.open(out).convert("RGB"))
            self.assertTrue(np.array_equal(
                saved, np.array(Image.open(beauty).convert("RGB"))))

    def test_probe_uses_the_same_entry_point(self):
        spec = importlib.util.spec_from_file_location(
            "probe_sequence", ROOT / "scripts/probe_sequence.py")
        probe = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(probe)
        with tempfile.TemporaryDirectory() as tmp:
            frame = Path(tmp)
            _write_floor_frame(frame)
            res = probe.composite_frame(
                frame, None, {"enabled": True, "shadow_opacity": 0.35},
                floor_mode=True)
            self.assertEqual(res["mode"], "rendered_floor")
            self.assertEqual(res["status"], "success")


class DispatcherFloorPreflightTests(unittest.TestCase):
    """Invalid floor combinations die at plan time, before any remote call."""

    @staticmethod
    def _cloud():
        spec = importlib.util.spec_from_file_location(
            "cloud_job_render", ROOT / "scripts/cloud_job_render.py")
        cloud = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cloud)
        return cloud

    @staticmethod
    def _fixture(root, output_extra=None, **extra):
        root = Path(root)
        (root / "jobs").mkdir(parents=True, exist_ok=True)
        (root / "cad").mkdir(exist_ok=True)
        (root / "cad/machine.blend").write_bytes(b"blend")
        manifest = {
            "job_id": "floor_job",
            "cad_source": {"file_path": "cad/machine.blend"},
            "camera": {"azimuth_deg": 42.0},
            "lighting": {"floor": {"enabled": True}},
            "compositing": {"enabled": True},
            "output": {"film_transparent": False,
                       "output_dir": "./output/floor"},
        }
        if output_extra:
            manifest["output"].update(output_extra)
        manifest.update(extra)
        path = root / "jobs/floor_job.json"
        path.write_text(json.dumps(manifest), encoding="utf-8")
        return path

    def test_floor_plan_passes_preflight(self):
        cloud = self._cloud()
        with tempfile.TemporaryDirectory() as tmp:
            path = self._fixture(tmp)
            plan = cloud.frame_plan(path, [42.0, 222.0])
            self.assertTrue(plan["floor_mode"])

    def test_key_enabled_override_reaches_frames_without_touching_source(self):
        cloud = self._cloud()
        with tempfile.TemporaryDirectory() as tmp:
            path = self._fixture(tmp)
            source_before = path.read_bytes()
            plan = cloud.frame_plan(
                path, [42.0, 222.0], ["lighting.key_enabled=false"])
            self.assertEqual([f["lighting"]["key_enabled"]
                              for f in plan["frames"]], [False, False])
            self.assertEqual(path.read_bytes(), source_before)

    def test_key_enabled_absent_floor_frames_keep_the_previous_structure(self):
        cloud = self._cloud()
        with tempfile.TemporaryDirectory() as tmp:
            path = self._fixture(tmp)
            plan = cloud.frame_plan(path, [42.0, 222.0])
            self.assertEqual([f["lighting"] for f in plan["frames"]],
                             [{"floor": {"enabled": True}}] * 2)

    def test_key_enabled_absent_studio_white_frames_keep_the_previous_structure(self):
        cloud = self._cloud()
        with tempfile.TemporaryDirectory() as tmp:
            path = self._fixture(
                tmp, lighting={"preset": "studio_white"},
                output_extra={"film_transparent": True})
            plan = cloud.frame_plan(path, [42.0])
            self.assertFalse(plan["floor_mode"])
            self.assertEqual([f["lighting"] for f in plan["frames"]],
                             [{"preset": "studio_white"}])

    def test_key_enabled_explicit_source_value_reaches_frames_verbatim(self):
        cloud = self._cloud()
        with tempfile.TemporaryDirectory() as tmp:
            for source_value in (True, False):
                path = self._fixture(
                    tmp, lighting={"preset": "studio_white",
                                   "key_enabled": source_value},
                    output_extra={"film_transparent": True})
                plan = cloud.frame_plan(path, [42.0])
                self.assertEqual([f["lighting"]["key_enabled"]
                                  for f in plan["frames"]], [source_value])

    def test_fill_enabled_override_reaches_frames_without_touching_source(self):
        cloud = self._cloud()
        with tempfile.TemporaryDirectory() as tmp:
            path = self._fixture(tmp)
            source_before = path.read_bytes()
            plan = cloud.frame_plan(
                path, [42.0, 222.0], ["lighting.fill_enabled=false"])
            self.assertEqual([f["lighting"]["fill_enabled"]
                              for f in plan["frames"]], [False, False])
            self.assertEqual(path.read_bytes(), source_before)

    def test_rim_enabled_override_reaches_frames_without_touching_source(self):
        cloud = self._cloud()
        with tempfile.TemporaryDirectory() as tmp:
            path = self._fixture(tmp)
            source_before = path.read_bytes()
            plan = cloud.frame_plan(
                path, [42.0, 222.0], ["lighting.rim_enabled=false"])
            self.assertEqual([f["lighting"]["rim_enabled"]
                              for f in plan["frames"]], [False, False])
            self.assertEqual(path.read_bytes(), source_before)

    def test_key_enabled_stays_the_only_creatable_override_path(self):
        cloud = self._cloud()
        with tempfile.TemporaryDirectory() as tmp:
            path = self._fixture(tmp)
            with self.assertRaisesRegex(ValueError, "UNKNOWN_OVERRIDE_PATH"):
                cloud.frame_plan(
                    path, [42.0], ["lighting.key_enabled_typo=false"])

    def test_floor_with_transparent_film_fails_before_dispatch(self):
        cloud = self._cloud()
        with tempfile.TemporaryDirectory() as tmp:
            path = self._fixture(tmp)
            with self.assertRaisesRegex(ValueError, "FLOOR_REQUIRES_OPAQUE_FILM"):
                cloud.frame_plan(
                    path, [42.0], ["output.film_transparent=true"])

    def test_opaque_non_floor_fails_before_dispatch(self):
        cloud = self._cloud()
        with tempfile.TemporaryDirectory() as tmp:
            path = self._fixture(tmp)
            with self.assertRaisesRegex(ValueError, "OPAQUE_NON_FLOOR_UNSUPPORTED"):
                cloud.frame_plan(path, [42.0],
                                 ["lighting.floor.enabled=false"])

    def test_floor_with_alpha_mask_disabled_fails_before_dispatch(self):
        cloud = self._cloud()
        with tempfile.TemporaryDirectory() as tmp:
            path = self._fixture(
                tmp, output_extra={"passes": {"alpha_mask": False}})
            with self.assertRaisesRegex(ValueError, "FLOOR_REQUIRES_ALPHA_MASK"):
                cloud.frame_plan(path, [42.0])

    def test_floor_estimate_counts_both_render_passes(self):
        cloud = self._cloud()
        plain = cloud.frame_render_seconds(floor_mode=False)
        floored = cloud.frame_render_seconds(floor_mode=True)
        self.assertAlmostEqual(floored, 2.0 * plain)
        per_second = (cloud.GPU_RATE_PER_S + 4 * cloud.CPU_RATE_PER_CORE_S
                      + 16 * cloud.MEMORY_RATE_PER_GIB_S)
        self.assertAlmostEqual(
            cloud.estimate_cost_usd([cloud.frame_render_seconds(True)]),
            round((cloud.COLD_START_SECONDS + 2 * 101.65) * per_second, 4))


class FloorRenderWorkerTests(unittest.TestCase):
    """render_worker behaviour against stubbed Blender state."""

    @staticmethod
    def _worker():
        import render_worker
        return render_worker

    def test_default_film_path_is_unchanged(self):
        worker = self._worker()
        self.assertEqual(worker.film_transparent_for({"output": {}}), True)
        self.assertEqual(
            worker.film_transparent_for({"output": {"film_transparent": False}}),
            False)

    def test_floor_is_built_after_the_hide_pass_and_suppresses_the_catcher(self):
        worker = self._worker()
        bpy = mock.MagicMock()
        bpy.data.objects.get.return_value = None
        bpy.context.scene.objects = []
        with mock.patch.object(worker, "bpy", bpy):
            # 3d target change: the build now runs the in-frame cove
            # assertions, so the fake camera must frame the cove (a downward
            # 3c-era fake puts the far tangent at the frame bottom).
            floor = worker.build_studio_floor(
                1.5, scene=_cove_camera((0.0, 0.0, 0.0), 1.5))
            self.assertEqual(floor.name, "MSP_StudioFloor")
            # The cyc is built with from_pydata; the floor build itself
            # makes zero primitive_plane_add calls.
            self.assertEqual(bpy.ops.mesh.primitive_plane_add.call_count, 0)
            plane_calls = bpy.ops.mesh.primitive_plane_add.call_count
            worker.setup_lighting(
                {"preset": "studio_white", "shadow_catcher": True},
                mock.MagicMock(), 1.5, suppress_shadow_catcher=True)
            # Suppressed: no second plane was built by the lighting branch.
            self.assertEqual(bpy.ops.mesh.primitive_plane_add.call_count,
                             plane_calls)
            worker.setup_lighting(
                {"preset": "studio_white", "shadow_catcher": True},
                mock.MagicMock(), 1.5)
            # Unsuppressed: the catcher plane is built as before.
            self.assertEqual(bpy.ops.mesh.primitive_plane_add.call_count,
                             plane_calls + 1)

    def test_invalid_cyc_mesh_raises_loudly(self):
        worker = self._worker()
        bpy = mock.MagicMock()
        bpy.data.objects.get.return_value = None
        bpy.context.scene.objects = []
        mesh = bpy.data.meshes.new.return_value
        mesh.validate.return_value = True
        # 3d target change: use a cove-framing camera; a downward fake now
        # fails the in-frame cove gate before the mesh is ever built.
        with mock.patch.object(worker, "bpy", bpy):
            with self.assertRaisesRegex(RuntimeError, "CYC_MESH_INVALID"):
                worker.build_studio_floor(
                    1.5, scene=_cove_camera((0.0, 0.0, 0.0), 1.5))

    @staticmethod
    def _analytic_light_names(spec):
        worker = FloorRenderWorkerTests._worker()
        bpy = mock.MagicMock()
        bpy.data.objects.get.return_value = None
        bpy.context.scene.objects = []
        with mock.patch.object(worker, "bpy", bpy):
            worker.setup_lighting(
                spec, mock.MagicMock(), 1.5, suppress_shadow_catcher=True)
        return [call.kwargs["name"]
                for call in bpy.data.lights.new.call_args_list]

    def test_missing_key_enabled_creates_the_unchanged_full_rig(self):
        names = self._analytic_light_names(
            {"preset": "studio_white"})
        self.assertEqual(
            names, ["Key_Softbox", "Fill_Softbox", "Rim_Light"])

    def test_explicit_true_key_enabled_creates_the_unchanged_full_rig(self):
        names = self._analytic_light_names(
            {"preset": "studio_dark", "key_enabled": True})
        self.assertEqual(
            names, ["Key_Softbox", "Fill_Softbox", "Rim_Light"])

    def test_false_key_enabled_omits_only_the_studio_key(self):
        for preset in ("studio_white", "studio_dark"):
            with self.subTest(preset=preset):
                names = self._analytic_light_names(
                    {"preset": preset, "key_enabled": False})
                self.assertEqual(names, ["Fill_Softbox", "Rim_Light"])

    def test_analytic_lights_off_with_key_enabled_false_still_skips_all(self):
        names = self._analytic_light_names(
            {"preset": "studio_white", "analytic_lights": False,
             "key_enabled": False})
        self.assertEqual(names, [])

    def test_explicit_true_fill_and_rim_enabled_create_the_unchanged_full_rig(self):
        names = self._analytic_light_names(
            {"preset": "studio_dark", "fill_enabled": True,
             "rim_enabled": True})
        self.assertEqual(
            names, ["Key_Softbox", "Fill_Softbox", "Rim_Light"])

    def test_false_fill_enabled_omits_only_the_studio_fill(self):
        for preset in ("studio_white", "studio_dark"):
            with self.subTest(preset=preset):
                names = self._analytic_light_names(
                    {"preset": preset, "fill_enabled": False})
                self.assertEqual(names, ["Key_Softbox", "Rim_Light"])

    def test_false_rim_enabled_omits_only_the_studio_rim(self):
        for preset in ("studio_white", "studio_dark"):
            with self.subTest(preset=preset):
                names = self._analytic_light_names(
                    {"preset": preset, "rim_enabled": False})
                self.assertEqual(names, ["Key_Softbox", "Fill_Softbox"])

    def test_all_three_flags_false_leave_no_analytic_light(self):
        names = self._analytic_light_names(
            {"preset": "studio_white", "key_enabled": False,
             "fill_enabled": False, "rim_enabled": False})
        self.assertEqual(names, [])

    def test_analytic_lights_off_with_fill_and_rim_false_still_skips_all(self):
        names = self._analytic_light_names(
            {"preset": "studio_white", "analytic_lights": False,
             "fill_enabled": False, "rim_enabled": False})
        self.assertEqual(names, [])

    def test_matte_render_restores_all_state_even_on_failure(self):
        worker = self._worker()

        class FakeCycles:
            def __init__(self):
                self.samples = 96
                self.seed = 7
                self.use_animated_seed = True
                self.use_denoising = True

        class FakeRender:
            def __init__(self):
                self.filepath = "/output/beauty.png"
                self.film_transparent = False
                self.engine = "CYCLES"

        class FakeScene:
            def __init__(self):
                self.render = FakeRender()
                self.cycles = FakeCycles()

        scene = FakeScene()
        floor = mock.MagicMock(hide_render=False)
        seen = {}

        def failing_render(write_still=False):
            seen["filepath"] = scene.render.filepath
            seen["film"] = scene.render.film_transparent
            seen["seed"] = scene.cycles.seed
            seen["animated"] = scene.cycles.use_animated_seed
            seen["denoise"] = scene.cycles.use_denoising
            seen["floor_hidden"] = floor.hide_render
            raise RuntimeError("GPU_WENT_AWAY")

        bpy = mock.MagicMock()
        bpy.ops.render.render.side_effect = failing_render
        with mock.patch.object(worker, "bpy", bpy):
            with self.assertRaisesRegex(RuntimeError, "GPU_WENT_AWAY"):
                worker.render_floor_hidden_matte(scene, floor, "/output")

        self.assertTrue(seen["filepath"].endswith("beauty-matte.png"))
        self.assertTrue(seen["film"])
        self.assertTrue(seen["floor_hidden"])
        self.assertFalse(seen["animated"])
        self.assertFalse(seen["denoise"])
        self.assertEqual(scene.render.filepath, "/output/beauty.png")
        self.assertFalse(scene.render.film_transparent)
        self.assertFalse(floor.hide_render)
        self.assertEqual(scene.cycles.seed, 7)
        self.assertTrue(scene.cycles.use_animated_seed)
        self.assertTrue(scene.cycles.use_denoising)

    def test_floor_seats_at_product_ground_bounds_not_assumed_zero(self):
        """A native .blend is never re-normalised to z=0; the floor must
        meet the product's measured ground, and hidden CAD scenery (the
        ground-hide pass output) must not drag it down."""
        worker = self._worker()

        class FakeMatrix:
            def __init__(self, t):
                self.translation = t

        class FakeObj:
            def __init__(self, name, translation, box, hidden=False):
                self.type = "MESH"
                self.name = name
                self.hide_render = hidden
                self.bound_box = box
                self.matrix_world = FakeMatrix(translation)

        class T:
            def __init__(self, x, y, z):
                self.x, self.y, self.z = x, y, z

        product = FakeObj("PumpBody", T(0.5, -0.25, 0.0),
                          [(-1, -1, -0.3), (1, -1, -0.3), (-1, 1, -0.3),
                           (1, 1, -0.3), (-1, -1, 0.9), (1, -1, 0.9),
                           (-1, 1, 0.9), (1, 1, 0.9)])
        hidden_slab = FakeObj("FactoryFloor", T(0.0, 0.0, -2.0),
                              [(-9, -9, -0.1), (9, -9, -0.1), (-9, 9, -0.1),
                               (9, 9, -0.1), (-9, -9, 0.1), (9, -9, 0.1),
                               (-9, 9, 0.1), (9, 9, 0.1)],
                              hidden=True)
        bpy = mock.MagicMock()
        bpy.context.scene.objects = [product, hidden_slab]
        with mock.patch.object(worker, "bpy", bpy):
            # 3d target change: camera frames the cove around the seated axis.
            worker.build_studio_floor(
                1.5, scene=_cove_camera((0.5, -0.25, -0.3), 1.5))
        verts = (bpy.data.meshes.new.return_value.from_pydata.call_args.args[0])
        # The disc seats exactly at the measured product ground, centred on it.
        self.assertAlmostEqual(min(v[2] for v in verts), -0.3)
        self.assertAlmostEqual(
            sum(v[0] for v in verts) / len(verts), 0.5)
        self.assertAlmostEqual(
            sum(v[1] for v in verts) / len(verts), -0.25)


class _V:
    def __init__(self, x, y, z):
        self.x, self.y, self.z = float(x), float(y), float(z)


class _IdentityMatrix:
    """Translation+identity-rotation stand-in for mathutils.Matrix."""
    col = [_V(1, 0, 0), _V(0, 1, 0), _V(0, 0, 1)]

    def __init__(self, translation):
        self.translation = translation

    def __matmul__(self, v):
        t = self.translation
        return _V(v.x + t.x, v.y + t.y, v.z + t.z)


class _FakeCamData:
    def __init__(self, corners, cam_type="PERSP", clip_end=200.0,
                 use_dof=False, aperture_fstop=0.0, focus_distance=0.0,
                 lens=50.0):
        self._corners = corners
        self.type = cam_type
        self.clip_end = clip_end
        self.lens = lens
        self.dof = type("Dof", (), {"use_dof": use_dof,
                                     "aperture_fstop": aperture_fstop,
                                     "focus_distance": focus_distance})()

    def view_frame(self, scene=None):
        return self._corners


class _FakeCamera:
    def __init__(self, cam_data, translation):
        self.data = cam_data
        self.matrix_world = _IdentityMatrix(translation)


class _FakeScene:
    def __init__(self, camera):
        self.camera = camera


class _UpdatableFakeCamera:
    """Camera whose matrix_world stays stale (identity) until the view layer
    updates - mirrors a freshly created object whose location/rotation were
    assigned but never evaluated by the depsgraph."""

    def __init__(self, cam_data, placed_translation):
        self.data = cam_data
        self._placed = _IdentityMatrix(placed_translation)
        self.matrix_world = _IdentityMatrix(_V(0, 0, 0))

    def apply_update(self):
        self.matrix_world = self._placed


class _RotatedFakeMatrix:
    """Orthonormal-basis + translation stand-in for a tilted mathutils matrix."""

    def __init__(self, col0, col1, col2, translation):
        self.col = [col0, col1, col2]
        self.translation = translation

    def __matmul__(self, v):
        cols = self.col
        return _V(cols[0].x * v.x + cols[1].x * v.y + cols[2].x * v.z
                  + self.translation.x,
                  cols[0].y * v.x + cols[1].y * v.y + cols[2].y * v.z
                  + self.translation.y,
                  cols[0].z * v.x + cols[1].z * v.y + cols[2].z * v.z
                  + self.translation.z)


def _cove_camera(placement, product_radial, daway=10.0, pitch_deg=13.96,
                 yaw_deg=0.0):
    """A perspective rig whose far-side cove tangent lands at row 0.35.

    The camera sits at radial daway on the -y side of the cove axis, pitched
    down pitch_deg, so the 3d in-frame assertions pass. Downward 3c-era fakes
    cannot satisfy the new target (their far tangent projects to the frame
    bottom), so the build_studio_floor tests use this camera.
    """
    import render_worker
    px, py, pz = placement
    fillet0 = max(2.0 * product_radial, 0.5)
    wall_radius = max(daway + render_worker.COVE_CAM_CLEARANCE_M,
                      product_radial + fillet0
                      + render_worker.PRODUCT_FLOOR_MARGIN_M)
    fillet = min(max(render_worker.COVE_FILLET_FRACTION * wall_radius, fillet0),
                 render_worker.COVE_FILLET_MAX_FRACTION * wall_radius)
    along = (wall_radius - fillet) + daway
    half_v = math.tan(math.radians(8.37))
    half_h = math.tan(math.radians(11.96))
    pitch = math.radians(pitch_deg)
    # Drop the camera so the far-side tangent projects to row 0.35 (ndc_y 0.30).
    drop = along * (math.sin(pitch) - 0.30 * half_v * math.cos(pitch)) / (
        math.cos(pitch) + 0.30 * half_v * math.sin(pitch))
    yaw = math.radians(yaw_deg)
    sin_y, cos_y = math.sin(yaw), math.cos(yaw)
    sin_p, cos_p = math.sin(pitch), math.cos(pitch)
    matrix = _RotatedFakeMatrix(
        _V(cos_y, sin_y, 0.0),
        _V(-sin_y * sin_p, cos_y * sin_p, cos_p),
        _V(sin_y * cos_p, -cos_y * cos_p, sin_p),
        _V(px + daway * sin_y, py - daway * cos_y, pz + drop))
    corners = [_V(half_h, half_v, -1.0), _V(-half_h, half_v, -1.0),
               _V(half_h, -half_v, -1.0), _V(-half_h, -half_v, -1.0)]
    cam = _FakeCamera(_FakeCamData(corners), _V(0.0, 0.0, 0.0))
    cam.matrix_world = matrix
    return _FakeScene(cam)


class FloorCameraMatrixFreshnessTests(unittest.TestCase):
    """The floor bound must be derived from the camera's evaluated transform,
    never a stale pre-depsgraph matrix_world (run2 az42 regression)."""

    @staticmethod
    def _worker():
        import render_worker
        return render_worker

    def test_view_layer_updates_before_camera_matrix_read(self):
        worker = self._worker()
        cam = _UpdatableFakeCamera(
            _FakeCamData([_V(-1, -1, -1), _V(1, 1, -1)]), _V(0, 0, 10))
        view_layer = type("ViewLayer", (), {"update_calls": 0})()

        def _update():
            view_layer.update_calls += 1
            cam.apply_update()

        view_layer.update = _update
        bpy = mock.MagicMock()
        bpy.context.view_layer = view_layer
        with mock.patch.object(worker, "bpy", bpy):
            rays, camera_origin, forward = worker._camera_corner_rays(
                _FakeScene(cam))
        # The update ran exactly once and BEFORE the matrix read: without it
        # the stale identity leaves the camera at the origin (the run2
        # FLOOR_BEHIND_CAMERA signature).
        self.assertEqual(view_layer.update_calls, 1)
        self.assertEqual(camera_origin, (0.0, 0.0, 10.0))
        self.assertEqual(forward, (0.0, 0.0, -1.0))
        for (origin, direction), corner in zip(rays, ((-1.0, -1.0, -1.0),
                                                      (1.0, 1.0, -1.0))):
            self.assertEqual(origin, (0.0, 0.0, 10.0))
            self.assertEqual(direction, corner)


class FloorGeometricBoundTests(unittest.TestCase):
    """Pure geometry: the cyc disc/wall must cover every frame-corner ray."""

    @staticmethod
    def _worker():
        import render_worker
        return render_worker

    def test_perspective_cove_profile_is_camera_radial_driven(self):
        worker = self._worker()
        # 3d target change: the disc is no longer stretched to the
        # frame-corner ground hits (that buried the cove and produced the az42
        # band); the profile now follows the camera radial.
        # Camera at (0,0,10), corner rays through local (+-1,+-1,-1): each hits
        # z=0 at t=10, i.e. (+-10,+-10,0).
        rays = [((0.0, 0.0, 10.0), (sx, sy, -1.0))
                for sx in (-1.0, 1.0) for sy in (-1.0, 1.0)]
        floor_r, _, fillet, wall_r = worker.required_cove_profile(
            rays, [], (0.0, 0.0, 0.0), (0.0, 0.0, 10.0), (0.0, 0.0, -1.0), 0.5)
        self.assertAlmostEqual(wall_r, worker.COVE_CAM_CLEARANCE_M)
        self.assertAlmostEqual(floor_r, wall_r - fillet)
        # Off-centre cove axis: cam_radial grows by the axis offset and the
        # wall follows it.
        _, _, _, wall_r2 = worker.required_cove_profile(
            rays, [], (2.0, -1.0, 0.0), (0.0, 0.0, 10.0), (0.0, 0.0, -1.0), 0.5)
        self.assertAlmostEqual(
            wall_r2, math.hypot(2.0, 1.0) + worker.COVE_CAM_CLEARANCE_M)
        self.assertGreater(wall_r2, wall_r)

    def test_direction_scale_leaves_extent_and_clipping_identical(self):
        """The ray parameter t is scale-bearing; extent and the clip gate
        must depend only on the hit point and its axial depth."""
        worker = self._worker()
        camera_origin = (0.0, 0.0, 10.0)
        forward = (0.0, 0.0, -1.0)
        base = (3.0, 2.0, -1.0)
        # 3d target change: the disc is no longer ray-derived, so its
        # scale-invariance is retired. The derived PROFILE must still be
        # direction-scale invariant (t is scale-bearing), and the clip gate
        # still keys off the hit's axial depth.
        for scale in (0.1, 1.0, 10.0):
            rays = [(camera_origin,
                     (base[0] * scale, base[1] * scale, base[2] * scale))]
            floor_r = worker.required_cove_profile(
                rays, [], (0.0, 0.0, 0.0), camera_origin, forward, 0.5,
                clip_end=11.0)[0]
            # Hit is fixed at (30, 20, 0); axial depth is 10 regardless of
            # the direction scale (t itself ranges 1..100).
            self.assertAlmostEqual(floor_r, 2.88)
            with self.assertRaisesRegex(RuntimeError,
                                        "FLOOR_EDGE_BEYOND_CLIP_END"):
                worker.required_cove_profile(
                    rays, [], (0.0, 0.0, 0.0), camera_origin, forward, 0.5,
                    clip_end=10.0)
        # Wall variant: direction (3,0,4) crosses wall_radius 5 at
        # t = 5/(3s), so the crossing is fixed at z = 10 + 20/3 and the
        # axial depth (along a forward parallel to the ray) is fixed at 25/3.
        wall_fwd = (0.6, 0.0, 0.8)
        for scale in (0.1, 1.0, 10.0):
            rays = [((0.0, 0.0, 10.0), (3.0 * scale, 0.0, 4.0 * scale))]
            height = worker.required_wall_height(
                rays, (0.0, 0.0, 0.0), camera_origin, wall_fwd,
                wall_radius=5.0, clip_end=200.0)
            self.assertAlmostEqual(height, (10.0 + 20.0 / 3.0) * 1.05)
            with self.assertRaisesRegex(RuntimeError,
                                        "FLOOR_EDGE_BEYOND_CLIP_END"):
                worker.required_wall_height(
                    rays, (0.0, 0.0, 0.0), camera_origin, wall_fwd,
                    wall_radius=5.0, clip_end=8.0)

    def test_above_horizon_rays_derive_wall_height(self):
        worker = self._worker()
        # The below-horizon corner is owned by the disc; the upward corner
        # derives the wall instead of failing.
        rays = [((0.0, 0.0, 10.0), (1.0, 1.0, -1.0)),
                ((0.0, 0.0, 10.0), (1.0, 0.0, 1.0))]
        height = worker.required_wall_height(
            rays, (0.0, 0.0, 0.0), (0.0, 0.0, 10.0), (0.0, 0.0, -1.0),
            wall_radius=6.0)
        # xy speed 1: crosses radius 6 at t=6, z_hit = 10 + 6.
        self.assertAlmostEqual(height, 16.0 * 1.05)

    def test_vertical_ray_cannot_be_covered_fails_loud(self):
        worker = self._worker()
        rays = [((0.0, 0.0, 10.0), (0.0, 0.0, 1.0))]
        with self.assertRaisesRegex(RuntimeError, "CYC_WALL_UNREACHABLE"):
            worker.required_wall_height(
                rays, (0.0, 0.0, 0.0), (0.0, 0.0, 10.0), (0.0, 0.0, -1.0),
                wall_radius=6.0)

    def test_camera_outside_the_wall_fails_loud(self):
        worker = self._worker()
        # 3d target change: the 4 m clearance clamp makes CYC_CAMERA_OUTSIDE
        # unreachable in normal use (wall_radius >= cam_radial + clearance),
        # so the guard is exercised defensively by removing the clearance:
        # wall_radius then equals cam_radial and the check must fire.
        bpy = mock.MagicMock()
        bpy.context.scene.objects = []
        # clip_end raised so the guard under test, not the wall clip gate,
        # is what fires.
        cam = _FakeCamera(
            _FakeCamData([_V(-1.0, 0.0, -1.0)] * 4, clip_end=1000.0),
            _V(100.0, 0.0, 10.0))
        with mock.patch.object(worker, "bpy", bpy), \
                mock.patch.object(worker, "COVE_CAM_CLEARANCE_M", 0.0):
            with self.assertRaisesRegex(RuntimeError, "CYC_CAMERA_OUTSIDE"):
                worker.build_studio_floor(0.5, scene=_FakeScene(cam))

    def test_hit_behind_camera_fails_loud(self):
        worker = self._worker()
        # 3d target change: the behind-camera guard now lives in the cove
        # profile's disc-hit scan. Camera below the floor plane looking down:
        # t = (0-(-5))/-1 < 0.
        rays = [((0.0, 0.0, -5.0), (0.0, 0.0, -1.0))]
        with self.assertRaisesRegex(RuntimeError, "FLOOR_BEHIND_CAMERA"):
            worker.required_cove_profile(
                rays, [], (0.0, 0.0, 0.0), (0.0, 0.0, -5.0), (0.0, 0.0, -1.0),
                0.5)

    def test_hit_beyond_clip_end_fails_loud(self):
        worker = self._worker()
        camera_origin = (0.0, 0.0, 10.0)
        forward = (0.0, 0.0, -1.0)
        rays = [(camera_origin, (1.0, 0.0, -1.0))]  # hit at axial depth 10
        with self.assertRaisesRegex(RuntimeError, "FLOOR_EDGE_BEYOND_CLIP_END"):
            worker.required_cove_profile(rays, [], (0.0, 0.0, 0.0),
                                         camera_origin, forward, 0.5,
                                         clip_end=10.0)
        # Axial depth 10 is far inside clip_end 100; it only trips when the
        # clip is tightened below the true axial depth.
        self.assertGreater(
            worker.required_cove_profile(rays, [], (0.0, 0.0, 0.0),
                                         camera_origin, forward, 0.5,
                                         clip_end=11.0)[0], 0.0)
        with self.assertRaisesRegex(RuntimeError,
                                    "FLOOR_EDGE_BEYOND_CLIP_END"):
            worker.required_cove_profile(rays, [], (0.0, 0.0, 0.0),
                                         camera_origin, forward, 0.5,
                                         clip_end=9.0)
        # Wall variant: hit at axial depth 25/3 along a forward parallel to
        # the ray (direction (3,0,4) against wall_radius 5).
        rays = [((0.0, 0.0, 10.0), (3.0, 0.0, 4.0))]
        with self.assertRaisesRegex(RuntimeError,
                                    "FLOOR_EDGE_BEYOND_CLIP_END"):
            worker.required_wall_height(rays, (0.0, 0.0, 0.0),
                                        camera_origin, (0.6, 0.0, 0.8),
                                        wall_radius=5.0, clip_end=8.0)
        self.assertGreater(
            worker.required_wall_height(rays, (0.0, 0.0, 0.0),
                                        camera_origin, (0.6, 0.0, 0.8),
                                        wall_radius=5.0, clip_end=9.0), 0.0)

    def test_dof_margin_adds_defocus_blur_radius(self):
        worker = self._worker()
        # 3d target change: the disc radius is no longer ray-derived, so DOF
        # no longer enters floor_radius; it enters the WALL HEIGHT instead.
        rays = [((0.0, 0.0, 10.0), (1.0, 1.0, -1.0))]
        camera_origin = (0.0, 0.0, 10.0)
        forward = (0.0, 0.0, -1.0)
        # 85 mm at f/3.2: aperture radius 13.28125 mm.
        aperture = (85.0 / (2.0 * 3.2)) / 1000.0
        plain = worker.required_cove_profile(
            rays, [], (0.0, 0.0, 0.0), camera_origin, forward, 0.5)
        with_dof = worker.required_cove_profile(
            rays, [], (0.0, 0.0, 0.0), camera_origin, forward, 0.5,
            aperture_radius_m=aperture, focus_distance_m=5.0)
        # Floor and fillet radii are DOF-independent.
        self.assertAlmostEqual(plain[0], with_dof[0])
        self.assertAlmostEqual(plain[2], with_dof[2])
        # Wall height grows by the blur at the crossing's axial depth: the
        # (1,1,-1) ray crosses wall_radius 4 at z=10-2*sqrt2, axial depth
        # 2*sqrt2 -> blur a*|2*sqrt2 - 5|/5.
        depth = 2.0 * math.sqrt(2.0)
        self.assertAlmostEqual(with_dof[1] - plain[1],
                               aperture * abs(depth - 5.0) / 5.0)
        # Wall variant: crossing at axial depth sqrt(2)*4 for direction
        # (1,0,1) against wall_radius 4 with a parallel forward.
        rays = [((0.0, 0.0, 10.0), (1.0, 0.0, 1.0))]
        diag_fwd = (1.0 / math.sqrt(2.0), 0.0, 1.0 / math.sqrt(2.0))
        plain = worker.required_wall_height(
            rays, (0.0, 0.0, 0.0), camera_origin, diag_fwd, wall_radius=4.0)
        with_dof = worker.required_wall_height(
            rays, (0.0, 0.0, 0.0), camera_origin, diag_fwd, wall_radius=4.0,
            aperture_radius_m=aperture, focus_distance_m=5.0)
        depth = math.sqrt(2.0) * 4.0
        self.assertAlmostEqual(with_dof - plain,
                               aperture * abs(depth - 5.0) / 5.0)

    def test_orthographic_rays_use_corner_origins_and_forward_axis(self):
        worker = self._worker()
        cam = _FakeCamera(
            _FakeCamData([_V(-1, -1, -1), _V(1, 1, -1)], cam_type="ORTHO"),
            _V(0, 0, 10))
        rays, camera_origin, forward = worker._camera_corner_rays(
            _FakeScene(cam))
        self.assertEqual([r[0] for r in rays], [(-1.0, -1.0, 9.0),
                                                (1.0, 1.0, 9.0)])
        for _, direction in rays:
            self.assertEqual(direction, (0.0, 0.0, -1.0))
        # Ortho clipping is measured from the camera CENTRE, not the corner
        # origins, and the forward axis is normalized even if the matrix
        # carries scale.
        self.assertEqual(camera_origin, (0.0, 0.0, 10.0))
        self.assertEqual(forward, (0.0, 0.0, -1.0))

    def test_unsupported_camera_type_is_rejected_clearly(self):
        worker = self._worker()
        cam = _FakeCamera(_FakeCamData([_V(1, 1, -1)], cam_type="PANO"),
                          _V(0, 0, 10))
        with self.assertRaisesRegex(RuntimeError, "FLOOR_CAMERA_UNSUPPORTED"):
            worker._camera_corner_rays(_FakeScene(cam))

    def test_scene_without_camera_is_rejected_clearly(self):
        worker = self._worker()
        with self.assertRaisesRegex(RuntimeError, "FLOOR_CAMERA_MISSING"):
            worker._camera_corner_rays(_FakeScene(None))

    def test_build_derives_size_from_the_cove_profile(self):
        worker = self._worker()
        bpy = mock.MagicMock()
        bpy.context.scene.objects = []
        # 3d target change: the 3c legacy minimum is retired and the disc is
        # cove-derived, so this pins floor_radius == wall_radius - fillet and
        # the wall radius the coverage assertions were computed against. A
        # leftover legacy_min max would push the disc edge past wall_radius
        # and invert the cove.
        with mock.patch.object(worker, "bpy", bpy):
            worker.build_studio_floor(
                0.5, scene=_cove_camera((0.0, 0.0, 0.0), 0.5))
        verts = (bpy.data.meshes.new.return_value.from_pydata.call_args
                 .args[0])
        fillet0 = max(2.0 * 0.5, 0.5)
        wall_radius = max(10.0 + worker.COVE_CAM_CLEARANCE_M,
                          0.5 + fillet0 + worker.PRODUCT_FLOOR_MARGIN_M)
        fillet = min(max(worker.COVE_FILLET_FRACTION * wall_radius, fillet0),
                     worker.COVE_FILLET_MAX_FRACTION * wall_radius)
        floor_radius = wall_radius - fillet
        self.assertAlmostEqual(
            max(math.hypot(v[0], v[1]) for v in verts), wall_radius)
        disc_radii = {round(math.hypot(v[0], v[1]), 6) for v in verts}
        self.assertIn(round(floor_radius, 6), disc_radii)
        self.assertAlmostEqual(max(v[2] for v in verts), fillet)

        # A larger product whose 2*radius shape rule beats 0.28*wall but stays
        # under the 0.40*wall ceiling: the fillet lower clamp applies.
        with mock.patch.object(worker, "bpy", bpy):
            worker.build_studio_floor(
                2.0, scene=_cove_camera((0.0, 0.0, 0.0), 2.0))
        verts = (bpy.data.meshes.new.return_value.from_pydata.call_args
                 .args[0])
        self.assertAlmostEqual(
            max(math.hypot(v[0], v[1]) for v in verts), wall_radius)
        self.assertAlmostEqual(max(v[2] for v in verts),
                               max(2.0 * 2.0, 0.5))

    def test_build_without_a_camera_fails_loud_no_silent_small_plane(self):
        worker = self._worker()
        bpy = mock.MagicMock()
        bpy.context.scene.objects = []
        bpy.context.scene.camera = None
        with mock.patch.object(worker, "bpy", bpy):
            # Scene omitted: resolves bpy.context.scene, finds no camera,
            # and refuses instead of falling back to a quiet legacy plane.
            with self.assertRaisesRegex(RuntimeError,
                                        "FLOOR_CAMERA_MISSING"):
                worker.build_studio_floor(1.5)
            # Explicit camera-less scene fails the same way.
            with self.assertRaisesRegex(RuntimeError,
                                        "FLOOR_CAMERA_MISSING"):
                worker.build_studio_floor(1.5, scene=_FakeScene(None))


class CoveProfileDerivationTests(unittest.TestCase):
    """Batch-3d cove-in-frame derivation (spec 3.1-3.3): clamp chain, dense
    top-edge scan, and the loud coverage/band gates."""

    @staticmethod
    def _worker():
        import render_worker
        return render_worker

    def test_clearance_clamp_wins_for_a_small_product(self):
        worker = self._worker()
        rays = [((10.0, 0.0, 10.0), (-1.0, 0.0, -1.0))]
        floor_r, wall_h, fillet, wall_r = worker.required_cove_profile(
            rays, [], (0.0, 0.0, 0.0), (10.0, 0.0, 10.0), (0.0, 0.0, -1.0),
            0.5)
        self.assertAlmostEqual(wall_r, 10.0 + worker.COVE_CAM_CLEARANCE_M)
        self.assertAlmostEqual(wall_h, fillet)
        self.assertAlmostEqual(floor_r, wall_r - fillet)

    def test_product_clamp_beats_clearance_and_the_fillet_refuses(self):
        # A product large enough to beat the clearance term also drives the
        # 2*radius shape rule past the 0.40*wall ceiling, so the chain must
        # refuse rather than emit inverted geometry.
        worker = self._worker()
        product = 5.0
        fillet0 = max(2.0 * product, 0.5)
        product_clamp = product + fillet0 + worker.PRODUCT_FLOOR_MARGIN_M
        clearance_clamp = 10.0 + worker.COVE_CAM_CLEARANCE_M
        self.assertGreater(product_clamp, clearance_clamp)
        rays = [((10.0, 0.0, 10.0), (-1.0, 0.0, -1.0))]
        with self.assertRaisesRegex(RuntimeError, "COVE_FILLET_CLAMP_INVALID"):
            worker.required_cove_profile(
                rays, [], (0.0, 0.0, 0.0), (10.0, 0.0, 10.0), (0.0, 0.0, -1.0),
                product)

    def test_fillet_clamp_fraction_lower_bound_and_ceiling(self):
        worker = self._worker()
        rays = [((10.0, 0.0, 10.0), (-1.0, 0.0, -1.0))]
        origin = (10.0, 0.0, 10.0)
        fwd = (0.0, 0.0, -1.0)
        # Small product: the 0.28*wall target applies.
        _, _, fillet, wall_r = worker.required_cove_profile(
            rays, [], (0.0, 0.0, 0.0), origin, fwd, 0.5)
        self.assertAlmostEqual(fillet, worker.COVE_FILLET_FRACTION * wall_r)
        # Product 2.0: 2*product (4.0) beats 0.28*wall (3.92) but stays under
        # 0.40*wall (5.6), so the lower clamp applies and the wall is unchanged.
        _, _, fillet2, wall_r2 = worker.required_cove_profile(
            rays, [], (0.0, 0.0, 0.0), origin, fwd, 2.0)
        self.assertAlmostEqual(fillet2, 4.0)
        self.assertAlmostEqual(wall_r2, wall_r)
        # Forced low ceiling: the clamp returns the 0.40*wall ceiling, never a
        # value above it.
        with mock.patch.object(worker, "COVE_FILLET_MAX_FRACTION", 0.25):
            _, _, fillet3, wall_r3 = worker.required_cove_profile(
                rays, [], (0.0, 0.0, 0.0), origin, fwd, 0.5)
        self.assertAlmostEqual(fillet3, 0.25 * wall_r3)

    def test_wall_height_uses_dense_top_edge_and_fillet_floor(self):
        worker = self._worker()
        origin = (0.0, 0.0, 10.0)
        fwd = (0.0, 0.0, -1.0)
        cyc = (0.0, 0.0, 0.0)
        corners = [((0.0, 0.0, 10.0), (0.0, 0.0, -1.0))]  # disc-owned
        top = [((0.0, 0.0, 10.0), (2.0, 0.0, -0.1))]       # misses the disc
        # Corner-only would derive H = 0 (the disc owns it); the interior
        # top-edge sample that misses the flat disc must raise the wall.
        corner_only = worker.required_wall_height(
            corners, cyc, origin, fwd, wall_radius=5.0, floor_radius=3.0)
        dense = worker.required_wall_height(
            corners + top, cyc, origin, fwd, wall_radius=5.0, floor_radius=3.0)
        self.assertAlmostEqual(corner_only, 0.0)
        self.assertGreater(dense, 0.0)

    def test_below_horizon_disc_escape_and_fillet_dominance(self):
        worker = self._worker()
        origin = (0.0, 0.0, 10.0)
        fwd = (0.0, 0.0, -1.0)
        cyc = (0.0, 0.0, 0.0)
        # A below-horizon ray that misses the flat disc raises H above fillet.
        miss = [((0.0, 0.0, 10.0), (1.0, 0.0, -0.2))]
        floor_r, wall_h, fillet, wall_r = worker.required_cove_profile(
            miss, [], cyc, origin, fwd, 0.1)
        self.assertGreater(wall_h, fillet)
        self.assertAlmostEqual(floor_r, wall_r - fillet)
        # The exact-value pin for the retired legacy minimum: the floor radius
        # is exactly wall_radius - fillet_radius, never a max with anything.
        self.assertAlmostEqual(
            floor_r,
            4.0 - min(max(worker.COVE_FILLET_FRACTION * 4.0, 0.5), 1.6))
        # A below-horizon ray that lands on the disc keeps H = fillet.
        inside = [((0.0, 0.0, 10.0), (0.2, 0.0, -1.0))]
        _, wall_h2, fillet2, _ = worker.required_cove_profile(
            inside, [], cyc, origin, fwd, 0.1)
        self.assertAlmostEqual(wall_h2, fillet2)

    def test_axis_aim_divergence_fires_beyond_tolerance(self):
        worker = self._worker()
        rays = [((0.0, 0.0, 10.0), (0.0, 0.0, -1.0))]
        with self.assertRaisesRegex(RuntimeError, "COVE_AXIS_AIM_DIVERGENT"):
            worker.required_cove_profile(
                rays, [], (0.0, 0.0, 0.0), (0.0, 0.0, 10.0), (0.0, 0.0, -1.0),
                0.5, aim_xy=(0.5, 0.0))
        profile = worker.required_cove_profile(
            rays, [], (0.0, 0.0, 0.0), (0.0, 0.0, 10.0), (0.0, 0.0, -1.0),
            0.5, aim_xy=(0.1, 0.0))
        self.assertAlmostEqual(profile[3], 4.0)

    def test_cove_ray_escape_fires_for_an_unreachable_vertex(self):
        worker = self._worker()
        # Defensive vertical-ray branch: the ray never meets the cylinder.
        rays = [((0.0, 0.0, 10.0), (0.0, 0.0, 1.0))]
        with self.assertRaisesRegex(RuntimeError, "COVE_RAY_ESCAPE"):
            worker._assert_cove_rays_covered(
                rays, (0.0, 0.0, 0.0), floor_radius=3.0, wall_radius=5.0,
                wall_height=2.0)

    def test_tangent_band_uses_the_far_side_and_fires_out_of_band(self):
        worker = self._worker()
        scene = _cove_camera((0.0, 0.0, 0.0), 0.5)
        rays, origin, fwd = worker._camera_corner_rays(scene)
        floor_r = worker.required_cove_profile(
            rays, worker._camera_top_edge_rays(scene), (0.0, 0.0, 0.0), origin,
            fwd, 0.5)[0]
        row = worker._cove_tangent_row(scene, (0.0, 0.0, 0.0), floor_r, origin)
        self.assertAlmostEqual(row, 0.35, places=2)
        # A point behind the camera cannot be projected: both-axes filtering
        # returns None rather than a garbage row (the -199.98 behind-camera
        # garbage the raw preflight showed).
        behind = worker._camera_ndc(
            scene, (origin[0], origin[1] + 1.0, origin[2] + 5.0))
        self.assertIsNone(behind)
        # A band that excludes the real cove line makes the build fail loudly.
        bpy = mock.MagicMock()
        bpy.context.scene.objects = []
        with mock.patch.object(worker, "bpy", bpy), \
                mock.patch.object(worker, "COVE_TANGENT_ROW_BAND", (0.10, 0.20)):
            with self.assertRaisesRegex(RuntimeError, "COVE_TANGENT_OUT_OF_BAND"):
                worker.build_studio_floor(
                    0.5, scene=_cove_camera((0.0, 0.0, 0.0), 0.5))

    def test_floor_under_product_and_persp_required(self):
        worker = self._worker()
        rays = [((10.0, 0.0, 10.0), (-1.0, 0.0, -1.0))]
        origin = (10.0, 0.0, 10.0)
        fwd = (0.0, 0.0, -1.0)
        # Forced near-total fillet: the cove floor can no longer clear the
        # product footprint, so the guard must refuse.
        with mock.patch.object(worker, "COVE_FILLET_FRACTION", 0.99), \
                mock.patch.object(worker, "COVE_FILLET_MAX_FRACTION", 0.99):
            with self.assertRaisesRegex(RuntimeError, "COVE_FLOOR_UNDER_PRODUCT"):
                worker.required_cove_profile(
                    rays, [], (0.0, 0.0, 0.0), origin, fwd, 2.0)
        # An ORTHO camera breaks the inside-the-cylinder argument, so both the
        # pure function and the build path refuse it.
        with self.assertRaisesRegex(RuntimeError, "COVE_PERSP_REQUIRED"):
            worker.required_cove_profile(
                rays, [], (0.0, 0.0, 0.0), origin, fwd, 0.5,
                camera_type="ORTHO")
        bpy = mock.MagicMock()
        bpy.context.scene.objects = []
        ortho = _FakeCamera(
            _FakeCamData([_V(-1, -1, -1), _V(1, -1, -1), _V(-1, 1, -1),
                          _V(1, 1, -1)], cam_type="ORTHO"), _V(0, 0, 10))
        with mock.patch.object(worker, "bpy", bpy):
            with self.assertRaisesRegex(RuntimeError, "COVE_PERSP_REQUIRED"):
                worker.build_studio_floor(0.5, scene=_FakeScene(ortho))

    def test_azimuth_invariance_is_a_tolerance(self):
        worker = self._worker()
        wall_radii = []
        for yaw in (0.0, 120.0, 240.0):
            scene = _cove_camera((0.0, 0.0, 0.0), 0.5, yaw_deg=yaw)
            rays, origin, fwd = worker._camera_corner_rays(scene)
            wall_radii.append(worker.required_cove_profile(
                rays, worker._camera_top_edge_rays(scene), (0.0, 0.0, 0.0),
                origin, fwd, 0.5)[3])
        self.assertLessEqual(max(wall_radii) - min(wall_radii), 0.05)


class BackgroundStepTests(unittest.TestCase):
    """The cove-in-frame probe metric (spec 3.5)."""

    @staticmethod
    def _probe():
        spec = importlib.util.spec_from_file_location(
            "probe_sequence", ROOT / "scripts/probe_sequence.py")
        probe = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(probe)
        return probe

    def test_known_step_is_measured_and_product_columns_ignored(self):
        probe = self._probe()
        height, width = 160, 40
        mask = np.zeros((height, width), dtype=np.uint8)
        mask[40:80, 10:30] = 255
        image = np.zeros((height, width, 3), dtype=np.uint8)
        image[:101] = 100
        image[101:] = 140
        image[:, 10:30] = 255  # hard step inside the product columns
        measured = probe.measure_background_step(Image.fromarray(image),
                                                 Image.fromarray(mask))
        self.assertEqual(measured["num_rows"], height)
        self.assertAlmostEqual(measured["max_step"], 40.0, places=3)
        self.assertEqual(measured["step_row"], 101)

    def test_a_smooth_gradient_has_a_small_step(self):
        probe = self._probe()
        height, width = 200, 30
        mask = np.zeros((height, width), dtype=np.uint8)
        rows = np.linspace(50, 150, height, dtype=np.uint8)
        image = np.zeros((height, width, 3), dtype=np.uint8)
        image[:] = rows[:, None, None]
        measured = probe.measure_background_step(Image.fromarray(image),
                                                 Image.fromarray(mask))
        self.assertLess(measured["max_step"], 2.0)

    def test_height_comes_from_the_image_not_a_default(self):
        probe = self._probe()
        for height in (24, 1250):
            image = np.full((height, 8, 3), 90, dtype=np.uint8)
            mask = np.zeros((height, 8), dtype=np.uint8)
            measured = probe.measure_background_step(Image.fromarray(image),
                                                     Image.fromarray(mask))
            self.assertEqual(measured["num_rows"], height)


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


class CycMeshDataTests(unittest.TestCase):
    """Pure mesh geometry of the revolved cyclorama profile."""

    @staticmethod
    def _mesh(radius=5.0, wall=3.0, fillet=1.0, center=(0.0, 0.0, 0.0)):
        import render_worker
        return render_worker.cyc_mesh_data(radius, wall, fillet, center)

    def test_vertex_and_face_counts(self):
        import render_worker
        angular = render_worker.CYC_ANGULAR_SEGMENTS
        profile_points = 2 + render_worker.FILLET_ARC_SEGMENTS
        verts, faces = self._mesh()
        self.assertEqual(len(verts), 1 + angular * profile_points)
        self.assertEqual(len(faces),
                         angular + angular * (profile_points - 1))

    def test_disc_fan_normals_point_up(self):
        import render_worker
        angular = render_worker.CYC_ANGULAR_SEGMENTS
        verts, faces = self._mesh()
        for face in faces[:angular]:
            p0, p1, p2 = (verts[face[0]], verts[face[1]], verts[face[2]])
            normal = _cross((p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2]),
                            (p2[0] - p0[0], p2[1] - p0[1], p2[2] - p0[2]))
            self.assertGreater(normal[2], 0.0)

    def test_wall_ring_quad_normals_point_inward(self):
        import render_worker
        angular = render_worker.CYC_ANGULAR_SEGMENTS
        verts, faces = self._mesh()
        # The last angular faces close the top wall ring; their normals
        # must point toward the axis (dot with the radial vector < 0).
        for face in faces[-angular:]:
            p0, p1, p2 = (verts[face[0]], verts[face[1]], verts[face[2]])
            normal = _cross((p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2]),
                            (p2[0] - p0[0], p2[1] - p0[1], p2[2] - p0[2]))
            radial = (p0[0], p0[1], 0.0)
            self.assertLess(normal[0] * radial[0] + normal[1] * radial[1],
                            0.0)

    def test_fillet_ring_radii_increase_with_ring_z(self):
        import render_worker
        angular = render_worker.CYC_ANGULAR_SEGMENTS
        segments = render_worker.FILLET_ARC_SEGMENTS
        center = (1.0, 2.0, 0.5)
        verts, _ = self._mesh(radius=5.0, wall=3.0, fillet=1.0,
                              center=center)
        prev = None
        for i in range(1, segments + 1):
            ring = verts[1 + i * angular: 1 + (i + 1) * angular]
            mean_r = (sum(math.hypot(v[0] - center[0], v[1] - center[1])
                          for v in ring) / angular)
            mean_z = sum(v[2] for v in ring) / angular
            if prev is not None:
                self.assertGreater(mean_r, prev[0])
                self.assertGreater(mean_z, prev[1])
            prev = (mean_r, mean_z)

    def test_zero_nominal_wall_skips_the_degenerate_ring(self):
        import render_worker
        angular = render_worker.CYC_ANGULAR_SEGMENTS
        segments = render_worker.FILLET_ARC_SEGMENTS
        verts, faces = self._mesh(radius=5.0, wall=1.0, fillet=1.0)
        profile_points = 1 + segments  # disc edge + arc; no wall-top point
        self.assertEqual(len(verts), 1 + angular * profile_points)
        self.assertEqual(len(faces), angular * profile_points)
        for face in faces:
            # Both halves of every face must be non-degenerate: a sliver
            # quad with an exact-zero first triangle used to slip through.
            # Triangulate (v0,v1,v2)+(v0,v2,v3) for quads; fan triangles are
            # (v0,v1,v2) only. Real rings differ by ~1e-1 m; degenerate
            # ones by 0.0, so 1e-9 separates them cleanly.
            tris = [(face[0], face[1], face[2])]
            if len(face) == 4:
                tris.append((face[0], face[2], face[3]))
            for tri in tris:
                p0, p1, p2 = (verts[tri[0]], verts[tri[1]], verts[tri[2]])
                area2 = _cross((p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2]),
                               (p2[0] - p0[0], p2[1] - p0[1], p2[2] - p0[2]))
                mag = math.sqrt(sum(c * c for c in area2))
                self.assertGreater(mag, 1e-9)
        self.assertAlmostEqual(max(v[2] for v in verts), 1.0)


class CycGeometryBlenderTests(unittest.TestCase):
    """Real-Blender smoke check: the cyc builds, validates, and matches the
    derived profile. Skipped when the pinned Blender is unavailable."""

    BLENDER = Path(os.environ.get("MSP_BLENDER_BIN")
                   or r"C:/Program Files/Blender Foundation/Blender 5.1/blender.exe")

    def test_cyc_builds_in_real_blender(self):
        if not self.BLENDER.is_file():
            self.skipTest(f"Pinned Blender unavailable: {self.BLENDER}")
        with tempfile.TemporaryDirectory() as tmp:
            driver = Path(tmp) / "_drive.py"
            driver.write_text(
                "import math, os, sys\n"
                "import bpy\n"
                "for _o in list(bpy.data.objects):\n"
                "    bpy.data.objects.remove(_o)\n"
                "saved, sys.argv = sys.argv, [a for a in sys.argv if a != '--']\n"
                "sys.path.insert(0, os.environ['MSP_REPO'])\n"
                "import render_worker as w\n"
                "sys.argv = saved\n"
                "cam_data = bpy.data.cameras.new('Cam')\n"
                "cam = bpy.data.objects.new('Cam', cam_data)\n"
                "bpy.context.scene.collection.objects.link(cam)\n"
                "cam_data.lens = 85.0\n"
                "bpy.context.scene.render.resolution_x = 1800\n"
                "bpy.context.scene.render.resolution_y = 1250\n"
                "bpy.context.scene.render.resolution_percentage = 100\n"
                # 3d target change: the camera frames the cove (far tangent at
                # row ~0.35) so the in-frame assertions pass; the 3c-era
                # upward camera now fails the cove band, spec 3.3.
                "cam.location = (0.0, -10.0, 4.0607)\n"
                "cam.rotation_euler = (math.radians(76.04), 0.0, 0.0)\n"
                "bpy.context.scene.camera = cam\n"
                "obj = w.build_studio_floor(0.5)\n"
                "failures = []\n"
                "def check(name, cond, detail=''):\n"
                "    if not cond:\n"
                "        failures.append(f'{name} {detail}')\n"
                "check('object_name', obj.name == 'MSP_StudioFloor', obj.name)\n"
                "mesh = obj.data\n"
                "check('validate_clean', mesh.validate() is False)\n"
                "mesh.update()\n"
                "rays, origin, fwd = w._camera_corner_rays(bpy.context.scene)\n"
                "seat = (0.0, 0.0, 0.0)\n"
                "clip = float(cam_data.clip_end)\n"
                "top_rays = w._camera_top_edge_rays(bpy.context.scene)\n"
                "floor_r, wall_h, rc, wall_r = w.required_cove_profile(\n"
                "    rays, top_rays, seat, origin, fwd, 0.5, clip_end=clip)\n"
                "check('cove_floor', abs(floor_r - (wall_r - rc)) < 1e-6)\n"
                "max_r = max(math.hypot(v.co.x, v.co.y) for v in mesh.vertices)\n"
                "max_z = max(v.co.z for v in mesh.vertices)\n"
                "min_z = min(v.co.z for v in mesh.vertices)\n"
                "check('max_radius', abs(max_r - wall_r) < 1e-4,\n"
                "      f'{max_r} vs {wall_r}')\n"
                "check('max_z', abs(max_z - wall_h) < 1e-4,\n"
                "      f'{max_z} vs {wall_h}')\n"
                "check('min_z', abs(min_z) < 1e-6, f'{min_z}')\n"
                # 3d target change: on this rig wall_h == rc, so the wall
                # segment is SKIPPED ([R4]) and the profile tops out on the
                # quarter-arc at (wall_r, seat+rc). Check the arc-top ring
                # reaches wall_r with an inward normal instead of a wall ring.
                "check('wall_skipped', wall_h <= rc + 1e-9)\n"
                "last_ring = mesh.polygons[-w.CYC_ANGULAR_SEGMENTS:]\n"
                "vs = [mesh.vertices[i].co for i in last_ring[0].vertices]\n"
                "n = (vs[1] - vs[0]).cross(vs[2] - vs[0])\n"
                "check('arc_normal_inward', n.x * vs[0].x + n.y * vs[0].y < 0,\n"
                "      str(n))\n"
                "arc_top_r = max(math.hypot(v.x, v.y) for v in vs)\n"
                "check('arc_tops_at_wall_r', abs(arc_top_r - wall_r) < 1e-4,\n"
                "      f'{arc_top_r} vs {wall_r}')\n"
                "mat = mesh.materials[0]\n"
                "bsdf = mat.node_tree.nodes.get('Principled BSDF')\n"
                "check('material', bsdf is not None)\n"
                "if bsdf:\n"
                "    check('roughness',\n"
                "          abs(bsdf.inputs['Roughness'].default_value - 0.7)\n"
                "          < 1e-6,\n"
                "          str(bsdf.inputs['Roughness'].default_value))\n"
                # Zero-nominal-wall (wall-skipped) profile: this rig already
                # derives wall_h == rc, so a rebuild exercises the arc-topping
                # geometry with no degenerate faces (a straight-down camera
                # now fails the in-frame cove band, spec 3.3).
                "bpy.data.objects.remove(obj, do_unlink=True)\n"
                "obj2 = w.build_studio_floor(0.5)\n"
                "check('steep_object_name', obj2.name == 'MSP_StudioFloor',\n"
                "      obj2.name)\n"
                "mesh2 = obj2.data\n"
                "check('steep_validate_clean', mesh2.validate() is False)\n"
                "mesh2.update()\n"
                "zero_area = [p for p in mesh2.polygons if p.area <= 1e-12]\n"
                "check('steep_no_zero_area_faces', not zero_area,\n"
                "      f'{len(zero_area)} zero-area faces')\n"
                "if failures:\n"
                "    print('CYC_SMOKE_FAIL:', '; '.join(failures))\n"
                "else:\n"
                "    print('CYC_SMOKE_OK')\n",
                encoding="utf-8")
            import subprocess
            result = subprocess.run(
                [str(self.BLENDER), "--background", "--factory-startup",
                 "--python", str(driver)],
                capture_output=True, text=True, timeout=300,
                env=dict(os.environ, MSP_REPO=str(ROOT)))
            self.assertIn("CYC_SMOKE_OK", result.stdout,
                          msg=result.stdout + result.stderr)
            self.assertNotIn("CYC_SMOKE_FAIL", result.stdout)


class RenderReportFloorTimingTests(unittest.TestCase):
    """The legacy report shape is a contract; floor pass timings are opt-in."""

    def setUp(self):
        import render_worker
        from types import SimpleNamespace
        self.worker = render_worker
        app = SimpleNamespace(version=(5, 1, 1), version_string="5.1.1",
                              build_hash="test-hash")
        patcher = mock.patch.object(render_worker, "bpy",
                                    SimpleNamespace(app=app))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_legacy_report_shape_is_unchanged_without_floor_timings(self):
        report = self.worker._render_report([], True, 0.5, 2.0, 2.5)
        self.assertEqual(report["timings"],
                         {"prepare": 0.5, "render": 2.0, "total": 2.5})

    def test_floor_timings_appear_only_when_measured_values_are_supplied(self):
        report = self.worker._render_report(
            [], True, 0.5, 3.0, 4.0,
            beauty_render_seconds=2.1, matte_render_seconds=0.8)
        self.assertEqual(report["timings"]["beauty_render_seconds"], 2.1)
        self.assertEqual(report["timings"]["matte_render_seconds"], 0.8)
        # Floor mode passes both; each is independent in the report shape.
        only_matte = self.worker._render_report(
            [], True, 0.5, 3.0, 4.0, matte_render_seconds=0.8)
        self.assertNotIn("beauty_render_seconds", only_matte["timings"])
        self.assertEqual(only_matte["timings"]["matte_render_seconds"], 0.8)


class SeedPinningTests(unittest.TestCase):
    def test_pin_sets_shared_seed_and_restore_round_trips(self):
        import render_worker

        class FakeCycles:
            seed = 7
            use_animated_seed = True

        class FakeScene:
            cycles = FakeCycles()

        scene = FakeScene()
        saved = render_worker.pin_render_seed(scene)
        self.assertEqual(scene.cycles.seed, 0)
        self.assertFalse(scene.cycles.use_animated_seed)
        render_worker.restore_render_seed(scene, saved)
        self.assertEqual(scene.cycles.seed, 7)
        self.assertTrue(scene.cycles.use_animated_seed)
        # Safe no-op when no pin was taken.
        render_worker.restore_render_seed(scene, None)


class MatteAlternateSourceBlenderTests(unittest.TestCase):
    BLENDER = Path(os.environ.get("MSP_BLENDER_BIN")
                   or r"C:/Program Files/Blender Foundation/Blender 5.1/blender.exe")

    def test_matte_from_beauty_matte_source(self):
        if not self.BLENDER.is_file():
            self.skipTest(f"Pinned Blender unavailable: {self.BLENDER}")
        with tempfile.TemporaryDirectory() as tmp:
            alpha = np.zeros((32, 48), dtype=np.uint8)
            alpha[8:24, 12:36] = 255
            matte = np.dstack([alpha] * 3 + [alpha]).astype(np.uint8)
            Image.fromarray(matte).save(Path(tmp) / "beauty-matte.png")
            driver = Path(tmp) / "_drive.py"
            driver.write_text(
                "import os, sys\n"
                "saved, sys.argv = sys.argv, [a for a in sys.argv if a != '--']\n"
                "sys.path.insert(0, os.environ['MSP_REPO'])\n"
                "import render_worker\n"
                "sys.argv = saved\n"
                "render_worker.write_matte_pass(os.environ['MSP_OUT'],\n"
                "    source_filename='beauty-matte.png')\n",
                encoding="utf-8")
            import subprocess
            result = subprocess.run(
                [str(self.BLENDER), "--background", "--factory-startup",
                 "--python", str(driver)],
                capture_output=True, text=True, timeout=300,
                env=dict(os.environ, MSP_REPO=str(ROOT), MSP_OUT=tmp))
            self.assertIn("Wrote alpha matte", result.stdout,
                          msg=result.stdout + result.stderr)
            mask = np.asarray(Image.open(Path(tmp) / "mask.png").convert("L"))
            self.assertLessEqual(
                int(np.abs(mask.astype(int) - alpha.astype(int)).max()), 1)


class CliFloorRouteTests(unittest.TestCase):
    def test_cmd_composite_routes_floor_jobs_to_the_floor_finishing(self):
        from msp_render_cli import cli
        with tempfile.TemporaryDirectory() as tmp:
            manifest = {
                "job_id": "floor_job", "package_model": "RL300_SAFE",
                "cad_source": {"file_path": "cad/x.blend"},
                "camera": {"preset": "CUSTOM"},
                "livery": {"preset": "preserve_existing"},
                "lighting": {"preset": "studio_white", "floor": {"enabled": True}},
                "output": {"width": 100, "height": 80, "film_transparent": False,
                           "output_dir": os.path.join(tmp, "out")},
                "compositing": {"enabled": True, "shadow_opacity": 0.35,
                                "background_plate": "backgrounds/p.png"},
            }
            manifest_path = os.path.join(tmp, "job.json")
            with open(manifest_path, "w", encoding="utf-8") as f:
                json.dump(manifest, f)
            beauty_path = os.path.join(tmp, "out", "beauty.png")
            os.makedirs(os.path.dirname(beauty_path))
            Image.new("RGBA", (100, 80), (120, 120, 120, 255)).save(beauty_path)
            args = argparse.Namespace(
                manifest=manifest_path, product=None, background=None,
                output=None, shadow_opacity=None)
            floor_result = {"output_path": "x", "status": "success",
                            "fidelity_gate_pass": True, "mask_gate_pass": True,
                            "saved_check_pass": True, "max_pixel_drift": 0,
                            "mean_pixel_drift": 0.0,
                            "dimensions": (100, 80), "coverage_pct": 15.0,
                            "mode": "rendered_floor"}
            buf = io.StringIO()
            with mock.patch.object(cli, "MSPCompositor") as comp:
                with mock.patch("sys.stdout", buf):
                    comp.composite_rendered_floor_asset.return_value = floor_result
                    cli.cmd_composite(args)
            self.assertTrue(comp.composite_rendered_floor_asset.called)
            self.assertFalse(comp.composite_asset.called)

    def test_validate_manifest_rejects_bad_new_fields(self):
        from msp_render_cli.manifest import validate_manifest
        base = {
            "job_id": "j", "package_model": "RL300_SAFE",
            "cad_source": {"file_path": "x.blend"},
            "camera": {"preset": "CUSTOM"},
            "livery": {"preset": "preserve_existing"},
            "lighting": {"preset": "studio_white"},
            "output": {"width": 100, "height": 80},
        }
        ok, _ = validate_manifest(base)
        self.assertTrue(ok)
        bad = json.loads(json.dumps(base))
        bad["output"]["film_transparent"] = "false"
        ok, err = validate_manifest(bad)
        self.assertFalse(ok)
        bad = json.loads(json.dumps(base))
        bad["lighting"]["floor"] = {"enabled": "yes"}
        ok, err = validate_manifest(bad)
        self.assertFalse(ok)


class NewJobManifestTests(unittest.TestCase):
    def test_studio_floor_job_is_valid_and_floor_shaped(self):
        from msp_render_cli.manifest import validate_manifest
        data = json.loads(
            (ROOT / "jobs/rl300_05_studio-floor.json").read_text(encoding="utf-8"))
        ok, err = validate_manifest(data)
        self.assertTrue(ok, err)
        self.assertEqual(validate_floor_config(data), [])
        self.assertTrue(floor_mode(data))
        self.assertIs(data["output"]["film_transparent"], False)
        self.assertEqual(data["camera"]["depth_of_field"]["f_stop"], 3.2)
        self.assertEqual(data["compositing"]["shadow_opacity"], 0.35)
        for raw in (data["lighting"].get("hdri_path"),
                    data["compositing"].get("background_plate")):
            if raw:
                self.assertTrue((ROOT / raw).is_file(), raw)


if __name__ == "__main__":
    unittest.main()

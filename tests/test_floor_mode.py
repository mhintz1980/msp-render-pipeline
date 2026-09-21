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
            steep = _FakeCamera(
                _FakeCamData([_V(-1, -1, -10), _V(1, -1, -10),
                              _V(-1, 1, -10), _V(1, 1, -10)]),
                _V(0, 0, 10))
            floor = worker.build_studio_floor(1.5, scene=_FakeScene(steep))
            self.assertEqual(floor.name, "MSP_StudioFloor")
            size = bpy.ops.mesh.primitive_plane_add.call_args_list[0].kwargs["size"]
            self.assertAlmostEqual(size, 1.5 * 14.0)
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
            steep = _FakeCamera(
                _FakeCamData([_V(-1, -1, -10), _V(1, -1, -10),
                              _V(-1, 1, -10), _V(1, 1, -10)]),
                _V(0, 0, 10))
            worker.build_studio_floor(1.5, scene=_FakeScene(steep))
        kwargs = bpy.ops.mesh.primitive_plane_add.call_args.kwargs
        self.assertEqual(kwargs["location"], (0.5, -0.25, -0.3))


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
    """Pure geometry: the plane must cover every frame-corner ground hit."""

    @staticmethod
    def _worker():
        import render_worker
        return render_worker

    def test_perspective_corners_bound_the_half_extent(self):
        worker = self._worker()
        # Camera at (0,0,10), corner rays through local (±1,±1,-1): each
        # hits z=0 at t=10, i.e. (±10,±10,0).
        rays = [((0.0, 0.0, 10.0), (sx, sy, -1.0))
                for sx in (-1.0, 1.0) for sy in (-1.0, 1.0)]
        half = worker.required_floor_half_extent(
            rays, (0.0, 0.0, 0.0), (0.0, 0.0, 10.0), (0.0, 0.0, -1.0))
        self.assertAlmostEqual(half, 10.0 * 1.05)
        # Plane centred off the hit cluster: Chebyshev distance from the
        # centre grows, not the raw hit magnitude.
        half = worker.required_floor_half_extent(
            rays, (2.0, -1.0, 0.0), (0.0, 0.0, 10.0), (0.0, 0.0, -1.0))
        self.assertAlmostEqual(half, 12.0 * 1.05)

    def test_direction_scale_leaves_extent_and_clipping_identical(self):
        """The ray parameter t is scale-bearing; extent and the clip gate
        must depend only on the hit point and its axial depth."""
        worker = self._worker()
        camera_origin = (0.0, 0.0, 10.0)
        forward = (0.0, 0.0, -1.0)
        base = (3.0, 2.0, -1.0)
        for scale in (0.1, 1.0, 10.0):
            rays = [(camera_origin,
                     (base[0] * scale, base[1] * scale, base[2] * scale))]
            half = worker.required_floor_half_extent(
                rays, (0.0, 0.0, 0.0), camera_origin, forward,
                clip_end=11.0)
            # Hit is fixed at (30, 20, 0); axial depth is 10 regardless of
            # the direction scale (t itself ranges 1..100).
            self.assertAlmostEqual(half, 30.0 * 1.05)
            with self.assertRaisesRegex(RuntimeError,
                                        "FLOOR_EDGE_BEYOND_CLIP_END"):
                worker.required_floor_half_extent(
                    rays, (0.0, 0.0, 0.0), camera_origin, forward,
                    clip_end=10.0)

    def test_horizon_in_frame_fails_loud(self):
        worker = self._worker()
        rays = [((0.0, 0.0, 10.0), (1.0, 1.0, -1.0)),
                ((0.0, 0.0, 10.0), (1.0, 1.0, 0.0))]  # top of frame at horizon
        with self.assertRaisesRegex(RuntimeError, "FLOOR_HORIZON_IN_FRAME"):
            worker.required_floor_half_extent(
                rays, (0.0, 0.0, 0.0), (0.0, 0.0, 10.0), (0.0, 0.0, -1.0))
        rays[1] = ((0.0, 0.0, 10.0), (1.0, 1.0, 0.25))  # pointing up
        with self.assertRaisesRegex(RuntimeError, "FLOOR_HORIZON_IN_FRAME"):
            worker.required_floor_half_extent(
                rays, (0.0, 0.0, 0.0), (0.0, 0.0, 10.0), (0.0, 0.0, -1.0))

    def test_hit_behind_camera_fails_loud(self):
        worker = self._worker()
        # Camera below the floor plane looking down: t = (0-(-5))/-1 < 0.
        rays = [((0.0, 0.0, -5.0), (0.0, 0.0, -1.0))]
        with self.assertRaisesRegex(RuntimeError, "FLOOR_BEHIND_CAMERA"):
            worker.required_floor_half_extent(
                rays, (0.0, 0.0, 0.0), (0.0, 0.0, -5.0), (0.0, 0.0, -1.0))

    def test_hit_beyond_clip_end_fails_loud(self):
        worker = self._worker()
        camera_origin = (0.0, 0.0, 10.0)
        forward = (0.0, 0.0, -1.0)
        rays = [(camera_origin, (1.0, 0.0, -1.0))]  # hit at axial depth 10
        with self.assertRaisesRegex(RuntimeError, "FLOOR_EDGE_BEYOND_CLIP_END"):
            worker.required_floor_half_extent(rays, (0.0, 0.0, 0.0),
                                              camera_origin, forward,
                                              clip_end=10.0)
        # Axial depth 10 is far inside clip_end 100; it only trips when the
        # clip is tightened below the true axial depth.
        self.assertGreater(
            worker.required_floor_half_extent(rays, (0.0, 0.0, 0.0),
                                              camera_origin, forward,
                                              clip_end=11.0), 0.0)
        with self.assertRaisesRegex(RuntimeError,
                                    "FLOOR_EDGE_BEYOND_CLIP_END"):
            worker.required_floor_half_extent(rays, (0.0, 0.0, 0.0),
                                              camera_origin, forward,
                                              clip_end=9.0)

    def test_dof_margin_adds_defocus_blur_radius(self):
        worker = self._worker()
        rays = [((0.0, 0.0, 10.0), (1.0, 1.0, -1.0))]
        camera_origin = (0.0, 0.0, 10.0)
        forward = (0.0, 0.0, -1.0)
        plain = worker.required_floor_half_extent(rays, (0.0, 0.0, 0.0),
                                                  camera_origin, forward)
        # 85 mm at f/3.2: aperture radius 13.28125 mm; hit at axial depth 10
        # with focus at 5 -> blur radius a*|10-5|/5 = a.
        aperture = (85.0 / (2.0 * 3.2)) / 1000.0
        with_dof = worker.required_floor_half_extent(
            rays, (0.0, 0.0, 0.0), camera_origin, forward,
            aperture_radius_m=aperture, focus_distance_m=5.0)
        self.assertAlmostEqual(with_dof - plain, aperture)

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

    def test_build_derives_size_from_actual_camera_and_keeps_legacy_minimum(self):
        worker = self._worker()
        bpy = mock.MagicMock()
        bpy.context.scene.objects = []
        cam = _FakeCamera(
            _FakeCamData([_V(-1, -1, -1), _V(1, -1, -1), _V(-1, 1, -1),
                          _V(1, 1, -1)], clip_end=200.0, use_dof=True,
                         aperture_fstop=3.2, focus_distance=5.0, lens=85.0),
            _V(0, 0, 10))
        with mock.patch.object(worker, "bpy", bpy):
            worker.build_studio_floor(0.5, scene=_FakeScene(cam))
        kwargs = bpy.ops.mesh.primitive_plane_add.call_args.kwargs
        # Corner hits at (±10,±10,0): half = 10*1.05 + DOF blur 0.01328125.
        expected = 2.0 * (10.0 * 1.05 + (85.0 / 6.4 / 1000.0))
        self.assertAlmostEqual(kwargs["size"], expected)
        self.assertEqual(kwargs["location"], (0.0, 0.0, 0.0))

        # A steep camera whose hits stay inside the legacy minimum keeps it.
        steep = _FakeCamera(
            _FakeCamData([_V(-1, -1, -10), _V(1, -1, -10), _V(-1, 1, -10),
                          _V(1, 1, -10)], clip_end=200.0),
            _V(0, 0, 10))
        with mock.patch.object(worker, "bpy", bpy):
            worker.build_studio_floor(0.5, scene=_FakeScene(steep))
        kwargs = bpy.ops.mesh.primitive_plane_add.call_args.kwargs
        self.assertAlmostEqual(kwargs["size"], 0.5 * 14.0)

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

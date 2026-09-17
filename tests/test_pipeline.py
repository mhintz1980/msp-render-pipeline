import unittest
import os
import tempfile
import numpy as np
from PIL import Image

import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from msp_render_cli.materials import hex_to_linear_rgb, LIVERY_PRESETS
from msp_render_cli.cameras import calculate_camera_transform, CAMERA_PRESETS
from msp_render_cli.manifest import create_default_manifest, validate_manifest
from composite_worker import MSPCompositor

class TestMSPRenderPipeline(unittest.TestCase):

    def test_materials_color_conversion(self):
        """Verify linear sRGB conversion for MSP Yellow and UR Blue."""
        yellow_linear = hex_to_linear_rgb(LIVERY_PRESETS["msp_standard_yellow"]["body_color_hex"])
        self.assertEqual(len(yellow_linear), 4)
        self.assertAlmostEqual(yellow_linear[3], 1.0)
        self.assertTrue(yellow_linear[0] > yellow_linear[2])  # Yellow has higher R than B

        blue_linear = hex_to_linear_rgb(LIVERY_PRESETS["united_rentals_blue"]["body_color_hex"])
        self.assertTrue(blue_linear[2] > blue_linear[0])  # Blue has higher B than R

    def test_camera_presets(self):
        """Verify all 8 camera presets generate valid 3D coordinates."""
        for name, preset in CAMERA_PRESETS.items():
            pos, rot = calculate_camera_transform(
                preset["azimuth_deg"],
                preset["elevation_deg"],
                distance=10.0,
                target_pos=(0, 0, 1.0)
            )
            self.assertEqual(len(pos), 3)
            self.assertEqual(len(rot), 3)
            self.assertFalse(any(np.isnan(pos)))
            self.assertFalse(any(np.isnan(rot)))

    def test_manifest_creation_and_validation(self):
        """Verify manifest generation and schema compliance."""
        manifest = create_default_manifest(
            job_id="test_rl300",
            package_model="RL300_SAFE",
            cad_path="V2RL300-SAFE.glb",
            camera_preset="P1_FRONT_ISO",
            livery_preset="msp_standard_yellow"
        )
        is_valid, err = validate_manifest(manifest)
        self.assertTrue(is_valid, f"Validation failed: {err}")

    def test_zero_loss_compositor(self):
        """Verify that product pixels inside the mask are 100% untouched by compositing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            w, h = 400, 300
            
            # Create synthetic background (e.g. grass/dirt pattern)
            bg_np = np.random.randint(50, 150, (h, w, 3), dtype=np.uint8)
            bg_img = Image.fromarray(bg_np, mode='RGB')
            bg_path = os.path.join(tmpdir, "bg.png")
            bg_img.save(bg_path)

            # Create synthetic product image (distinct pattern) with alpha mask
            prod_rgba = np.zeros((h, w, 4), dtype=np.uint8)
            # Machine body in center: (100:250, 100:300)
            prod_rgba[100:250, 100:300, 0] = 247  # Yellow
            prod_rgba[100:250, 100:300, 1] = 181
            prod_rgba[100:250, 100:300, 2] = 0
            prod_rgba[100:250, 100:300, 3] = 255 # Solid mask

            prod_img = Image.fromarray(prod_rgba, mode='RGBA')
            prod_path = os.path.join(tmpdir, "prod.png")
            prod_img.save(prod_path)

            out_path = os.path.join(tmpdir, "comp.png")

            # Run composite
            res = MSPCompositor.composite_asset(
                product_image_path=prod_path,
                background_image_path=bg_path,
                output_image_path=out_path,
                shadow_opacity=0.85,
                target_size=(w, h)
            )

            self.assertTrue(res["fidelity_gate_pass"])
            self.assertEqual(res["max_pixel_drift"], 0)
            self.assertEqual(res["dimensions"], (w, h))
            self.assertEqual(res["product_bbox"], (100, 100, 300, 250))

    def _synthetic_job(self, tmpdir, w=400, h=300, box=(100, 100, 300, 250)):
        """Writes a background plate and a product render, returns their paths."""
        bg_path = os.path.join(tmpdir, "bg.png")
        Image.fromarray(
            np.random.randint(50, 150, (h, w, 3), dtype=np.uint8)).save(bg_path)

        left, top, right, bottom = box
        prod = np.zeros((h, w, 4), dtype=np.uint8)
        prod[top:bottom, left:right] = (247, 181, 0, 255)
        prod_path = os.path.join(tmpdir, "prod.png")
        Image.fromarray(prod).save(prod_path)
        return prod_path, bg_path

    def test_shadow_follows_the_machine_not_the_canvas(self):
        """The contact shadow must sit under the silhouette, wherever it is."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # A machine parked high in the frame: its feet are at y=150 of 300,
            # nowhere near the 88%-of-canvas line the old code assumed.
            prod_path, bg_path = self._synthetic_job(tmpdir, box=(100, 40, 300, 150))
            mask = Image.open(prod_path).split()[3]
            shadow = np.array(MSPCompositor.create_contact_shadow(mask))

            darkest_row = int(np.argmax(shadow.sum(axis=1)))
            self.assertLess(abs(darkest_row - 150), 40,
                            f"Shadow centred on row {darkest_row}, expected near 150.")
            # Nothing should be cast down at the bottom of an empty canvas.
            self.assertLess(shadow[260:, :].mean(), 1.0)

    def test_placement_offset_and_scale_preserve_fidelity(self):
        """Repositioning and rescaling must not corrupt opaque machine pixels."""
        with tempfile.TemporaryDirectory() as tmpdir:
            prod_path, bg_path = self._synthetic_job(tmpdir)
            out_path = os.path.join(tmpdir, "comp.png")

            res = MSPCompositor.composite_asset(
                product_image_path=prod_path,
                background_image_path=bg_path,
                output_image_path=out_path,
                product_scale=0.8,
                product_offset_pct=(0.0, 0.1),
            )
            self.assertTrue(res["fidelity_gate_pass"], "Rescaled composite drifted.")
            self.assertEqual(res["max_pixel_drift"], 0)
            # 10% of 300px down, and 20% smaller.
            self.assertGreater(res["product_bbox"][1], 100)
            self.assertLess(res["product_bbox"][2] - res["product_bbox"][0], 200)

    def test_empty_render_is_reported_not_silently_composited(self):
        """A fully transparent render is a failed render, and must say so."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _, bg_path = self._synthetic_job(tmpdir)
            blank = os.path.join(tmpdir, "blank.png")
            Image.new("RGBA", (400, 300), (0, 0, 0, 0)).save(blank)
            with self.assertRaises(ValueError):
                MSPCompositor.composite_asset(
                    blank, bg_path, os.path.join(tmpdir, "out.png"))

    def test_locked_output_falls_back_instead_of_losing_the_render(self):
        """
        Re-running a job while the previous image is open in a viewer must not
        throw away a render that already cost GPU time.
        """
        import unittest.mock as mock
        with tempfile.TemporaryDirectory() as tmpdir:
            prod_path, bg_path = self._synthetic_job(tmpdir)
            out_path = os.path.join(tmpdir, "final.png")
            Image.new("RGB", (10, 10)).save(out_path)  # the "locked" file

            real_replace = os.replace
            calls = {"n": 0}

            def flaky_replace(src, dst):
                calls["n"] += 1
                if calls["n"] == 1:
                    raise OSError(22, "Invalid argument")
                return real_replace(src, dst)

            with mock.patch("composite_worker.os.replace", flaky_replace):
                res = MSPCompositor.composite_asset(prod_path, bg_path, out_path)

            self.assertNotEqual(res["output_path"], os.path.abspath(out_path))
            self.assertTrue(os.path.exists(res["output_path"]))
            self.assertTrue(res["fidelity_gate_pass"])
            leftovers = [f for f in os.listdir(tmpdir) if f.endswith(".tmp.png")]
            self.assertEqual(leftovers, [], "Temp file left behind.")

    def test_plate_is_fitted_to_the_render_not_the_reverse(self):
        """The hero render must never be resampled to match the plate."""
        with tempfile.TemporaryDirectory() as tmpdir:
            prod_path, _ = self._synthetic_job(tmpdir, w=800, h=600,
                                               box=(200, 200, 600, 500))
            odd_bg = os.path.join(tmpdir, "odd_bg.png")
            Image.fromarray(
                np.random.randint(50, 150, (211, 337, 3), dtype=np.uint8)).save(odd_bg)

            res = MSPCompositor.composite_asset(
                prod_path, odd_bg, os.path.join(tmpdir, "out.png"))
            self.assertEqual(res["dimensions"], (800, 600))
            self.assertTrue(res["fidelity_gate_pass"])

    def test_composite_cli_exits_nonzero_when_any_gate_fails(self):
        """cmd_composite must exit 1 on a failed gate, not just fidelity."""
        import argparse
        import io
        import json
        import unittest.mock as mock
        from msp_render_cli import cli

        with tempfile.TemporaryDirectory() as tmpdir:
            manifest = create_default_manifest(
                job_id="gate_fail", package_model="RL300_SAFE",
                cad_path="dummy.glb", camera_preset="P1_FRONT_ISO",
                livery_preset="msp_standard_yellow")
            manifest_path = os.path.join(tmpdir, "job.json")
            with open(manifest_path, "w", encoding="utf-8") as f:
                json.dump(manifest, f)

            prod_path = os.path.join(tmpdir, "prod.png")
            Image.new("RGBA", (20, 20), (255, 0, 0, 255)).save(prod_path)

            failed = {
                "output_path": os.path.join(tmpdir, "out.png"),
                "saved_image_path": os.path.join(tmpdir, "out.png"),
                "status": "failed",
                "fidelity_gate_pass": True,
                "mask_gate_pass": False,
                "saved_check_pass": True,
                "max_pixel_drift": 0,
                "mean_pixel_drift": 0.0,
                "dimensions": (20, 20),
                "product_bbox": (0, 0, 20, 20),
                "coverage_pct": 100.0,
            }
            args = argparse.Namespace(
                manifest=manifest_path, product=prod_path,
                background=os.path.join(tmpdir, "bg.png"),
                output=os.path.join(tmpdir, "out.png"), shadow_opacity=None)

            buf = io.StringIO()
            with mock.patch.object(cli, "MSPCompositor") as comp_cls, \
                    mock.patch("sys.stdout", buf):
                comp_cls.composite_asset.return_value = failed
                with self.assertRaises(SystemExit) as ctx:
                    cli.cmd_composite(args)

            self.assertEqual(ctx.exception.code, 1)
            self.assertIn("Mask Consistency Gate", buf.getvalue())
            self.assertIn("FAIL", buf.getvalue())


class TestDemoManifests(unittest.TestCase):
    """The three manifests the demo actually runs must stay valid and complete."""

    JOBS_DIR = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "jobs"))

    def test_every_demo_manifest_validates_and_its_assets_exist(self):
        import json
        manifests = sorted(f for f in os.listdir(self.JOBS_DIR) if f.endswith(".json"))
        self.assertTrue(manifests, "No job manifests found in jobs/.")

        root = os.path.dirname(self.JOBS_DIR)
        for name in manifests:
            with self.subTest(manifest=name):
                with open(os.path.join(self.JOBS_DIR, name), encoding="utf-8") as f:
                    data = json.load(f)
                ok, err = validate_manifest(data)
                self.assertTrue(ok, f"{name}: {err}")

                for label, raw in (("hdri_path", data["lighting"].get("hdri_path")),
                                   ("background_plate",
                                    data.get("compositing", {}).get("background_plate"))):
                    if not raw:
                        continue
                    path = raw if os.path.isabs(raw) else os.path.join(root, raw)
                    self.assertTrue(os.path.exists(path),
                                    f"{name}: {label} missing -> {raw}")


if __name__ == "__main__":
    unittest.main()

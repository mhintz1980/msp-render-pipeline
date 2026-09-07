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

if __name__ == "__main__":
    unittest.main()

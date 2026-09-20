"""The lens pass must be deterministic, no-op by default, and gated honestly."""
import os
import sys
import tempfile
import unittest

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from composite_worker import MSPCompositor


def flat(color, size=(240, 320)):
    return Image.fromarray(np.tile(np.array(color, dtype=np.uint8), (*size, 1)), "RGB")


class LensPassTests(unittest.TestCase):
    def test_all_zero_params_is_a_byte_exact_no_op(self):
        image = flat((128, 64, 32))
        out = MSPCompositor.apply_lens_pass(image, vignette=0, bloom=0, grain=0)
        self.assertTrue(np.array_equal(np.array(image), np.array(out)))

    def test_grain_is_fixed_per_frame_index_and_differs_across_frames(self):
        image = flat((100, 100, 100))
        a = np.array(MSPCompositor.apply_lens_pass(image, grain=2.0, frame_index=7))
        b = np.array(MSPCompositor.apply_lens_pass(image, grain=2.0, frame_index=7))
        c = np.array(MSPCompositor.apply_lens_pass(image, grain=2.0, frame_index=8))
        self.assertTrue(np.array_equal(a, b), "same frame must be identical forever")
        self.assertFalse(np.array_equal(a, c), "neighbouring frames must differ")

    def test_grain_is_monochrome_and_small(self):
        image = flat((100, 100, 100))
        grain = np.array(MSPCompositor.apply_lens_pass(image, grain=2.2)) .astype(int)
        deviation = grain - 100
        self.assertTrue(np.all(deviation[:, :, 0] == deviation[:, :, 2]),
                        "one noise field must ride all channels")
        self.assertLessEqual(np.abs(deviation).max(), 12)
        self.assertGreater(np.abs(deviation).mean(), 0.1)

    def test_vignette_darkens_corners_and_leaves_the_centre(self):
        image = flat((200, 200, 200))
        out = np.array(MSPCompositor.apply_lens_pass(image, vignette=1.0)).astype(int)
        centre = out[out.shape[0] // 2, out.shape[1] // 2]
        corner = out[2, 2]
        self.assertGreaterEqual(centre.min(), 199, "centre must not darken")
        self.assertLess(corner.min(), 190, "corner must darken")

    def test_bloom_glow_starts_at_a_highlight_not_at_mid_greys(self):
        pixels = np.full((240, 320, 3), 128, dtype=np.uint8)
        pixels[100:140, 150:170] = 255  # one specular hotspot
        out = np.array(MSPCompositor.apply_lens_pass(
            Image.fromarray(pixels, "RGB"), bloom=1.0)).astype(int)
        beside = out[120, 174]  # 4 px from the hotspot edge, inside the glow
        far = out[10, 10]
        self.assertGreater(beside.mean(), 129.5, "glow must spill around the hotspot")
        self.assertEqual(far.tolist(), [128, 128, 128],
                         "mid-grey far from highlights must not move")


class CompositeLensIntegrationTests(unittest.TestCase):
    W, H = 320, 240
    BOX = (100, 80, 220, 180)

    def fixtures(self, tmpdir):
        left, top, right, bottom = self.BOX
        prod = np.zeros((self.H, self.W, 4), dtype=np.uint8)
        prod[top:bottom, left:right] = (247, 181, 0, 255)
        prod_path = os.path.join(tmpdir, "prod.png")
        Image.fromarray(prod).save(prod_path)
        plate_path = os.path.join(tmpdir, "plate.png")
        Image.fromarray(np.full((self.H, self.W, 3), 240, dtype=np.uint8), "RGB").save(plate_path)
        return prod_path, plate_path

    def test_lens_runs_after_the_gates_and_reports_itself(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            prod, plate = self.fixtures(tmpdir)
            out = os.path.join(tmpdir, "final.png")
            result = MSPCompositor.composite_asset(
                prod, plate, out, shadow_opacity=0.0,
                lens_vignette=0.4, lens_bloom=0.2, lens_grain=2.0, frame_index=5)
            self.assertTrue(result["fidelity_gate_pass"],
                            "the gate must verify the composite the lens consumed")
            self.assertTrue(result["lens_applied"])
            self.assertEqual(result["lens"]["frame_index"], 5)
            self.assertTrue(os.path.isfile(result["output_path"]))

    def test_no_lens_params_leaves_the_gated_composite_as_the_deliverable(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            prod, plate = self.fixtures(tmpdir)
            plain = os.path.join(tmpdir, "plain.png")
            lensed = os.path.join(tmpdir, "lensed.png")
            r1 = MSPCompositor.composite_asset(prod, plate, plain, shadow_opacity=0.0)
            r2 = MSPCompositor.composite_asset(prod, plate, lensed, shadow_opacity=0.0,
                                               lens_grain=2.0)
            self.assertFalse(r1["lens_applied"])
            self.assertTrue(r2["lens_applied"])
            self.assertTrue(np.array_equal(np.array(Image.open(plain)),
                                           np.array(Image.open(r1["output_path"]))))
            self.assertFalse(np.array_equal(np.array(Image.open(plain)),
                                            np.array(Image.open(lensed))))


if __name__ == "__main__":
    unittest.main()

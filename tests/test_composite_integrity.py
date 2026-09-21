import unittest
import os
import sys
import tempfile
import unittest.mock as mock
import numpy as np
from PIL import Image

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from composite_worker import MATTE_COVERAGE_CEILING
from composite_worker import MSPCompositor


class TestCompositeIntegrityGates(unittest.TestCase):
    """
    The integrity gates must inspect the seated mask and the saved file
    instead of trusting them: an un-transformed mask or a degrading save
    both destroy machine pixels that already cost GPU time.
    """

    W, H = 400, 300
    BOX = (120, 100, 280, 220)  # solid opaque product block: (l, t, r, b)

    def _fixtures(self, tmpdir, mask_shift_px=0, antialiased=False,
                  edge_alpha=None, max_alpha=None):
        """Writes a product render, a silhouette mask (optionally shifted
        horizontally), and a background plate; returns their paths.

        antialiased ramps the block perimeter 0..255 and makes the mask file
        the matte itself; edge_alpha sets a uniform 1px soft ring around the
        opaque core; max_alpha caps every alpha so no fully opaque pixel
        remains.
        """
        left, top, right, bottom = self.BOX
        prod = np.zeros((self.H, self.W, 4), dtype=np.uint8)
        prod[top:bottom, left:right] = (247, 181, 0, 255)
        if antialiased:
            # 1px alpha-ramped edge: the perimeter grades 0..255 into the
            # opaque core, so partially covered pixels line every side.
            x_ramp = np.linspace(0, 255, right - left).round().astype(np.uint8)
            y_ramp = np.linspace(0, 255, bottom - top).round().astype(np.uint8)
            prod[top, left:right, 3] = x_ramp
            prod[bottom - 1, left:right, 3] = x_ramp
            prod[top:bottom, left, 3] = y_ramp
            prod[top:bottom, right - 1, 3] = y_ramp
        elif edge_alpha is not None:
            ring = np.zeros((self.H, self.W), dtype=bool)
            ring[top:bottom, left:right] = True
            ring[top + 1:bottom - 1, left + 1:right - 1] = False
            prod[:, :, 3][ring] = edge_alpha
        if max_alpha is not None:
            alpha = prod[:, :, 3].astype(np.uint16)
            prod[:, :, 3] = (alpha * max_alpha // 255).astype(np.uint8)
        prod_path = os.path.join(tmpdir, "prod.png")
        Image.fromarray(prod).save(prod_path)

        if antialiased or edge_alpha is not None:
            # The file mask is the matte itself, soft edge included.
            mask = prod[:, :, 3].copy()
        else:
            m_left = left + mask_shift_px
            mask = np.zeros((self.H, self.W), dtype=np.uint8)
            mask[top:bottom, m_left:m_left + (right - left)] = 255
            if max_alpha is not None:
                mask = (mask.astype(np.uint16) * max_alpha // 255).astype(np.uint8)
        mask_path = os.path.join(tmpdir, "mask.png")
        Image.fromarray(mask).save(mask_path)

        bg_path = os.path.join(tmpdir, "bg.png")
        Image.fromarray(
            np.random.randint(50, 150, (self.H, self.W, 3), dtype=np.uint8)).save(bg_path)
        return prod_path, mask_path, bg_path

    def test_offset_mask_rides_with_the_product(self):
        """An offset product seated through a file mask must land intact."""
        with tempfile.TemporaryDirectory() as tmpdir:
            prod_path, mask_path, bg_path = self._fixtures(tmpdir)
            out_path = os.path.join(tmpdir, "comp.png")

            res = MSPCompositor.composite_asset(
                prod_path, bg_path, out_path,
                mask_image_path=mask_path,
                product_offset_px=(18, 0),
                target_size=(self.W, self.H),
            )

            self.assertEqual(res["status"], "success")
            self.assertTrue(res["mask_gate_pass"])
            self.assertTrue(res["fidelity_gate_pass"])
            self.assertTrue(res["saved_check_pass"])
            self.assertEqual(res["saved_image_path"], res["output_path"])

            # The seated footprint carries the full offset - the trailing
            # strip is not dropped and the leading edge is not clipped.
            l, t, r, b = self.BOX
            self.assertEqual(res["product_bbox"], (l + 18, t, r + 18, b))

            # No plate-dependent band on the leading edge: every opaque
            # machine pixel in the output is byte-equal to the placed product.
            placed = MSPCompositor._place_product(
                Image.open(prod_path).convert("RGBA"),
                (self.W, self.H), 1.0, (18, 0))
            placed_np = np.array(placed)
            out_np = np.array(Image.open(res["output_path"]).convert("RGB"))
            opaque = placed_np[:, :, 3] == 255
            self.assertTrue(opaque.any(), "No opaque product pixels seated.")
            self.assertTrue(np.array_equal(
                placed_np[:, :, :3][opaque], out_np[opaque]),
                "Composite product pixels differ from the placed render.")

    def test_normal_matte_passes_plausibility_unchanged(self):
        """A product-sized matte sits far below the ceiling and leaves an
        otherwise passing composite passing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            prod_path, mask_path, bg_path = self._fixtures(tmpdir)
            out_path = os.path.join(tmpdir, "comp.png")

            res = MSPCompositor.composite_asset(
                prod_path, bg_path, out_path,
                mask_image_path=mask_path,
                target_size=(self.W, self.H),
            )

            mask = np.array(Image.open(mask_path)) == 255
            self.assertLess(float(mask.mean()), MATTE_COVERAGE_CEILING / 2.0)
            self.assertTrue(res["matte_plausibility_pass"])
            self.assertEqual(res["status"], "success")

    def test_full_frame_matte_fails_the_plausibility_gate(self):
        """A near-full-frame mask means the beauty alpha swallowed an opaque
        floor; the result fails loudly instead of passing meaninglessly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            prod_path, _, bg_path = self._fixtures(tmpdir)
            mask = np.full((self.H, self.W), 255, dtype=np.uint8)
            mask[0, 0] = 0
            mask_path = os.path.join(tmpdir, "mask_full.png")
            Image.fromarray(mask).save(mask_path)
            out_path = os.path.join(tmpdir, "comp.png")

            res = MSPCompositor.composite_asset(
                prod_path, bg_path, out_path,
                mask_image_path=mask_path,
                target_size=(self.W, self.H),
            )

            self.assertFalse(res["matte_plausibility_pass"])
            self.assertEqual(res["status"], "failed")
            self.assertTrue(os.path.exists(res["output_path"]),
                            "Failed gate must not discard the saved render.")

    def test_mismatched_mask_fails_the_gate_but_keeps_the_render(self):
        """A mask shifted off the product fails the gate; the file survives."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # 20px of 400 = 5% of width: a misregistration no legitimate
            # antialiased edge can explain (IoU collapses to ~0.78).
            prod_path, mask_path, bg_path = self._fixtures(tmpdir, mask_shift_px=20)
            out_path = os.path.join(tmpdir, "comp.png")

            res = MSPCompositor.composite_asset(
                prod_path, bg_path, out_path,
                mask_image_path=mask_path,
                product_offset_px=(18, 0),
                target_size=(self.W, self.H),
            )

            self.assertFalse(res["mask_gate_pass"])
            self.assertEqual(res["status"], "failed")
            self.assertTrue(os.path.exists(res["output_path"]),
                            "Failed gate must not discard the saved render.")

    def test_saved_image_gate_catches_a_corrupted_write(self):
        """The pixel gate must read back the file, not re-trust memory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            prod_path, mask_path, bg_path = self._fixtures(tmpdir)
            out_path = os.path.join(tmpdir, "comp.png")

            real_save = Image.Image.save

            def degrading_save(self, fp, format=None, **kwargs):
                # Simulate a save that silently degrades the bytes on disk:
                # every channel lifted, so the file no longer matches the
                # composite that was built in memory.
                degraded = Image.eval(self.convert("RGB"),
                                      lambda px: min(255, px + 40))
                real_save(degraded, fp, format or "PNG")

            with mock.patch.object(Image.Image, "save", degrading_save):
                res = MSPCompositor.composite_asset(
                    prod_path, bg_path, out_path,
                    mask_image_path=mask_path,
                    target_size=(self.W, self.H),
                )

            self.assertFalse(res["saved_check_pass"])
            self.assertFalse(res["fidelity_gate_pass"])
            self.assertEqual(res["status"], "failed")
            self.assertGreater(res["max_pixel_drift"], 0)

    def test_identity_placement_with_file_mask_matches_fallback_alpha(self):
        """Zero offset at scale 1.0 must be byte-identical with or without
        a mask file - accepted evidence digests depend on it."""
        with tempfile.TemporaryDirectory() as tmpdir:
            prod_path, mask_path, bg_path = self._fixtures(tmpdir)
            out_mask = os.path.join(tmpdir, "with_mask.png")
            out_alpha = os.path.join(tmpdir, "fallback.png")

            res_mask = MSPCompositor.composite_asset(
                prod_path, bg_path, out_mask, mask_image_path=mask_path,
                target_size=(self.W, self.H))
            res_alpha = MSPCompositor.composite_asset(
                prod_path, bg_path, out_alpha,
                target_size=(self.W, self.H))

            self.assertEqual(res_mask["status"], "success")
            self.assertEqual(res_alpha["status"], "success")
            with open(res_mask["output_path"], "rb") as f_mask, \
                    open(res_alpha["output_path"], "rb") as f_alpha:
                self.assertEqual(f_mask.read(), f_alpha.read(),
                                 "Identity placement changed pixels.")

    def test_antialiased_identity_is_byte_identical_with_and_without_mask(self):
        """A 1px alpha-ramped edge must survive identity placement unresampled:
        file bytes are identical whether the mask comes from a file or the
        fallback alpha, pinning the _place_product early return."""
        with tempfile.TemporaryDirectory() as tmpdir:
            prod_path, mask_path, bg_path = self._fixtures(tmpdir, antialiased=True)
            out_mask = os.path.join(tmpdir, "with_mask.png")
            out_alpha = os.path.join(tmpdir, "fallback.png")

            res_mask = MSPCompositor.composite_asset(
                prod_path, bg_path, out_mask, mask_image_path=mask_path,
                target_size=(self.W, self.H))
            res_alpha = MSPCompositor.composite_asset(
                prod_path, bg_path, out_alpha, target_size=(self.W, self.H))

            self.assertEqual(res_mask["status"], "success")
            self.assertEqual(res_alpha["status"], "success")
            self.assertTrue(res_mask["mask_gate_pass"])
            with open(res_mask["output_path"], "rb") as f_mask, \
                    open(res_alpha["output_path"], "rb") as f_alpha:
                self.assertEqual(f_mask.read(), f_alpha.read(),
                                 "Identity placement resampled the AA edge.")

    def test_binarized_matte_passes_the_mask_gate(self):
        """A caller's binarized matte (0/255 only) legitimately diverges from
        the placed alpha footprint at the >8 threshold (paste squares low
        values); the >=128 pairing must rescue it, at identity and offset."""
        with tempfile.TemporaryDirectory() as tmpdir:
            prod_path, matte_path, bg_path = self._fixtures(tmpdir, edge_alpha=110)
            matte = np.array(Image.open(matte_path))
            bin_path = os.path.join(tmpdir, "mask_bin.png")
            Image.fromarray(np.where(matte >= 128, 255, 0).astype(np.uint8)).save(bin_path)

            for offset in ((0, 0), (18, 0)):
                with self.subTest(offset=offset):
                    out_path = os.path.join(tmpdir, f"comp_{offset[0]}.png")
                    res = MSPCompositor.composite_asset(
                        prod_path, bg_path, out_path,
                        mask_image_path=bin_path,
                        product_offset_px=offset,
                        target_size=(self.W, self.H),
                    )
                    self.assertTrue(res["mask_gate_pass"])
                    self.assertEqual(res["status"], "success")

    def test_soft_matte_with_no_opaque_pixel_fails_the_fidelity_gate(self):
        """A matte peaking at 254 gives the fidelity gate nothing to measure:
        that is a failure, not a vacuous 100%-exact pass."""
        with tempfile.TemporaryDirectory() as tmpdir:
            prod_path, mask_path, bg_path = self._fixtures(tmpdir, max_alpha=254)
            out_path = os.path.join(tmpdir, "comp.png")

            res = MSPCompositor.composite_asset(
                prod_path, bg_path, out_path, target_size=(self.W, self.H))

            self.assertFalse(res["fidelity_gate_pass"])
            self.assertEqual(res["max_pixel_drift"], 0)
            self.assertEqual(res["mean_pixel_drift"], 0.0)
            self.assertEqual(res["status"], "failed")

    def test_no_mask_supplied_reports_na_not_a_pass(self):
        """Without a mask file the mask gate never runs: mask_gate_pass is
        None and must not be reported as a measured pass."""
        with tempfile.TemporaryDirectory() as tmpdir:
            prod_path, mask_path, bg_path = self._fixtures(tmpdir)
            out_path = os.path.join(tmpdir, "comp.png")

            res = MSPCompositor.composite_asset(
                prod_path, bg_path, out_path, target_size=(self.W, self.H))

            self.assertIsNone(res["mask_gate_pass"])
            self.assertEqual(res["status"], "success")


if __name__ == "__main__":
    unittest.main()

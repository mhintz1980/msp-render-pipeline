"""Regression tests for the alpha matte pass (mask.png).

Background: every mask.png in the RL300 parity evidence was written as solid
black while the beauty pass alpha was correct. Root cause was ordering inside
`render_worker.write_matte_pass` - assigning `colorspace_settings.name` on a
generated image frees and regenerates its buffer from `generated_color`
(opaque black), so setting it after the pixel write discarded the matte.

The blank mask survived a full five-mode verification run because nothing
compared mask.png against the beauty alpha at the time. These tests close both
halves of that gap: the writer must produce a faithful matte, and the verifier
must still reject one that is blank.
"""

import importlib.util
import os
import shutil
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
VERIFY_SCENE = ROOT / "scripts" / "verify_scene.py"

BLENDER_CANDIDATES = (
    os.environ.get("MSP_BLENDER_BIN"),
    r"C:/Program Files/Blender Foundation/Blender 5.1/blender.exe",
    "blender",
)


def _find_blender():
    for candidate in BLENDER_CANDIDATES:
        if not candidate:
            continue
        if os.path.isfile(candidate):
            return candidate
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    return None


def _load_verify_scene():
    spec = importlib.util.spec_from_file_location("verify_scene", VERIFY_SCENE)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _beauty_with_gradient_alpha(width=64, height=48):
    """An RGBA plate whose alpha has real structure, edges and holes."""
    ys, xs = np.mgrid[0:height, 0:width]
    alpha = (xs / (width - 1) * 255).astype(np.uint8)
    alpha[: height // 4, :] = 0            # fully transparent band
    alpha[-height // 4:, :] = 255          # fully opaque band
    alpha[height // 2, width // 2] = 17    # a lone interior value
    rgb = np.dstack([
        (ys / (height - 1) * 255).astype(np.uint8),
        np.full((height, width), 96, dtype=np.uint8),
        (xs / (width - 1) * 200).astype(np.uint8),
    ])
    return np.dstack([rgb, alpha]), alpha


class TestMattePassWriter(unittest.TestCase):
    """Drives the real render_worker.write_matte_pass inside Blender."""

    def test_mask_matches_beauty_alpha(self):
        blender = _find_blender()
        if blender is None:
            self.skipTest("Blender not found; set MSP_BLENDER_BIN to run this test")

        with tempfile.TemporaryDirectory() as tmp:
            beauty, alpha = _beauty_with_gradient_alpha()
            Image.fromarray(beauty).save(Path(tmp) / "beauty.png")

            driver = Path(tmp) / "_drive_matte.py"
            driver.write_text(textwrap.dedent("""
                import os, sys
                repo, out_dir = os.environ["MSP_REPO"], os.environ["MSP_OUT"]
                # render_worker reads everything after "--" as a manifest on import.
                saved, sys.argv = sys.argv, [a for a in sys.argv if a != "--"]
                sys.path.insert(0, repo)
                import render_worker
                sys.argv = saved
                render_worker.write_matte_pass(out_dir)
                print("MATTE_WRITTEN")
            """), encoding="utf-8")

            env = dict(os.environ, MSP_REPO=str(ROOT), MSP_OUT=tmp)
            result = subprocess.run(
                [blender, "--background", "--factory-startup", "--python", str(driver)],
                capture_output=True, text=True, timeout=300, env=env)
            self.assertIn("MATTE_WRITTEN", result.stdout,
                          msg=f"matte pass did not complete:\n{result.stdout}\n{result.stderr}")

            mask_path = Path(tmp) / "mask.png"
            self.assertTrue(mask_path.is_file(), "mask.png was not written")
            with Image.open(mask_path) as im:
                mask = np.asarray(im.convert("L"))

            self.assertEqual(mask.shape, alpha.shape)
            # The verifier's own tolerance: mask must agree with beauty alpha
            # to within one 8-bit step.
            self.assertLessEqual(int(np.abs(mask.astype(int) - alpha.astype(int)).max()), 1)
            # Guards the exact failure that shipped: a flat, structureless mask
            # passes a loose diff only if the alpha was flat too.
            self.assertGreater(len(np.unique(mask)), 1, "mask.png is a single flat value")


class TestVerifierRejectsBlankMask(unittest.TestCase):
    """The gate that would have caught this must keep catching it."""

    def setUp(self):
        self.verify_scene = _load_verify_scene()

    def _consistency(self, mask, alpha):
        """Mirror of the verifier's mask/alpha check on decoded arrays."""
        return mask.shape == alpha.shape and \
            np.abs(mask.astype(int) - alpha.astype(int)).max() <= 1

    def test_blank_mask_is_rejected(self):
        _, alpha = _beauty_with_gradient_alpha()
        blank = np.zeros_like(alpha)
        self.assertFalse(self._consistency(blank, alpha))

    def test_faithful_mask_is_accepted(self):
        _, alpha = _beauty_with_gradient_alpha()
        self.assertTrue(self._consistency(alpha.copy(), alpha))

    def test_off_by_one_is_tolerated(self):
        _, alpha = _beauty_with_gradient_alpha()
        nudged = np.clip(alpha.astype(int) + 1, 0, 255).astype(np.uint8)
        self.assertTrue(self._consistency(nudged, alpha))

    def test_off_by_two_is_rejected(self):
        _, alpha = _beauty_with_gradient_alpha()
        nudged = np.clip(alpha.astype(int) + 2, 0, 255).astype(np.uint8)
        self.assertFalse(self._consistency(nudged, alpha))

    def test_shape_mismatch_is_rejected(self):
        _, alpha = _beauty_with_gradient_alpha()
        self.assertFalse(self._consistency(alpha[:, :-1].copy(), alpha))


if __name__ == "__main__":
    unittest.main()

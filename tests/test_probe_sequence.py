"""The sequence gates must catch what a still pipeline cannot see."""
import importlib.util
import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("probe_sequence", ROOT / "scripts/probe_sequence.py")
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)

import numpy as np
from PIL import Image


def scalars(mean_luma):
    return {"coverage": 0.42, "mean_luma": mean_luma, "p95_luma": mean_luma + 40}


class SequenceReportTests(unittest.TestCase):
    def az(self, n, step=12.0):
        return [42 + step * i for i in range(n)]

    def test_a_smooth_sequence_passes_with_no_problems(self):
        report = probe.sequence_report(
            [scalars(100 + i * 0.5) for i in range(10)],
            [6.3, 6.4, 6.2, 6.3, 6.4, 6.2, 6.3, 6.4, 6.2],
            [f"d{i}" for i in range(10)], self.az(10))
        self.assertEqual(report["problems"], [])

    def test_a_flicker_outlier_frame_is_named(self):
        maes = [6.3, 6.4, 6.2, 25.0, 6.3, 6.4]
        report = probe.sequence_report(
            [scalars(100) for _ in maes], maes, [f"d{i}" for i in range(6)], self.az(6))
        self.assertIn("FLICKER_OUTLIER_FRAMES: [3]", report["problems"])

    def test_a_luminance_spike_fails_the_second_difference_gate(self):
        smooth = [scalars(100 + i * 0.5) for i in range(10)]
        smooth[5] = scalars(60)  # one frame goes dark
        report = probe.sequence_report(
            smooth, [6.3] * 9, [f"d{i}" for i in range(10)], self.az(10))
        self.assertGreater(
            report["max_abs_second_difference"]["mean_luma"], 10.0)

    def test_duplicate_and_gapped_sequences_are_rejected(self):
        report = probe.sequence_report(
            [scalars(100)] * 4, [6.3] * 3, ["d", "d", "d", "d"], self.az(4))
        self.assertTrue(any(p.startswith("DUPLICATE_CONSECUTIVE_FRAMES")
                            for p in report["problems"]))
        report = probe.sequence_report(
            [scalars(100)] * 4, [6.3] * 3, ["a", "b", "c", "d"],
            [42, 54, 90, 102])  # missing 66, 78
        self.assertTrue(any(p.startswith("NON_UNIFORM_AZIMUTH_STEPS")
                            for p in report["problems"]))


class ScalarTests(unittest.TestCase):
    def test_frame_scalars_and_mae_measure_only_product_pixels(self):
        mask = Image.new("L", (10, 10), 0)
        mask.putpixel((5, 5), 255)
        a = Image.new("RGB", (10, 10), (0, 0, 0))
        a.putpixel((5, 5), (100, 100, 100))
        b = Image.new("RGB", (10, 10), (200, 200, 200))  # plate moved, product fixed
        b.putpixel((5, 5), (104, 100, 100))
        s = probe.frame_scalars(a, mask)
        self.assertAlmostEqual(s["mean_luma"], 100.0)
        self.assertAlmostEqual(s["p95_luma"], 100.0)
        self.assertAlmostEqual(s["coverage"], 0.01)
        self.assertAlmostEqual(probe.frame_mae(a, b, mask, mask), 4.0 / 3.0)


if __name__ == "__main__":
    unittest.main()

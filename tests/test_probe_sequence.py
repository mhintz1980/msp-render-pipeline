"""The sequence gates must catch what a still pipeline cannot see."""
import importlib.util
import json
import shutil
import tempfile
import sys
import unittest.mock as mock
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


class EncodedFrameCountTests(unittest.TestCase):
    """encoded_frame_count must read the encoded file, with ffprobe stubbed."""

    def _patch_probe(self, replies):
        calls = []

        def fake_run(args, capture_output=False, text=False):
            calls.append(args)
            reply = replies[min(len(calls), len(replies)) - 1]
            return mock.Mock(returncode=0, stdout=reply, stderr="")

        return mock.patch.object(probe.subprocess, "run", fake_run), calls

    def test_normal_nb_frames_reply_parses_directly(self):
        patch, calls = self._patch_probe(["30\n"])
        with patch:
            self.assertEqual(probe.encoded_frame_count("x.mp4"), 30)
        self.assertEqual(len(calls), 1)

    def test_na_reply_falls_back_to_the_counting_probe(self):
        patch, calls = self._patch_probe(["N/A\n", "30\n"])
        with patch:
            self.assertEqual(probe.encoded_frame_count("x.mp4"), 30)
        self.assertEqual(len(calls), 2)
        self.assertIn("-count_frames", calls[1])

    def test_no_parseable_reply_raises(self):
        patch, _ = self._patch_probe(["N/A\n", "\n"])
        with patch, self.assertRaisesRegex(RuntimeError,
                                           "^FFPROBE_FRAME_COUNT_UNAVAILABLE:"):
            probe.encoded_frame_count("x.mp4")


class EncodeGateTests(unittest.TestCase):
    """main() must gate the encoded file's frame count against the unique
    source frames; ffmpeg/ffprobe are stubbed so no encoder is required."""

    FRAME_COUNT = 1

    def _run_main(self, ffprobe_count, argv_extra=(), extra_patches=None):
        extra_patches = extra_patches or {}
        def fake_run(args, capture_output=False, text=False, check=False):
            if args[0] == "ffmpeg" and "libx264" in args:
                Path(args[-1]).write_bytes(b"stub")
            elif args[0] == "ffmpeg":
                # The decode-back probe re-serves the source frame bytes, so
                # PSNR stays infinite and only the frame-count gate is tested.
                index = Path(args[-1]).stem.split("f")[-1]
                shutil.copyfile(Path(args[-1]).parent / "lens-frames" / f"f{index}.png",
                                args[-1])
            return mock.Mock(returncode=0, stdout=ffprobe_count, stderr="")

        with tempfile.TemporaryDirectory() as temp:
            run_dir = Path(temp)
            (run_dir / "cloud" / "frame-az42").mkdir(parents=True)
            frame = np.zeros((24, 32, 4), dtype=np.uint8)
            frame[6:18, 8:24] = (200, 100, 50, 255)
            Image.fromarray(frame).save(run_dir / "cloud/frame-az42/beauty.png")
            Image.fromarray(frame[:, :, 3]).save(run_dir / "cloud/frame-az42/mask.png")
            (run_dir / "request.json").write_text(json.dumps(
                {"job_id": "rl300_04_studio-white", "overrides": []}), encoding="utf-8")
            encode_args = []

            def recording_run(args, **kwargs):
                if args[0] == "ffmpeg" and "libx264" in args:
                    encode_args.append(list(args))
                return fake_run(args, **kwargs)

            with mock.patch.object(probe.subprocess, "run", recording_run), \
                    mock.patch.object(sys, "argv",
                                      ["probe_sequence.py", "--run-dir", str(run_dir),
                                       *argv_extra]):
                if extra_patches:
                    with mock.patch.multiple(probe, create=True, **extra_patches):
                        exit_code = probe.main()
                else:
                    exit_code = probe.main()
            report = json.loads((run_dir / "sequence-report.json").read_text())
        return exit_code, report, encode_args

    def test_encoded_count_mismatch_lands_in_problems(self):
        exit_code, report, _ = self._run_main("150\n")
        self.assertEqual(report["encoded_frame_count"], 150)
        self.assertEqual(report["unique_frame_count"], self.FRAME_COUNT)
        self.assertIn(
            f"ENCODED_FRAME_COUNT_MISMATCH: encoded 150 vs unique {self.FRAME_COUNT}",
            report["problems"])
        self.assertEqual(report["status"], "failed")
        self.assertEqual(exit_code, 1)

    def test_matching_encoded_count_stays_clean(self):
        exit_code, report, _ = self._run_main(f"{self.FRAME_COUNT}\n")
        self.assertNotIn("ENCODED_FRAME_COUNT_MISMATCH", report["problems"])
        self.assertEqual(report["encoded_frame_count"], report["unique_frame_count"])
        self.assertEqual(exit_code, 0)

    def test_encode_is_one_pass_with_no_stream_loop(self):
        _, _, encode_args = self._run_main("3\n")
        self.assertEqual(len(encode_args), 1)
        self.assertNotIn("-stream_loop", encode_args[0])

    def test_unavailable_encoded_count_fails_without_discarding_the_report(self):
        # The encode is billable and already on disk: a missing ffprobe must
        # land in problems and keep every other measured gate in the report.
        def explode(video_path):
            raise RuntimeError(f"FFPROBE_FRAME_COUNT_UNAVAILABLE: {video_path}")

        exit_code, report, _ = self._run_main(
            None, extra_patches={"encoded_frame_count": explode})
        self.assertTrue(any(p.startswith("ENCODED_FRAME_COUNT_UNAVAILABLE:")
                            for p in report["problems"]))
        self.assertIsNone(report["encoded_frame_count"])
        self.assertEqual(report["status"], "failed")
        self.assertEqual(exit_code, 1)
        self.assertIn("unique_frame_count", report)
        self.assertIn("frame_mae_median", report)

    def test_a_shorter_than_declared_run_is_reported(self):
        _, report, _ = self._run_main(f"{self.FRAME_COUNT}\n",
                                      argv_extra=("--expect-frames", "5"))
        self.assertIn(
            f"FRAME_COUNT_NOT_AS_DECLARED: found {self.FRAME_COUNT} expected 5",
            report["problems"])
        self.assertEqual(report["status"], "failed")


class FrameAzimuthTests(unittest.TestCase):
    def test_the_manifests_true_value_wins_over_the_label(self):
        with tempfile.TemporaryDirectory() as temp:
            run_dir = Path(temp)
            (run_dir / "manifest-az102.json").write_text(json.dumps(
                {"camera": {"azimuth_deg": 102.0}}), encoding="utf-8")
            frame_dir = run_dir / "cloud" / "frame-az102"
            frame_dir.mkdir(parents=True)
            self.assertEqual(probe.frame_azimuth(run_dir, frame_dir), 102.0)

    def test_a_missing_manifest_falls_back_to_the_label(self):
        with tempfile.TemporaryDirectory() as temp:
            run_dir = Path(temp)
            frame_dir = run_dir / "cloud" / "frame-az42"
            frame_dir.mkdir(parents=True)
            self.assertEqual(probe.frame_azimuth(run_dir, frame_dir), 42.0)

    def test_a_present_but_contractless_manifest_is_a_fault(self):
        with tempfile.TemporaryDirectory() as temp:
            run_dir = Path(temp)
            path = run_dir / "manifest-az42.json"
            path.write_text(json.dumps({"camera": {}}), encoding="utf-8")
            frame_dir = run_dir / "cloud" / "frame-az42"
            with self.assertRaisesRegex(RuntimeError, "^FRAME_AZIMUTH_UNAVAILABLE:"):
                probe.frame_azimuth(run_dir, frame_dir)


class OrbitAzimuthGateTests(unittest.TestCase):
    def test_a_300_frame_orbit_passes_on_true_azimuths_fails_on_labels(self):
        import importlib.util as _ilu
        spec = _ilu.spec_from_file_location("cloud_job_render_probe",
                                            ROOT / "scripts/cloud_job_render.py")
        cloud = _ilu.module_from_spec(spec)
        spec.loader.exec_module(cloud)
        true_azimuths = cloud.orbit_azimuths(300)
        labels = [int(round(a)) for a in true_azimuths]
        clean = probe.sequence_report(
            [scalars(100.0 + i * 0.01) for i in range(300)],
            [6.3] * 299, [f"d{i}" for i in range(300)], true_azimuths)
        self.assertFalse(any(p.startswith("NON_UNIFORM_AZIMUTH_STEPS")
                             for p in clean["problems"]))
        lossy = probe.sequence_report(
            [scalars(100.0 + i * 0.01) for i in range(300)],
            [6.3] * 299, [f"d{i}" for i in range(300)], labels)
        self.assertTrue(any(p.startswith("NON_UNIFORM_AZIMUTH_STEPS")
                            for p in lossy["problems"]))


if __name__ == "__main__":
    unittest.main()

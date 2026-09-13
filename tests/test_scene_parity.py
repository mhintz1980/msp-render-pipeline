"""Contract tests for scene image and structure parity comparisons."""

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
VERIFY_SCENE = ROOT / "scripts" / "verify_scene.py"


def _load_verify_scene():
    spec = importlib.util.spec_from_file_location("verify_scene", VERIFY_SCENE)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


verify_scene = _load_verify_scene()


class TestImageMetrics(unittest.TestCase):
    def write_image(self, folder, name, image):
        path = Path(folder) / name
        Image.fromarray(image).save(path, format="PNG")
        return path

    def opaque_square(self, color=(96, 144, 192, 255), size=32, left=8, top=8, width=16):
        image = np.zeros((size, size, 4), dtype=np.uint8)
        image[top : top + width, left : left + width] = color
        return image

    def compare(self, reference, candidate, reference_mask=None, candidate_mask=None):
        with tempfile.TemporaryDirectory(prefix="scene-parity-images-") as folder:
            return verify_scene.image_metrics(
                self.write_image(folder, "reference.png", reference),
                self.write_image(folder, "candidate.png", candidate),
                reference_mask=self.write_image(folder, "reference-mask.png",
                    reference[..., 3] if reference_mask is None else reference_mask),
                candidate_mask=self.write_image(folder, "candidate-mask.png",
                    candidate[..., 3] if candidate_mask is None else candidate_mask),
            )

    def test_identical_meaningful_opaque_object_passes(self):
        image = self.opaque_square()

        metrics = self.compare(image, image.copy())

        self.assertTrue(metrics["passed"], metrics)
        self.assertEqual(metrics["failures"], [])
        self.assertEqual(metrics["mask_iou"], 1.0)
        self.assertEqual(metrics["coverage_delta"], 0.0)
        self.assertEqual(metrics["linear_rgb_mae"], 0.0)
        self.assertEqual(metrics["linear_rgb_p99"], 0.0)
        self.assertGreater(metrics["interior_pixels"], 0)

    def test_transparent_images_fail_product_and_interior_gates(self):
        image = np.zeros((32, 32, 4), dtype=np.uint8)

        metrics = self.compare(image, image.copy())

        self.assertFalse(metrics["passed"])
        self.assertIn("EMPTY_PRODUCT", metrics["failures"])
        self.assertIn("NO_OPAQUE_PIXELS", metrics["failures"])
        self.assertIn("EMPTY_INTERIOR", metrics["failures"])

    def test_nonopaque_object_fails_opaque_and_interior_gates(self):
        image = self.opaque_square(color=(96, 144, 192, 128))

        metrics = self.compare(image, image.copy())

        self.assertFalse(metrics["passed"])
        self.assertIn("NO_OPAQUE_PIXELS", metrics["failures"])
        self.assertIn("EMPTY_INTERIOR", metrics["failures"])

    def test_alpha_threshold_counts_values_above_eight_in_the_mask(self):
        reference = self.opaque_square(color=(96, 144, 192, 9))
        candidate = self.opaque_square(color=(96, 144, 192, 8))

        metrics = self.compare(reference, candidate)

        self.assertGreater(metrics["reference_coverage"], 0.0)
        self.assertEqual(metrics["candidate_coverage"], 0.0)
        self.assertIn("SILHOUETTE_MISMATCH", metrics["failures"])

    def test_tiny_opaque_object_fails_minimum_occupancy(self):
        image = self.opaque_square(width=1)

        metrics = self.compare(image, image.copy())

        self.assertFalse(metrics["passed"])
        self.assertIn("EMPTY_PRODUCT", metrics["failures"])

    def test_silhouette_shift_fails_without_a_material_change(self):
        reference = self.opaque_square()
        candidate = self.opaque_square(left=9)

        metrics = self.compare(reference, candidate)

        self.assertFalse(metrics["passed"])
        self.assertIn("SILHOUETTE_MISMATCH", metrics["failures"])
        self.assertNotIn("RGB_MISMATCH", metrics["failures"])

    def test_material_rgb_change_fails_inside_matching_silhouette(self):
        reference = self.opaque_square(color=(255, 0, 0, 255))
        candidate = self.opaque_square(color=(0, 0, 255, 255))

        metrics = self.compare(reference, candidate)

        self.assertFalse(metrics["passed"])
        self.assertGreaterEqual(metrics["mask_iou"], 0.995)
        self.assertNotIn("SILHOUETTE_MISMATCH", metrics["failures"])
        self.assertIn("RGB_MISMATCH", metrics["failures"])

    def test_dimension_mismatch_fails_before_comparison(self):
        reference = self.opaque_square(size=32)
        candidate = self.opaque_square(size=31)

        metrics = self.compare(reference, candidate)

        self.assertFalse(metrics["passed"])
        self.assertIn("DIMENSIONS_MISMATCH", metrics["failures"])

    def test_saved_mask_controls_coverage_within_alpha_tolerance(self):
        image = self.opaque_square()
        image[0:4, :, 3] = 8
        reference_mask = image[..., 3].copy()
        candidate_mask = reference_mask.copy()
        candidate_mask[0:4, :] = 9

        metrics = self.compare(image, image, reference_mask, candidate_mask)

        self.assertIn("SILHOUETTE_MISMATCH", metrics["failures"])
        self.assertEqual(metrics["coverage_delta"], 0.125)
        self.assertEqual(metrics["linear_rgb_mae"], 0.0)

    def test_blank_saved_mask_cannot_pass_identical_beauties(self):
        image = self.opaque_square()
        metrics = self.compare(image, image, candidate_mask=np.zeros((32, 32), dtype=np.uint8))
        self.assertFalse(metrics["passed"])
        self.assertIn("MASK_ALPHA_MISMATCH", metrics["failures"])

    def test_soft_shadow_changes_coverage_but_not_product_rgb(self):
        reference = self.opaque_square()
        candidate = reference.copy()
        candidate[25:29, 4:28] = (0, 0, 0, 96)

        metrics = self.compare(reference, candidate)

        self.assertIn("SILHOUETTE_MISMATCH", metrics["failures"])
        self.assertEqual(metrics["linear_rgb_mae"], 0.0)
        self.assertEqual(metrics["interior_pixels"], 14 * 14)


class TestStructureDifferences(unittest.TestCase):
    def test_equal_nested_structure_accepts_finite_float_tolerance(self):
        reference = {
            "camera": {"lens": 50.0, "clip": [0.01, 1000.0]},
            "objects": [{"name": "Cube", "bounds": [[-1.0, 1.0]]}],
            "frame": 1,
        }
        candidate = {
            "camera": {"lens": 50.000009, "clip": [0.01, 1000.000009]},
            "objects": [{"name": "Cube", "bounds": [[-1.0, 1.0]]}],
            "frame": 1,
        }

        self.assertEqual(verify_scene.structure_differences(reference, candidate), [])

    def test_nonfinite_float_is_a_structural_difference(self):
        differences = verify_scene.structure_differences(
            {"exposure": float("nan")}, {"exposure": float("nan")}
        )

        self.assertEqual(differences, ["root.exposure: value differs"])

    def test_key_change_is_a_structural_difference(self):
        differences = verify_scene.structure_differences(
            {"camera": {"lens": 50.0}}, {"camera": {"focal_length": 50.0}}
        )

        self.assertEqual(differences, ["root.camera: keys differ"])

    def test_list_length_change_is_a_structural_difference(self):
        differences = verify_scene.structure_differences(
            {"objects": ["Cube"]}, {"objects": ["Cube", "Light"]}
        )

        self.assertEqual(differences, ["root.objects: length differs"])


class TestVerifierJob(unittest.TestCase):
    def test_default_job_is_preserved(self):
        parser = verify_scene.build_parser()
        args = parser.parse_args([
            "--preparation-report", "preparation-report.json",
            "--linux-runtime", "/opt/blender",
            "--output-dir", "evidence",
        ])

        self.assertEqual(args.job, str(verify_scene.DEFAULT_JOB))
        manifest, _, _, _ = verify_scene.load_verification_job(args.job)
        self.assertEqual(manifest["job_id"], "rl300_02_studio-dark")

    def test_selected_job_reaches_payload(self):
        source = ROOT / "cad" / "RL300-SAFE-photoreal.blend"
        selected_job = ROOT / "jobs" / "rl300_04_studio-white.json"
        with tempfile.TemporaryDirectory(prefix="scene-verifier-job-") as folder:
            output = Path(folder) / "evidence"
            output.mkdir()
            prepared = Path(folder) / "prepared.blend"
            prepared.write_bytes(b"prepared fixture")

            manifest, _ = verify_scene.stage_job_payload(output, prepared, source, selected_job)

            payload_manifest = json.loads((output / "payload" / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["job_id"], "rl300_04_studio-white")
            self.assertEqual(payload_manifest["job_id"], "rl300_04_studio-white")
            self.assertEqual(payload_manifest["lighting"]["hdri_path"], "/input/environment_light.png")
            self.assertEqual(payload_manifest["compositing"]["background_plate"], "/input/environment.png")
            self.assertEqual(
                (output / "payload" / "environment.png").read_bytes(),
                (ROOT / "backgrounds" / "env_studio-white.png").read_bytes(),
            )

    def test_missing_job_path_is_reported_clearly(self):
        with self.assertRaisesRegex(ValueError, "Job manifest does not exist"):
            verify_scene.load_verification_job("jobs/does-not-exist.json")

    def test_job_source_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix="scene-verifier-source-") as folder:
            output = Path(folder) / "evidence"
            output.mkdir()
            prepared = Path(folder) / "prepared.blend"
            prepared.write_bytes(b"prepared fixture")

            with self.assertRaisesRegex(ValueError, "does not match the preparation source"):
                verify_scene.stage_job_payload(
                    output, prepared, ROOT / "cad" / "different.blend", verify_scene.DEFAULT_JOB
                )

    def test_shared_image_stages_one_payload_file(self):
        """The dark anchor lights and backs itself with one file; its payload must not grow."""
        source = ROOT / "cad" / "RL300-SAFE-photoreal.blend"
        with tempfile.TemporaryDirectory(prefix="scene-verifier-shared-") as folder:
            output = Path(folder) / "evidence"
            output.mkdir()
            prepared = Path(folder) / "prepared.blend"
            prepared.write_bytes(b"prepared fixture")

            verify_scene.stage_job_payload(output, prepared, source, verify_scene.DEFAULT_JOB)

            payload = output / "payload"
            self.assertFalse((payload / "environment_light.png").exists())
            staged = json.loads((payload / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(staged["lighting"]["hdri_path"], "/input/environment.png")
            self.assertEqual(staged["compositing"]["background_plate"], "/input/environment.png")

    def test_separate_lighting_and_backdrop_are_both_staged(self):
        """A job may light with one image and show another; both must reach the probe."""
        source = ROOT / "cad" / "RL300-SAFE-photoreal.blend"
        job = ROOT / "jobs" / "rl300_04_studio-white.json"
        manifest = json.loads(job.read_text(encoding="utf-8"))
        self.assertNotEqual(manifest["lighting"]["hdri_path"],
                            manifest["compositing"]["background_plate"])

        with tempfile.TemporaryDirectory(prefix="scene-verifier-split-") as folder:
            output = Path(folder) / "evidence"
            output.mkdir()
            prepared = Path(folder) / "prepared.blend"
            prepared.write_bytes(b"prepared fixture")

            _, inputs = verify_scene.stage_job_payload(output, prepared, source, job)

            payload = output / "payload"
            staged = json.loads((payload / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(staged["lighting"]["hdri_path"], "/input/environment_light.png")
            self.assertEqual(staged["compositing"]["background_plate"], "/input/environment.png")
            self.assertEqual((payload / "environment.png").read_bytes(),
                             (ROOT / manifest["compositing"]["background_plate"]).read_bytes())
            self.assertEqual((payload / "environment_light.png").read_bytes(),
                             (ROOT / manifest["lighting"]["hdri_path"]).read_bytes())
            # Both images are hashed, so neither can be swapped inside the probe.
            self.assertIn("environment.png", inputs)
            self.assertIn("environment_light.png", inputs)
            self.assertNotEqual(inputs["environment.png"], inputs["environment_light.png"])


class TestPixelDigest(unittest.TestCase):
    """A cross-device comparison must measure the render, not the render clock."""

    def _write(self, path, pixels, **text):
        from PIL import PngImagePlugin

        info = PngImagePlugin.PngInfo()
        for key, value in text.items():
            info.add_text(key, value)
        Image.fromarray(pixels).save(path, pnginfo=info)

    def test_render_metadata_changes_the_file_hash_but_not_the_pixel_hash(self):
        pixels = np.random.default_rng(0).integers(0, 256, (11, 13, 4), dtype=np.uint8)
        with tempfile.TemporaryDirectory(prefix="scene-pixel-digest-") as folder:
            first = Path(folder) / "first.png"
            second = Path(folder) / "second.png"
            self._write(first, pixels, Date="2026/09/11 18:11:31", RenderTime="00:26.75")
            self._write(second, pixels, Date="2026/09/12 05:07:53", RenderTime="00:22.88")

            self.assertNotEqual(verify_scene.digest(first), verify_scene.digest(second))
            self.assertEqual(verify_scene.pixel_digest(first), verify_scene.pixel_digest(second))

    def test_a_single_changed_pixel_changes_the_pixel_hash(self):
        pixels = np.zeros((6, 7, 4), dtype=np.uint8)
        with tempfile.TemporaryDirectory(prefix="scene-pixel-digest-") as folder:
            first = Path(folder) / "first.png"
            second = Path(folder) / "second.png"
            self._write(first, pixels)
            pixels[3, 4, 1] = 1
            self._write(second, pixels)

            self.assertNotEqual(verify_scene.pixel_digest(first), verify_scene.pixel_digest(second))

    def test_unreadable_image_yields_no_digest_instead_of_raising(self):
        with tempfile.TemporaryDirectory(prefix="scene-pixel-digest-") as folder:
            broken = Path(folder) / "broken.png"
            broken.write_bytes(b"not a png")

            self.assertIsNone(verify_scene.pixel_digest(broken))
            self.assertIsNone(verify_scene.pixel_digest(Path(folder) / "absent.png"))


if __name__ == "__main__":
    unittest.main()

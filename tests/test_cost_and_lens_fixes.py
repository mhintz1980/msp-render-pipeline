"""Regressions from the batch3b review: request costs and lens forwarding.

Covers the estimate undercount (per-frame render seconds must be repeated once
per frame), lens forwarding into the floor composite route (dispatcher and
CLI, exactly once when configured), the probe's deliberately pre-lens floor
composite, and parity between the shared and worker floor validators.
"""
import importlib.util
import json
from types import SimpleNamespace
import tempfile
import unittest
import unittest.mock as mock
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cloud = _load("cloud_job_render", "scripts/cloud_job_render.py")
probe = _load("probe_sequence", "scripts/probe_sequence.py")


def _fixture(root, floor):
    """A minimal jobs/-shaped tree, floor mode when requested."""
    (root / "jobs").mkdir()
    (root / "cad").mkdir()
    (root / "backgrounds").mkdir()
    (root / "cad/machine.blend").write_bytes(b"blend")
    (root / "backgrounds/env_softbox.png").write_bytes(b"env")
    (root / "backgrounds/env_white.png").write_bytes(b"plate")
    lighting = {"hdri_path": "backgrounds/env_softbox.png"}
    output = {"output_dir": "./output/fixture"}
    if floor:
        lighting["floor"] = {"enabled": True}
        output["film_transparent"] = False
    manifest = {
        "job_id": "fixture_job",
        "cad_source": {"file_path": "cad/machine.blend"},
        "camera": {"azimuth_deg": 42.0},
        "lighting": lighting,
        "compositing": {"enabled": True},
        "output": output,
    }
    manifest_path = root / "jobs/fixture_job.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return manifest_path


class RequestCostTests(unittest.TestCase):
    """The request on disk must price every frame, non-floor and floor."""

    def _preflight_request(self, root, floor, count):
        manifest_path = _fixture(root, floor)
        out = root / "out"
        azimuth_args = (["--orbit", str(count)] if count >= 2
                        else ["--azimuths", "42"])
        argv = (["cloud_job_render.py", "--manifest", str(manifest_path)]
                + azimuth_args + ["--output-dir", str(out)])
        with mock.patch.object(sys, "argv", argv):
            cloud.main()
        return json.loads((out / "request.json").read_text(encoding="utf-8"))

    def test_request_cost_scales_with_frame_count(self):
        per_second = (cloud.GPU_RATE_PER_S + 4 * cloud.CPU_RATE_PER_CORE_S
                      + 16 * cloud.MEMORY_RATE_PER_GIB_S)
        for floor in (False, True):
            for count in (1, 2, 30):
                with self.subTest(floor=floor, count=count):
                    with tempfile.TemporaryDirectory() as temp:
                        request = self._preflight_request(Path(temp), floor, count)
                    per_frame = cloud.frame_render_seconds(floor_mode=floor)
                    self.assertEqual(request["render_passes_per_frame"],
                                     2 if floor else 1)
                    self.assertEqual(request["cost_estimate_usd"],
                                     round((cloud.COLD_START_SECONDS
                                            + count * per_frame) * per_second, 4))


class FakeFloorCompositor:
    """Records the floor composite kwargs; never touches images."""

    calls = []

    @classmethod
    def composite_rendered_floor_asset(cls, *args, **kwargs):
        cls.calls.append(kwargs)
        return {"status": "success", "mode": "rendered_floor",
                "output_path": str(args[3])}


class DispatcherLensForwardingTests(unittest.TestCase):
    def test_floor_route_forwards_configured_lens_exactly_once(self):
        import composite_worker
        FakeFloorCompositor.calls = []
        with tempfile.TemporaryDirectory() as temp:
            frame_dir = Path(temp)
            compositing = {"enabled": True, "shadow_opacity": 0.5,
                           "lens_vignette": 0.45, "lens_bloom": 0.3,
                           "lens_grain": 2.2}
            with mock.patch.object(composite_worker, "MSPCompositor",
                                   FakeFloorCompositor):
                cloud.run_composite(frame_dir, None, compositing,
                                    floor_mode=True)
        self.assertEqual(len(FakeFloorCompositor.calls), 1)
        kwargs = FakeFloorCompositor.calls[0]
        self.assertEqual(kwargs["shadow_opacity"], 0.5)
        self.assertEqual(kwargs["lens_vignette"], 0.45)
        self.assertEqual(kwargs["lens_bloom"], 0.3)
        self.assertEqual(kwargs["lens_grain"], 2.2)

    def test_floor_route_sends_no_lens_kwargs_when_unconfigured(self):
        import composite_worker
        FakeFloorCompositor.calls = []
        with tempfile.TemporaryDirectory() as temp:
            with mock.patch.object(composite_worker, "MSPCompositor",
                                   FakeFloorCompositor):
                cloud.run_composite(Path(temp), None, {"enabled": True},
                                    floor_mode=True)
        kwargs = FakeFloorCompositor.calls[0]
        for key in ("lens_vignette", "lens_bloom", "lens_grain"):
            self.assertNotIn(key, kwargs)


class CliLensForwardingTests(unittest.TestCase):
    def test_cli_floor_composite_forwards_configured_lens(self):
        import msp_render_cli.cli as cli
        manifest = {"job_id": "j",
                    "compositing": {"enabled": True, "shadow_opacity": 0.6,
                                    "lens_vignette": 0.45, "lens_bloom": 0.3,
                                    "lens_grain": 2.2},
                    "lighting": {"floor": {"enabled": True}},
                    "output": {"film_transparent": False}}
        calls = []

        class CliFake:
            @classmethod
            def composite_rendered_floor_asset(cls, *args, **kwargs):
                calls.append(kwargs)
                return {"mode": "rendered_floor", "output_path": "o.png",
                        "dimensions": [10, 10], "fidelity_gate_pass": True,
                        "mask_gate_pass": None, "saved_check_pass": True,
                        "max_pixel_drift": 0,
                        "coverage_pct": 100.0, "status": "success",
                        "configured_shadow_opacity": None,
                        "effective_shadow_opacity": 0.0}
        args = SimpleNamespace(manifest="m.json", background=None, product=None,
                               output=None, shadow_opacity=None)
        with (mock.patch.object(cli, "_load_valid", return_value=manifest),
              mock.patch.object(cli, "_job_paths",
                                return_value=("d", "b.png", "f.png")),
              mock.patch.object(cli, "_resolve_asset",
                                side_effect=lambda p, m: p),
             mock.patch.object(cli, "MSPCompositor", CliFake),
              mock.patch("os.path.exists", return_value=True)):
            cli.cmd_composite(args)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["lens_vignette"], 0.45)
        self.assertEqual(calls[0]["lens_bloom"], 0.3)
        self.assertEqual(calls[0]["lens_grain"], 2.2)


class ProbePreLensRegressionTests(unittest.TestCase):
    def test_probe_floor_composite_stays_pre_lens(self):
        # The probe applies the lens itself after the motion gates; the floor
        # route must not consume the lens kwargs or the grain would land twice.
        captured = {}

        class Fake:
            @classmethod
            def composite_rendered_floor_asset(cls, *args, **kwargs):
                captured.update(kwargs)
                return {"status": "success", "mode": "rendered_floor",
                        "output_path": str(args[3])}

        with tempfile.TemporaryDirectory() as temp:
            with mock.patch.object(probe, "MSPCompositor", Fake):
                probe.composite_frame(
                    Path(temp), None,
                    {"shadow_opacity": 0.5, "lens_vignette": 0.45,
                     "lens_bloom": 0.3, "lens_grain": 2.2},
                    True)
        self.assertEqual(captured.get("shadow_opacity"), 0.5)
        for key in ("lens_vignette", "lens_bloom", "lens_grain"):
            self.assertNotIn(key, captured)


class SharedWorkerFloorValidationParityTests(unittest.TestCase):
    """Every floor-validation case: shared errors and the worker agree."""

    @staticmethod
    def _cases():
        return [
            {"lighting": {"floor": {"enabled": True}},
             "output": {"film_transparent": False}},
            {"lighting": {}},
            {"lighting": {"floor": {"enabled": True}},
             "output": {"film_transparent": True}},
            {"lighting": {}, "output": {"film_transparent": False}},
            {"lighting": {"floor": {"enabled": True}},
             "output": {"film_transparent": False},
             "compositing": {"product_scale": 0.8}},
            {"lighting": {"floor": {"enabled": True}},
             "output": {"film_transparent": False},
             "compositing": {"product_offset_px": [10, 0]}},
            {"lighting": {"floor": {"enabled": True}},
             "output": {"film_transparent": False},
             "compositing": {"product_offset_pct": [0.0, -0.02]}},
            {"lighting": {"floor": {"enabled": True}},
             "output": {"film_transparent": False,
                        "passes": {"alpha_mask": False}}},
        ]

    def test_worker_raises_exactly_the_shared_error_codes(self):
        import render_worker
        import composite_worker
        for index, manifest in enumerate(self._cases()):
            with self.subTest(case=index):
                shared = {code.split(":", 1)[0] for code in
                          composite_worker.validate_floor_config(manifest)}
                try:
                    render_worker.validate_output_config(manifest)
                    worker = set()
                except ValueError as exc:
                    worker = {str(exc).split(":", 1)[0]}
                # The worker prefixes the non-boolean film error differently.
                worker = {"INVALID_FILM_TRANSPARENT" if code == "INVALID_OUTPUT_CONFIG"
                          else code for code in worker}
                self.assertEqual(shared, worker)


if __name__ == "__main__":
    unittest.main()

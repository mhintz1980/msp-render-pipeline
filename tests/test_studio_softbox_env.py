"""Direct tests for scripts/build_studio_softbox_env.py (batch 3e).

The generator gained a second profile, "horizon-lift", whose output is
backgrounds/env_studio-softbox-v2.png and which composes a horizon-band lift on
top of the accepted profile's *bytes*. These are the generator's first tests.
They pin the accepted profile byte-for-byte, enforce the v2 out-of-band
byte-identity (amendment 4), record the whole-orbit band invariants computed
from the maps themselves, and record the constraint-11 headroom state.

Numbers are measured on 2026-09-22 and restated in
output/batch3e-env-horizon-derivation.md, section "Revision after adversarial
review". They are asserted so they cannot drift silently.
"""

import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import build_studio_softbox_env as softbox  # noqa: E402
from scripts.build_studio_softbox_env import (  # noqa: E402
    ACCEPTED_OUTPUT, HEIGHT, HORIZON_LIFT, HORIZON_LIFT_OUTPUT, NEGFILL_COMP_ALPHA,
    PROFILE_ACCEPTED, PROFILE_HORIZON_LIFT, WIDTH, _decode_srgb, _encode_srgb,
    _horizon_window, _panel, build, guard_accepted_output,
)

# Accepted v1 map, the pinned anchor of DRAFT-2 constraint 1.
ACCEPTED_SHA256 = "bf67d7ea04884ae229ccb42f7dc62e0f98e79ade2bc52bd9954d24d5ec1b2b4f"
# v2 asset as generated 2026-09-22 by the horizon-lift profile (Pillow 12.3.0).
HORIZON_LIFT_SHA256 = "617e63a7de1a9833f6cb553cedad7675f5c5c942c2a769d24358fa9f32bccb86"

BAND_NARROW = (-20.0, 20.0)
BAND_EXTENDED = (-20.0, 30.0)

# Whole-orbit worst azimuth-to-azimuth step of the band column means (byte per
# column, wraparound), measured on the generated maps.
V1_STEP_NARROW = 0.9692982456140271
V2_STEP_NARROW = 0.5131578947368496
V1_STEP_EXTENDED = 1.136842105263156
V2_STEP_EXTENDED = 0.7684210526315667

# Constraint-11 state (recorded, not enforced - see the test comment).
BAND_ADDED_MAX = 0.385
BAND_PRECLIP_MAX = 1.2999732176452983
BAND_NEWLY_CLIPPED_PX = 13541

ELEVATION = (0.5 - (np.arange(HEIGHT) + 0.5) / HEIGHT) * 180.0
AZIMUTH = ((np.arange(WIDTH) + 0.5) / WIDTH) * 360.0


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _worst_azimuth_step(grey, band):
    """Max wrapped azimuth-to-azimuth step of the band column mean."""
    rows = np.where((ELEVATION >= band[0]) & (ELEVATION <= band[1]))[0]
    col = grey[rows, :].astype(np.float64).mean(axis=0)
    deltas = np.abs(np.diff(np.concatenate([col, col[:1]])))
    k = int(np.argmax(deltas))
    return float(deltas[k]), float(AZIMUTH[k])


class TestStudioSoftboxEnv(unittest.TestCase):

    def test_accepted_profile_is_byte_identical_to_tracked_png(self):
        """Constraint 1: the accepted profile reproduces the tracked v1 PNG."""
        tracked = np.asarray(Image.open(ACCEPTED_OUTPUT).convert("L"), dtype=np.uint8)
        self.assertEqual(tracked.shape, (HEIGHT, WIDTH))
        grey = build(profile=PROFILE_ACCEPTED)
        self.assertEqual(grey.shape, (HEIGHT, WIDTH))
        self.assertTrue(np.array_equal(grey, tracked),
                        "accepted profile no longer reproduces the tracked v1 map")
        # The no-argument default must be the accepted profile.
        self.assertTrue(np.array_equal(build(), tracked))
        self.assertEqual(_sha256(ACCEPTED_OUTPUT), ACCEPTED_SHA256)

    def test_srgb_roundtrip_is_exact(self):
        """The v2 byte-identity premise: decode(encode(x)) is the identity."""
        levels = np.arange(256, dtype=np.uint8)
        self.assertTrue(np.array_equal(_encode_srgb(_decode_srgb(levels)), levels))

    def test_horizon_lift_differs_and_holds_band_invariants(self):
        """Amendments 1 and 4: window shape, out-of-band identity, band step.

        The amended spec asked v2's worst in-band azimuth step to be at most
        HALF v1's (0.4846 narrow, 0.5684 extended). The pinned window's upper
        edge was moved to +30 for band coverage, and the measured ratios are
        0.52941 (narrow) and 0.67593 (extended): the half target is NOT met.
        The measured values are recorded here, with the shortfall flagged for
        the architect's correction (see the derivation revision).
        """
        v1 = build(profile=PROFILE_ACCEPTED)
        v2 = build(profile=PROFILE_HORIZON_LIFT)
        self.assertFalse(np.array_equal(v1, v2))

        window = _horizon_window(ELEVATION)
        in_band = window > 0.0
        # Compact support: exactly zero at and outside [-20, +30].
        self.assertTrue(np.all(window[ELEVATION <= -20.0] == 0.0))
        self.assertTrue(np.all(window[ELEVATION >= 30.0] == 0.0))
        self.assertTrue(np.all(window[(ELEVATION >= -14.0) & (ELEVATION <= 24.0)] == 1.0))
        self.assertAlmostEqual(float(_horizon_window(np.array([-17.0]))[0]), 0.5, places=12)
        self.assertAlmostEqual(float(_horizon_window(np.array([27.0]))[0]), 0.5, places=12)

        # Rows the window never reaches keep the accepted bytes exactly.
        self.assertTrue(np.array_equal(v2[~in_band, :], v1[~in_band, :]))
        delta = np.abs(v2.astype(int) - v1.astype(int))
        self.assertEqual(int(delta[~in_band, :].max()), 0)
        self.assertGreater(int(delta[in_band, :].max()), 0)

        step_v1_narrow, _ = _worst_azimuth_step(v1, BAND_NARROW)
        step_v2_narrow, _ = _worst_azimuth_step(v2, BAND_NARROW)
        step_v1_ext, _ = _worst_azimuth_step(v1, BAND_EXTENDED)
        step_v2_ext, _ = _worst_azimuth_step(v2, BAND_EXTENDED)
        self.assertAlmostEqual(step_v1_narrow, V1_STEP_NARROW, places=9)
        self.assertAlmostEqual(step_v2_narrow, V2_STEP_NARROW, places=9)
        self.assertAlmostEqual(step_v1_ext, V1_STEP_EXTENDED, places=9)
        self.assertAlmostEqual(step_v2_ext, V2_STEP_EXTENDED, places=9)
        # Strict improvement holds; the HALF target of the amended spec does not.
        self.assertLess(step_v2_narrow, step_v1_narrow)
        self.assertLess(step_v2_ext, step_v1_ext)

    def test_v2_asset_on_disk_matches_profile_output(self):
        """The checked-in v2 PNG is exactly what the profile generates."""
        grey = build(profile=PROFILE_HORIZON_LIFT)
        self.assertEqual(grey.shape, (HEIGHT, WIDTH))
        with Image.open(HORIZON_LIFT_OUTPUT) as img:
            self.assertEqual(img.size, (WIDTH, HEIGHT))
            tracked = np.asarray(img.convert("L"), dtype=np.uint8)
        self.assertTrue(np.array_equal(grey, tracked),
                        "backgrounds/env_studio-softbox-v2.png is stale; regenerate it")
        self.assertEqual(_sha256(HORIZON_LIFT_OUTPUT), HORIZON_LIFT_SHA256)

    def test_constraint_11_headroom_is_recorded(self):
        """Constraint 11, recorded rather than enforced (band-local reading).

        DRAFT-2 constraint 11 asked the pre-encode linear maximum to be <= 0.96
        so the lift cannot silently clip. The accepted map already clips to 1.0
        in the key core, and the pinned design forbids capping, so the bound is
        only meaningful over the region the lift alters. The measured in-band
        state is:
          composed (post-clip, pre-encode) max 1.0            -> above 0.96
          pre-clip max 1.2999732176452983 (v1 pre-clip 1.0744)
          added lift term max 0.385
          band pixels the lift newly pushes over 1.0: 13541
        These are pinned with an explicit comment flagging owner sign-off; they
        are NOT a claim that the 0.96 headroom was met.
        """
        v1 = build(profile=PROFILE_ACCEPTED)
        v2 = build(profile=PROFILE_HORIZON_LIFT)
        window = _horizon_window(ELEVATION)
        in_band = window > 0.0
        negfill = _panel(azimuth=300.0, elevation=-4.0, width_deg=120.0,
                         height_deg=90.0, softness_deg=22.0)
        added = window[:, None] * (HORIZON_LIFT + NEGFILL_COMP_ALPHA * negfill)
        linear_v1 = _decode_srgb(v1)
        raw = linear_v1 + added
        composed = np.clip(raw, 0.0, 1.0)

        self.assertAlmostEqual(float(added[in_band, :].max()), BAND_ADDED_MAX, places=12)
        self.assertAlmostEqual(float(composed[in_band, :].max()), 1.0, places=12)
        self.assertAlmostEqual(float(raw[in_band, :].max()), BAND_PRECLIP_MAX, places=9)
        self.assertEqual(
            int(((linear_v1 < 1.0) & (raw > 1.0) & in_band[:, None]).sum()),
            BAND_NEWLY_CLIPPED_PX)
        # Composing over the whole map and encoding once is what the file holds.
        self.assertTrue(np.array_equal(_encode_srgb(composed), v2))

    def test_manifests_use_the_declared_env_maps(self):
        """Ruling: rl300_05 flips to v2, rl300_04 stays on v1 deliberately."""
        floor_manifest = json.loads(
            (ROOT / "jobs" / "rl300_05_studio-floor.json").read_text())
        white_manifest = json.loads(
            (ROOT / "jobs" / "rl300_04_studio-white.json").read_text())
        self.assertEqual(floor_manifest["lighting"]["hdri_path"],
                         "backgrounds/env_studio-softbox-v2.png")
        self.assertEqual(white_manifest["lighting"]["hdri_path"],
                         "backgrounds/env_studio-softbox.png")

    def test_job_of_record_carries_the_accepted_rim_profile(self):
        """2026-09-24 owner acceptance: pool_soft is the rig look of record
        for the floor job (the job the 3h orbit measured); the stills job
        keeps the value absent (= pool_v1), the exact rig its accepted
        parity was measured with."""
        floor_manifest = json.loads(
            (ROOT / "jobs" / "rl300_05_studio-floor.json").read_text())
        white_manifest = json.loads(
            (ROOT / "jobs" / "rl300_04_studio-white.json").read_text())
        self.assertEqual(floor_manifest["lighting"]["rim_profile"],
                         "pool_soft")
        self.assertNotIn("rim_profile", white_manifest["lighting"])


class AcceptedOutputGuardTests(unittest.TestCase):
    """3e GLM finding 7: the accepted asset must never change on disk."""

    def test_guard_passes_the_reproducing_write_on_the_tracked_asset(self):
        # The tracked file hashes to the pin and the accepted profile
        # reproduces its bytes, so the exact write main() would make is
        # allowed through. This is also the encode-determinism tripwire: if
        # _png_bytes ever diverged from what save() wrote, leg 2 refuses.
        guard_accepted_output(ACCEPTED_OUTPUT, build(profile=PROFILE_ACCEPTED))

    def test_guard_refuses_when_the_existing_asset_has_diverged(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "env_studio-softbox.png"
            target.write_bytes(b"not the accepted map")
            with mock.patch.object(softbox, "ACCEPTED_OUTPUT", target):
                with self.assertRaisesRegex(SystemExit, "no longer matches"):
                    softbox.guard_accepted_output(
                        target, build(profile=PROFILE_ACCEPTED))

    def test_guard_refuses_bytes_that_would_change_the_asset(self):
        # No existing file (fresh-checkout shape) and the wrong profile aimed
        # at the accepted path: the write itself is refused. v1_path pins the
        # horizon-lift base to the real accepted map; the patch below only
        # moves the guard's ACCEPTED_OUTPUT.
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "env_studio-softbox.png"
            with mock.patch.object(softbox, "ACCEPTED_OUTPUT", target):
                with self.assertRaisesRegex(SystemExit,
                                            "would change its bytes"):
                    softbox.guard_accepted_output(
                        target,
                        build(profile=PROFILE_HORIZON_LIFT, v1_path=ACCEPTED_OUTPUT))

    def test_guard_passes_writes_to_any_other_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            other = Path(tmp) / "env_studio-softbox-v2.png"
            with mock.patch.object(softbox, "ACCEPTED_OUTPUT",
                                   Path(tmp) / "elsewhere.png"):
                softbox.guard_accepted_output(
                    other,
                    build(profile=PROFILE_HORIZON_LIFT, v1_path=ACCEPTED_OUTPUT))

    def test_guard_treats_a_hard_link_to_the_asset_as_the_asset(self):
        # Review finding 1: a resolved-path string comparison lets a hard
        # link through (resolves unequal, samefile True) and main() would
        # write through the link into the accepted inode.
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "env_studio-softbox.png"
            target.write_bytes(b"not the accepted map")
            alias = Path(tmp) / "alias.png"
            try:
                os.link(target, alias)
            except OSError:
                raise unittest.SkipTest("hard links unavailable on this fs")
            with mock.patch.object(softbox, "ACCEPTED_OUTPUT", target):
                with self.assertRaisesRegex(SystemExit, "no longer matches"):
                    softbox.guard_accepted_output(
                        alias, build(profile=PROFILE_ACCEPTED))

    @unittest.skipUnless(os.name == "nt", "case-insensitive lookup is Windows")
    def test_guard_matches_a_case_variant_output_while_the_asset_is_absent(self):
        # Review finding 1, second leg: with the asset absent, resolve()
        # keeps the typed case, so a case-variant --output would slip the
        # guard and Windows would create the accepted path with the wrong
        # profile's bytes. normcase closes it.
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "env_studio-softbox.png"
            variant = Path(tmp) / "ENV_STUDIO-Softbox.png"
            with mock.patch.object(softbox, "ACCEPTED_OUTPUT", target):
                with self.assertRaisesRegex(SystemExit,
                                            "would change its bytes"):
                    softbox.guard_accepted_output(
                        variant,
                        build(profile=PROFILE_HORIZON_LIFT,
                              v1_path=ACCEPTED_OUTPUT))


if __name__ == "__main__":
    unittest.main()

"""Build the equirectangular studio environment the metal reflects.

The white sweep plate is a backdrop: a smooth gradient with no features. That is
correct behind the machine and wrong in front of it, because a metal surface has
no colour of its own - it shows you its surroundings. Lit by a featureless
gradient, cast aluminium reflects the same near-white in every direction and
collapses into flat pale grey, which is exactly how the RL300 fittings read
beside the DD4 photograph.

This map gives them something to reflect: two bright soft sources, a cooler top
strip, and - just as important - a dark band where the camera and the unlit side
of the room are. The dark side is what produces the tonal falloff across a
curved barrel; without it the highlight has no shoulder and the part looks
plastic.

The output is an LDR PNG, not an HDR panorama, and that is deliberate: the
pipeline stages environments as PNG and the renderer multiplies by
`lighting.hdri_strength`, so the *ratio* between the sources and the walls is
what matters here, not the absolute values. At strength 2.0 the softboxes land
near 2.0 and the walls near 0.2.

This map is for `lighting.hdri_path` only. The visible backdrop stays
`env_studio-white.png` via `compositing.background_plate`.

Two profiles, one generator
---------------------------

``build(profile="accepted")`` (the default, and what ``main()`` selects with no
``--profile``) is the frozen v1 composition. Its output is pinned byte-for-byte to
``backgrounds/env_studio-softbox.png``
(sha256 bf67d7ea04884ae229ccb42f7dc62e0f98e79ade2bc52bd9954d24d5ec1b2b4f); it is
the accepted appearance reference for ``jobs/rl300_04_studio-white.json`` and must
never change.

``build(profile="horizon-lift")`` (batch 3e) composes a horizon-band lift on top
of the accepted profile's **bytes** and writes
``backgrounds/env_studio-softbox-v2.png``. The accepted map is sector-dark across
the horizon band, so a render whose background samples that sector (az42-type)
puts a flat dark wall plateau directly over a flat bright floor plateau, which
the background-band gate reads as a row step. The lift raises the band's floor
at every azimuth and neutralises the frozen negative fill where it bites,
leaving the key/fill/overhead cores untouched. It is the lighting environment
for ``jobs/rl300_05_studio-floor.json`` only. The visible backdrop is unchanged.
"""

import argparse
import hashlib
import io
import math
import os
from pathlib import Path

import numpy as np
from PIL import Image

WIDTH, HEIGHT = 2048, 1024

ROOT = Path(__file__).resolve().parents[1]
ACCEPTED_OUTPUT = ROOT / "backgrounds/env_studio-softbox.png"
HORIZON_LIFT_OUTPUT = ROOT / "backgrounds/env_studio-softbox-v2.png"

# The frozen v1 composition this file's docstring pins byte-for-byte (also
# asserted in tests/test_studio_softbox_env.py). Writing ACCEPTED_OUTPUT is
# refused unless the write reproduces these exact bytes (3e GLM finding 7).
ACCEPTED_SHA256 = "bf67d7ea04884ae229ccb42f7dc62e0f98e79ade2bc52bd9954d24d5ec1b2b4f"

# Profile names accepted by build() / --profile.
PROFILE_ACCEPTED = "accepted"
PROFILE_HORIZON_LIFT = "horizon-lift"

# v2 "horizon-lift" design (batch 3e). The window is compactly supported on
# [-20, +30] degrees elevation, flat over the core [-14, +24], smoothstep-tapered
# on the rising side (-20 -> -14) and the falling side (+24 -> +30), and exactly
# zero outside [-20, +30] so those rows stay byte-identical to the accepted map.
# Order: (lo_edge, lo_core, hi_core, hi_edge).
HORIZON_WINDOW_EL = (-20.0, -14.0, 24.0, 30.0)
HORIZON_LIFT = 0.30          # linear, pre-encode, added inside the window
NEGFILL_COMP_ALPHA = 0.085   # linear; neutralises the frozen negative fill in band


def _smoothstep(edge0, edge1, x):
    t = np.clip((x - edge0) / (edge1 - edge0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def _panel(azimuth, elevation, width_deg, height_deg, softness_deg=9.0):
    """A soft-edged rectangular source in equirectangular space."""
    u = (np.arange(WIDTH) + 0.5) / WIDTH * 360.0
    v = (np.arange(HEIGHT) + 0.5) / HEIGHT
    el = (0.5 - v) * 180.0

    # Wrap the azimuth delta into [-180, 180] so a panel can straddle the seam.
    du = np.abs((u - azimuth + 180.0) % 360.0 - 180.0)
    de = np.abs(el - elevation)

    half_w, half_h = width_deg / 2.0, height_deg / 2.0
    # An equirectangular map stretches azimuth near the poles; widen the panel by
    # 1/cos(elevation) so it stays rectangular in the world, not on the image.
    stretch = 1.0 / max(math.cos(math.radians(elevation)), 0.2)
    fu = 1.0 - _smoothstep(half_w * stretch - softness_deg * stretch,
                           half_w * stretch + softness_deg * stretch, du)
    fv = 1.0 - _smoothstep(half_h - softness_deg, half_h + softness_deg, de)
    return fv[:, None] * fu[None, :]


def _encode_srgb(env):
    """Linear scene value -> sRGB byte levels. The single encode path."""
    env = np.clip(env, 0.0, 1.0)
    srgb = np.where(env <= 0.0031308, env * 12.92,
                    1.055 * np.power(env, 1 / 2.4) - 0.055)
    return np.rint(np.clip(srgb, 0.0, 1.0) * 255).astype(np.uint8)


def _decode_srgb(grey):
    """sRGB byte levels -> linear scene value; inverse of _encode_srgb."""
    s = np.asarray(grey, dtype=np.float64) / 255.0
    return np.where(s <= 0.04045, s / 12.92, ((s + 0.055) / 1.055) ** 2.4)


def _horizon_window(elevation):
    """v2 elevation window: 1 over the core, 0 outside [-20, +30] degrees."""
    lo_edge, lo_core, hi_core, hi_edge = HORIZON_WINDOW_EL
    return _smoothstep(lo_edge, lo_core, elevation) * (
        1.0 - _smoothstep(hi_core, hi_edge, elevation))


def _build_accepted():
    v = (np.arange(HEIGHT) + 0.5) / HEIGHT
    elevation = (0.5 - v) * 180.0

    # Walls: a dim, very slightly cool room. Everything else is added on top.
    env = np.full((HEIGHT, WIDTH), 0.10, dtype=np.float64)

    # Floor bounce - the sweep the machine stands on, brighter than the walls
    # because it is the lit surface directly under the sources.
    floor = _smoothstep(0.0, -35.0, elevation)
    env += 0.14 * floor[:, None]

    # Key: a large softbox high and to the camera's left.
    env += 0.95 * _panel(azimuth=18.0, elevation=38.0, width_deg=62.0, height_deg=40.0)
    # Fill: broader, dimmer, opposite side, to open up the shadowed flank.
    env += 0.34 * _panel(azimuth=205.0, elevation=22.0, width_deg=78.0, height_deg=34.0)
    # Overhead strip, for the long highlight down a horizontal barrel.
    env += 0.26 * _panel(azimuth=110.0, elevation=68.0, width_deg=150.0, height_deg=26.0)

    # Negative fill behind the camera. Cast aluminium needs somewhere dark to
    # reflect or the highlight never resolves into a shoulder.
    env -= 0.085 * _panel(azimuth=300.0, elevation=-4.0, width_deg=120.0, height_deg=90.0,
                          softness_deg=22.0)

    env = np.clip(env, 0.0, 1.0)
    # Encode straight to sRGB bytes; the renderer decodes it back on load.
    return _encode_srgb(env)


def _build_horizon_lift(v1_path=ACCEPTED_OUTPUT):
    """v2 profile: the accepted bytes plus a horizon-band lift, encoded once.

    The base is the accepted PNG's *bytes*, decoded with '_decode_srgb'; nothing
    is rebuilt from generator floats and nothing is renormalised, so the rows the
    window never reaches (elevation outside [-20, +30] degrees) keep the accepted
    map's exact byte values.
    """
    v1 = np.asarray(Image.open(v1_path).convert("L"), dtype=np.uint8)
    if v1.shape != (HEIGHT, WIDTH):
        raise ValueError(f"base env map {v1_path} is {v1.shape}, expected {(HEIGHT, WIDTH)}")

    v = (np.arange(HEIGHT) + 0.5) / HEIGHT
    elevation = (0.5 - v) * 180.0
    window = _horizon_window(elevation)[:, None]

    # The same frozen negative-fill panel the accepted profile carves out. The
    # compensation term can only neutralise it inside the band, never invert it.
    negfill = _panel(azimuth=300.0, elevation=-4.0, width_deg=120.0, height_deg=90.0,
                     softness_deg=22.0)

    linear = _decode_srgb(v1)
    composed = np.clip(
        linear + window * (HORIZON_LIFT + NEGFILL_COMP_ALPHA * negfill), 0.0, 1.0)
    encoded = _encode_srgb(composed)

    out = v1.copy()
    in_band = window[:, 0] > 0.0
    out[in_band, :] = encoded[in_band, :]
    return out


def build(profile=PROFILE_ACCEPTED, *, v1_path=None):
    """Return the map for 'profile' as an (HEIGHT, WIDTH) uint8 grey array."""
    if profile == PROFILE_ACCEPTED:
        return _build_accepted()
    if profile == PROFILE_HORIZON_LIFT:
        return _build_horizon_lift(ACCEPTED_OUTPUT if v1_path is None else Path(v1_path))
    raise ValueError(f"unknown profile {profile!r}; choose one of "
                     f"{PROFILE_ACCEPTED!r}, {PROFILE_HORIZON_LIFT!r}")


def _png_bytes(grey):
    """The exact bytes main() would write for 'grey' (same save parameters)."""
    pixels = np.repeat(np.asarray(grey)[..., None], 3, axis=2)
    buffer = io.BytesIO()
    Image.fromarray(pixels).save(buffer, format="PNG", compress_level=9)
    return buffer.getvalue()


def _targets_accepted_output(output) -> bool:
    """True when 'output' names the accepted asset - directly, case-variant,
    or through a link.

    Review finding 1: a resolved-path string comparison misses a hard link
    (resolves unequal, samefile True) and a case-variant spelling while the
    asset is absent (Windows would then create the accepted path with
    another profile's bytes). Compare files when both exist, else compare
    normcased realpaths.
    """
    if (os.path.normcase(str(Path(output).resolve()))
            == os.path.normcase(str(ACCEPTED_OUTPUT.resolve()))):
        return True
    try:
        return os.path.samefile(output, ACCEPTED_OUTPUT)
    except OSError:
        return False


def guard_accepted_output(output, grey) -> None:
    """Refuse any write to ACCEPTED_OUTPUT that would not reproduce it.

    Two refusals, both before the file is touched: an existing file that no
    longer hashes to ACCEPTED_SHA256 means the accepted asset has diverged
    and regenerating would silently destroy that state; bytes about to be
    written that do not hash to ACCEPTED_SHA256 mean the generator - or a
    --output aimed here with another profile - no longer reproduces the
    frozen composition. Writes anywhere else pass through untouched.
    """
    if not _targets_accepted_output(output):
        return
    if ACCEPTED_OUTPUT.is_file():
        existing = hashlib.sha256(ACCEPTED_OUTPUT.read_bytes()).hexdigest()
        if existing != ACCEPTED_SHA256:
            raise SystemExit(
                f"REFUSED: {ACCEPTED_OUTPUT} no longer matches the pinned "
                f"accepted sha256 {ACCEPTED_SHA256} (found {existing}); "
                "regenerating would overwrite a modified accepted asset - "
                "resolve manually")
    new_sha = hashlib.sha256(_png_bytes(grey)).hexdigest()
    if new_sha != ACCEPTED_SHA256:
        raise SystemExit(
            f"REFUSED: writing to {ACCEPTED_OUTPUT} would change its bytes "
            f"(pinned sha256 {ACCEPTED_SHA256}, this build hashes to "
            f"{new_sha}); the accepted asset must never change")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--profile",
        choices=(PROFILE_ACCEPTED, PROFILE_HORIZON_LIFT),
        default=PROFILE_ACCEPTED,
        help="accepted = frozen v1 map; horizon-lift = batch 3e v2 map",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="output PNG (default: backgrounds/env_studio-softbox.png for the "
             "accepted profile, backgrounds/env_studio-softbox-v2.png for horizon-lift)",
    )
    args = parser.parse_args()
    output = args.output
    if output is None:
        output = ACCEPTED_OUTPUT if args.profile == PROFILE_ACCEPTED else HORIZON_LIFT_OUTPUT
    grey = build(profile=args.profile)
    guard_accepted_output(output, grey)
    pixels = np.repeat(grey[..., None], 3, axis=2)
    output.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(pixels).save(output, compress_level=9)
    print(f"Studio softbox environment [{args.profile}]: {output} ({WIDTH}x{HEIGHT}, equirectangular, "
          f"byte range {int(grey.min())}-{int(grey.max())})")


if __name__ == "__main__":
    main()

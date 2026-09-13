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
"""

import argparse
import math
from pathlib import Path

import numpy as np
from PIL import Image

WIDTH, HEIGHT = 2048, 1024


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


def build():
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
    srgb = np.where(env <= 0.0031308, env * 12.92, 1.055 * np.power(env, 1 / 2.4) - 0.055)
    return np.rint(np.clip(srgb, 0, 1) * 255).astype(np.uint8)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "backgrounds/env_studio-softbox.png",
    )
    args = parser.parse_args()
    grey = build()
    pixels = np.repeat(grey[..., None], 3, axis=2)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(pixels).save(args.output, compress_level=9)
    print(f"Studio softbox environment: {args.output} ({WIDTH}x{HEIGHT}, equirectangular, "
          f"byte range {int(grey.min())}-{int(grey.max())})")


if __name__ == "__main__":
    main()

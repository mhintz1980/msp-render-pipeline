"""Build the neutral, seamless LDR plate used by the white studio job.

Run from any directory with the repository's Python environment. The analytic
studio softboxes supply directional highlights; this plate supplies gentle
neutral fill and the composite background, not a calibrated HDR panorama.
"""

import argparse
from pathlib import Path

import numpy as np
from PIL import Image


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "backgrounds/env_studio-white.png",
    )
    args = parser.parse_args()
    # Broad, neutral white wall rolling into a slightly darker foreground.
    # No baked object/shadow, horizon line, texture, or colour cast.
    width, height = 1800, 1250
    y, x = np.mgrid[0:height, 0:width]
    x = x / (width - 1)
    y = y / (height - 1)
    glow = np.exp(-((x - 0.5) / 0.58) ** 2 - ((y - 0.35) / 0.48) ** 2)
    floor = np.clip((y - 0.5) / 0.5, 0, 1)
    sweep = np.rint(244 + 8 * glow - 9 * floor * floor).astype(np.uint8)
    pixels = np.repeat(sweep[..., None], 3, axis=2)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(pixels).save(args.output, compress_level=9)
    print(f"White studio plate: {args.output} ({width}x{height}, RGB)")


if __name__ == "__main__":
    main()

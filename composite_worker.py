"""
Zero-Loss Product Compositor and Grounding Engine for Myers-Seth Pumps.

Takes a transparent-film Cycles render (the "beauty" pass) and seats it on a
photographic background plate with a synthesized ground contact shadow, while
guaranteeing that not one machine pixel is altered in the process.

The render is never resampled: the plate is scaled and cropped to the render's
canvas, not the other way around.
"""

import os
from typing import Optional, Tuple, Dict, Any, Sequence
import numpy as np
from PIL import Image, ImageFilter, ImageOps


class MSPCompositor:
    """
    Composites CAD renders and studio photos onto real-world backgrounds
    with authentic contact shadows and ambient occlusion.
    """

    @staticmethod
    def _mask_bounds(mask: Image.Image) -> Tuple[int, int, int, int]:
        """Returns (left, top, right, bottom) of the opaque product silhouette."""
        bbox = mask.point(lambda px: 255 if px > 8 else 0).getbbox()
        if bbox is None:
            raise ValueError(
                "The product image is fully transparent - there is nothing to "
                "composite. Check that the render actually produced geometry.")
        return bbox

    @classmethod
    def create_contact_shadow(
        cls,
        alpha_mask: Image.Image,
        shadow_opacity: float = 0.85,
        penumbra_blur: float = 16.0,
        contact_blur: float = 3.5,
        y_offset_px: int = 4,
        sun_direction: str = "top_left",
    ) -> Image.Image:
        """
        Synthesizes dual-tier photorealistic grounding:
        1. Core Contact AO: tight, dark contact line directly under the skid feet.
        2. Directional Penumbra: soft falloff cast along the ground plane.

        Both tiers are anchored to the *measured* bottom of the silhouette rather
        than a fixed fraction of the canvas, so the shadow follows the machine
        wherever the camera framing puts it.
        """
        w, h = alpha_mask.size
        mask_np = np.array(alpha_mask)
        left, top, right, bottom = cls._mask_bounds(alpha_mask)
        product_h = max(1, bottom - top)

        # --- 1. TIGHT CONTACT AO -------------------------------------------------
        # Take the bottom 14% of the machine (the skid rails and feet) and squash
        # it into a thin dark band sitting exactly at the contact line.
        contact_top = max(top, bottom - int(product_h * 0.14))
        contact_np = np.zeros_like(mask_np)
        contact_np[contact_top:bottom, :] = mask_np[contact_top:bottom, :]

        ao_h = max(4, int(product_h * 0.055))
        ao_squashed = Image.fromarray(contact_np).resize((w, ao_h), Image.Resampling.BILINEAR)
        ao_canvas = Image.new("L", (w, h), 0)
        ao_canvas.paste(ao_squashed, (0, min(h - ao_h, bottom - ao_h // 2 + y_offset_px)))
        core_ao = ao_canvas.filter(ImageFilter.GaussianBlur(radius=contact_blur))

        # --- 2. DIRECTIONAL PENUMBRA --------------------------------------------
        # The lower 35% of the machine, faded in from the top so the cast shadow
        # dissolves rather than starting with a hard edge.
        pen_top = max(top, bottom - int(product_h * 0.35))
        pen_np = np.zeros_like(mask_np)
        pen_np[pen_top:bottom, :] = mask_np[pen_top:bottom, :]
        fade_rows = max(1, (bottom - pen_top) // 2)
        for i in range(fade_rows):
            y = pen_top + i
            pen_np[y, :] = (pen_np[y, :] * (i / fade_rows)).astype(np.uint8)

        pen_h = max(12, int(product_h * 0.20))
        pen_squashed = Image.fromarray(pen_np).resize((w, pen_h), Image.Resampling.BILINEAR)
        x_shift = int(w * 0.06) if sun_direction == "top_left" else int(-w * 0.06)
        pen_canvas = Image.new("L", (w, h), 0)
        pen_canvas.paste(pen_squashed, (x_shift, min(h - pen_h, bottom - pen_h // 3 + y_offset_px)))
        soft_penumbra = pen_canvas.filter(ImageFilter.GaussianBlur(radius=penumbra_blur))

        combined = Image.blend(soft_penumbra, core_ao, 0.5)
        # Non-linear curve: the contact line goes dark, the edges feather out.
        return Image.eval(combined, lambda px: int(min(255, px * 1.4) * shadow_opacity))

    @staticmethod
    def _place_product(
        prod_img: Image.Image,
        canvas_size: Tuple[int, int],
        scale: float,
        offset_px: Sequence[int],
    ) -> Image.Image:
        """Scales and offsets the product on a transparent canvas of canvas_size."""
        if scale == 1.0 and tuple(offset_px) == (0, 0) and prod_img.size == canvas_size:
            return prod_img
        w, h = canvas_size
        scaled = prod_img
        if scale != 1.0:
            scaled = prod_img.resize(
                (max(1, int(prod_img.width * scale)), max(1, int(prod_img.height * scale))),
                Image.Resampling.LANCZOS)
        canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        x = (w - scaled.width) // 2 + int(offset_px[0])
        y = (h - scaled.height) // 2 + int(offset_px[1])
        # paste() accepts negative coordinates and clips for us; alpha_composite()
        # does not, and a machine pushed partly off-canvas is a legitimate framing.
        canvas.paste(scaled, (x, y), scaled)
        return canvas

    @staticmethod
    def _save_robustly(image: Image.Image, output_image_path: str) -> str:
        """
        Writes the finished image, surviving a viewer holding the old one open.

        On Windows, re-running a job while the previous result is still open in
        Photos makes a plain save fail with EINVAL - which is exactly what
        happens when you run a demo step twice. Writing to a sibling temp file
        and renaming over the target succeeds even against an open viewer; if
        the rename is refused too, fall back to a numbered filename rather than
        losing a render that has already been paid for in GPU time.
        """
        out_path = os.path.abspath(output_image_path)
        out_dir = os.path.dirname(out_path)
        os.makedirs(out_dir, exist_ok=True)

        tmp_path = out_path + ".tmp.png"
        image.save(tmp_path, "PNG")
        try:
            os.replace(tmp_path, out_path)
            return out_path
        except OSError:
            stem, ext = os.path.splitext(out_path)
            for n in range(1, 100):
                alt = f"{stem}_{n:02d}{ext}"
                if not os.path.exists(alt):
                    os.replace(tmp_path, alt)
                    print(f"  ! {os.path.basename(out_path)} is open in another "
                          f"program; wrote {os.path.basename(alt)} instead.")
                    return alt
            os.remove(tmp_path)
            raise

    @classmethod
    def composite_asset(
        cls,
        product_image_path: str,
        background_image_path: str,
        output_image_path: str,
        mask_image_path: Optional[str] = None,
        shadow_opacity: float = 0.85,
        target_size: Optional[Tuple[int, int]] = None,
        product_scale: float = 1.0,
        product_offset_px: Sequence[int] = (0, 0),
        product_offset_pct: Optional[Sequence[float]] = None,
        sun_direction: str = "top_left",
    ) -> Dict[str, Any]:
        """
        Merges product and background while strictly preserving machine pixels.

        target_size defaults to the product render's own resolution so the hero
        render is never resampled; the plate is fitted to it instead.

        product_offset_pct expresses placement as a fraction of the canvas, so a
        composite tuned on a fast 800px preview lands identically on the 1800px
        final. It is added to product_offset_px.
        """
        if not os.path.exists(product_image_path):
            raise FileNotFoundError(f"Product image not found: {product_image_path}")
        if not os.path.exists(background_image_path):
            raise FileNotFoundError(f"Background plate not found: {background_image_path}")

        prod_img = Image.open(product_image_path).convert("RGBA")
        bg_img = Image.open(background_image_path).convert("RGB")

        canvas_size = tuple(target_size) if target_size else prod_img.size
        offset = [int(product_offset_px[0]), int(product_offset_px[1])]
        if product_offset_pct:
            offset[0] += int(round(product_offset_pct[0] * canvas_size[0]))
            offset[1] += int(round(product_offset_pct[1] * canvas_size[1]))
        prod_img = cls._place_product(prod_img, canvas_size, product_scale, offset)
        bg_img = ImageOps.fit(bg_img, canvas_size, Image.Resampling.LANCZOS)

        if mask_image_path and os.path.exists(mask_image_path):
            mask = Image.open(mask_image_path).convert("L")
            if mask.size != canvas_size:
                mask = ImageOps.fit(mask, canvas_size, Image.Resampling.NEAREST)
        else:
            mask = prod_img.split()[3]

        contact_shadow = cls.create_contact_shadow(
            mask, shadow_opacity=shadow_opacity, sun_direction=sun_direction)

        # Multiply the shadow into the plate.
        bg_np = np.array(bg_img, dtype=np.float32) / 255.0
        shadow_np = np.array(contact_shadow, dtype=np.float32) / 255.0
        darkened = bg_np * (1.0 - shadow_np[:, :, np.newaxis] * 0.75)
        shadowed_bg = Image.fromarray(np.clip(darkened * 255.0, 0, 255).astype(np.uint8))

        final_comp = shadowed_bg.copy()
        final_comp.paste(prod_img, (0, 0), mask)

        output_image_path = cls._save_robustly(final_comp, output_image_path)

        # --- Product Pixel Integrity Gate ---------------------------------------
        prod_np = np.array(prod_img.convert("RGB"))
        final_np = np.array(final_comp)
        # Only fully opaque pixels can be byte-exact: paste() alpha-blends
        # anything below 255, so a partially transparent antialiased edge pixel
        # is *supposed* to pick up the plate behind it. Gating on >250 instead of
        # ==255 reports a false failure on any render that has been rescaled.
        mask_binary = np.array(mask) == 255
        if mask_binary.any():
            diff = np.abs(prod_np[mask_binary].astype(int) - final_np[mask_binary].astype(int))
            max_diff, mean_diff = int(np.max(diff)), float(np.mean(diff))
        else:
            max_diff, mean_diff = 0, 0.0

        left, top, right, bottom = cls._mask_bounds(mask)
        return {
            "output_path": output_image_path,
            "status": "success",
            "fidelity_gate_pass": max_diff == 0,
            "max_pixel_drift": max_diff,
            "mean_pixel_drift": mean_diff,
            "dimensions": final_comp.size,
            "product_bbox": (left, top, right, bottom),
            "coverage_pct": round(100.0 * float(mask_binary.mean()), 2),
        }


if __name__ == "__main__":
    import sys
    if len(sys.argv) >= 4:
        res = MSPCompositor.composite_asset(sys.argv[1], sys.argv[2], sys.argv[3])
        print(f"Compositing completed: {res}")
    else:
        print("usage: python composite_worker.py <product.png> <background.png> <output.png>")

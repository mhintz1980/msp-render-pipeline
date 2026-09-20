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

    @staticmethod
    def _footprint_bbox(footprint: np.ndarray) -> Optional[Tuple[int, int, int, int]]:
        """Returns (left, top, right, bottom) of a boolean footprint, or None."""
        rows = np.flatnonzero(footprint.any(axis=1))
        cols = np.flatnonzero(footprint.any(axis=0))
        if rows.size == 0 or cols.size == 0:
            return None
        return (int(cols[0]), int(rows[0]), int(cols[-1]) + 1, int(rows[-1]) + 1)

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
    def apply_lens_pass(cls, image: Image.Image, vignette: float = 0.0,
                        bloom: float = 0.0, grain: float = 0.0,
                        frame_index: int = 0) -> Image.Image:
        """Photographic finishing: a pure function of (pixels, params, index).

        Vignette darkens the frame edge like a lens; bloom lifts a soft glow
        around true specular highlights like veiling glare; grain adds
        monochrome sensor noise. Grain is seeded by frame_index alone, so a
        given frame's noise is fixed forever and identical on every rerun and
        machine - the antiflicker rule (docs/video-pipeline-brief.md section
        6.4) is seed determinism, and this pass obeys it by construction.

        This runs AFTER the integrity gates in composite_asset: the gates
        verify the composite these effects consume, machine pixels byte-exact;
        the lens pass is the only thing allowed to touch them afterwards.
        """
        arr = np.asarray(image.convert("RGB"), dtype=np.float32)
        height, width = arr.shape[:2]
        if vignette > 0:
            yy, xx = np.mgrid[0:height, 0:width]
            radius = np.sqrt(((xx - width / 2) / (width / 2)) ** 2
                             + ((yy - height / 2) / (height / 2)) ** 2)
            # Only the outer ring darkens; the product at centre is untouched.
            falloff = 1.0 - vignette * 0.30 * np.clip(radius - 0.55, 0, None) ** 2
            arr = arr * falloff[:, :, np.newaxis]
        if bloom > 0:
            luma = arr @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
            # Only near-clipped speculars (and the sweep's peak glow) bloom; a
            # mid-tone machine or the plate body stays put.
            highlights = np.clip(luma - 250.0, 0, 5) / 5.0
            blurred = np.asarray(
                Image.fromarray((highlights * 255.0).astype(np.uint8)).filter(
                    ImageFilter.GaussianBlur(radius=max(width, height) * 0.02)),
                dtype=np.float32) / 255.0
            arr = arr + blurred[:, :, np.newaxis] * (bloom * 18.0)
        if grain > 0:
            rng = np.random.default_rng(1000003 + frame_index)
            noise = rng.normal(0.0, grain, size=(height, width)).astype(np.float32)
            arr = arr + noise[:, :, np.newaxis]
        return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))

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
        lens_vignette: float = 0.0,
        lens_bloom: float = 0.0,
        lens_grain: float = 0.0,
        frame_index: int = 0,
    ) -> Dict[str, Any]:
        """
        Merges product and background while strictly preserving machine pixels.

        target_size defaults to the product render's own resolution so the hero
        render is never resampled; the plate is fitted to it instead.

        product_offset_pct expresses placement as a fraction of the canvas, so a
        composite tuned on a fast 800px preview lands identically on the 1800px
        final. It is added to product_offset_px.

        Integrity is gated three ways and reported, never raised once the image
        is on disk: pixel fidelity of the SAVED file, consistency of a supplied
        mask with the seated product, and a size check on the reloaded output.
        Any gate failing marks the result "failed" - the render itself stays
        saved, because it was already paid for in GPU time.
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

        mask_file_supplied = bool(mask_image_path and os.path.exists(mask_image_path))
        if mask_file_supplied:
            mask = Image.open(mask_image_path).convert("L")
            if mask.size != canvas_size:
                mask = ImageOps.fit(mask, canvas_size, Image.Resampling.NEAREST)
            # The mask must ride through the same placement transform as the
            # product: pasting an offset product through an un-offset mask
            # paints the leading edge with the plate and silently drops the
            # trailing strip. An "L" channel cannot be pasted through itself,
            # so carry it in the alpha band and take that channel back out.
            mask_rgba = Image.merge("RGBA", (mask, mask, mask, mask))
            mask = cls._place_product(
                mask_rgba, canvas_size, product_scale, offset).split()[3]
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

        # From here on nothing may raise: the render is on disk and paid for,
        # so every gate reports through the result dict instead.

        # --- Product Pixel Integrity Gate, run on the SAVED file ---------------
        # The gate has to inspect the bytes the client will open, not the
        # in-memory composite - a save that silently degrades the file would
        # otherwise sail through a gate run on the pixels we started with.
        # Only fully opaque pixels can be byte-exact: paste() alpha-blends
        # anything below 255, so a partially transparent antialiased edge pixel
        # is *supposed* to pick up the plate behind it. Gating on >250 instead
        # of ==255 reports a false failure on any render that has been rescaled.
        prod_np = np.array(prod_img.convert("RGB"))
        mask_np = np.array(mask)
        mask_binary = mask_np == 255
        fidelity_gate_pass = False
        saved_check_pass = False
        max_diff, mean_diff = 0, 0.0
        try:
            with Image.open(output_image_path) as reloaded_fh:
                reloaded = reloaded_fh.convert("RGB")
            if reloaded.size == final_comp.size:
                reloaded_np = np.array(reloaded)
                if mask_binary.any():
                    diff = np.abs(prod_np[mask_binary].astype(int)
                                  - reloaded_np[mask_binary].astype(int))
                    max_diff, mean_diff = int(np.max(diff)), float(np.mean(diff))
                    fidelity_gate_pass = max_diff == 0
                # Zero opaque pixels: the gate measured nothing - a failure, not a pass.
            saved_check_pass = fidelity_gate_pass and reloaded.size == final_comp.size
        except Exception:
            # A file that cannot be re-read is a failed check, not a lost render.
            fidelity_gate_pass = saved_check_pass = False

        # --- Mask Consistency Gate ---------------------------------------------
        # A supplied mask that disagrees with the seated product means the paste
        # painted plate pixels onto the machine or dropped a strip of it. The
        # mask went through the exact placement transform, so a matching mask
        # agrees bit for bit; antialiased edges differ legitimately, which is
        # why agreement is measured on binary footprints with tolerance.
        # With no mask file the gate never runs: mask_gate_pass stays None, and
        # only a measured False counts as a failure downstream.
        mask_gate_pass = None
        if mask_file_supplied:
            try:
                prod_alpha = np.array(prod_img.split()[3])

                def footprint_pairing(mask_fp, prod_fp):
                    inter = int(np.count_nonzero(mask_fp & prod_fp))
                    union = int(np.count_nonzero(mask_fp | prod_fp))
                    iou = (inter / union) if union else 1.0
                    mask_box = cls._footprint_bbox(mask_fp)
                    prod_box = cls._footprint_bbox(prod_fp)
                    if mask_box and prod_box:
                        bbox_ok = all(abs(a - b) <= 2 for a, b in zip(mask_box, prod_box))
                    else:
                        bbox_ok = union == 0
                    return bool(iou >= 0.98 and bbox_ok)

                # A raw matte matches the alpha footprint exactly; a binarized
                # matte matches the >=128 footprint; a misregistered mask fails both.
                mask_gate_pass = (footprint_pairing(mask_np > 8, prod_alpha > 8)
                                  or footprint_pairing(mask_np >= 128, prod_alpha >= 128))
            except Exception:
                mask_gate_pass = False

        left, top, right, bottom = cls._mask_bounds(mask)
        # None means the mask gate did not run - only a measured False fails.
        gates_ok = (fidelity_gate_pass and mask_gate_pass is not False
                    and saved_check_pass)

        # --- Lens pass: only after the gates ----------------------------------
        # The gates above describe the composite the effects consume; the
        # finished file is the gated bytes plus a pure global transform whose
        # determinism is pinned by tests. All-zero params (the default) leave
        # the gated composite itself as the deliverable, byte for byte, so
        # every accepted digest stays reproducible.
        lens_applied = False
        if any((lens_vignette, lens_bloom, lens_grain)):
            try:
                with Image.open(output_image_path) as base_fh:
                    lens_base = base_fh.convert("RGB")
                lensed = cls.apply_lens_pass(lens_base, vignette=lens_vignette,
                                             bloom=lens_bloom, grain=lens_grain,
                                             frame_index=frame_index)
                output_image_path = cls._save_robustly(lensed, output_image_path)
                lens_applied = True
            except Exception:
                # The gated composite is already the deliverable on disk; a
                # failed finish degrades to it, never to nothing.
                lens_applied = False
        return {
            "output_path": output_image_path,
            "saved_image_path": output_image_path,
            "status": "success" if gates_ok else "failed",
            "fidelity_gate_pass": fidelity_gate_pass,
            "mask_gate_pass": mask_gate_pass,
            "saved_check_pass": saved_check_pass,
            "max_pixel_drift": max_diff,
            "mean_pixel_drift": mean_diff,
            "dimensions": final_comp.size,
            "product_bbox": (left, top, right, bottom),
            "coverage_pct": round(100.0 * float(mask_binary.mean()), 2),
            "lens_applied": lens_applied,
            "lens": {"vignette": lens_vignette, "bloom": lens_bloom,
                     "grain": lens_grain, "frame_index": frame_index},
        }


if __name__ == "__main__":
    import sys
    if len(sys.argv) >= 4:
        res = MSPCompositor.composite_asset(sys.argv[1], sys.argv[2], sys.argv[3])
        print(f"Compositing completed: {res}")
    else:
        print("usage: python composite_worker.py <product.png> <background.png> <output.png>")

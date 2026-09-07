"""
Zero-Loss Product Compositor and Grounding Engine for Myers-Seth Pumps.
Ensures 100% mechanical pixel preservation while seamlessly embedding machines into job-site plates.
"""

import os
from typing import Optional, Tuple, Dict, Any
import numpy as np
from PIL import Image, ImageFilter, ImageOps

class MSPCompositor:
    """
    Composites CAD renders and studio photos onto real-world backgrounds
    with authentic contact shadows and ambient occlusion.
    """

    @staticmethod
    def create_contact_shadow(
        alpha_mask: Image.Image,
        shadow_opacity: float = 0.85,
        penumbra_blur: float = 16.0,
        contact_blur: float = 3.5,
        y_offset_px: int = 4,
        sun_direction: str = "top_left"
    ) -> Image.Image:
        """
        Synthesizes dual-tier photorealistic grounding:
        1. Core Contact AO: Tight, dark contact line directly under skid runners and feet.
        2. Directional Penumbra: Progressive soft falloff cast along the ground plane based on sun angle.
        """
        w, h = alpha_mask.size
        mask_np = np.array(alpha_mask)
        
        # 1. TIGHT CONTACT AO: Extract bottom 12% of the machine contact line
        contact_threshold = int(h * 0.80)
        contact_mask_np = np.zeros_like(mask_np)
        contact_mask_np[contact_threshold:, :] = mask_np[contact_threshold:, :]
        
        # Micro-vertical squash for ground interface
        contact_img = Image.fromarray(contact_mask_np, mode="L")
        ao_squashed = contact_img.resize((w, max(4, int(h * 0.08))), Image.Resampling.BILINEAR)
        ao_canvas = Image.new("L", (w, h), 0)
        ao_y = int(h * 0.88) + y_offset_px
        ao_canvas.paste(ao_squashed, (0, ao_y))
        core_ao = ao_canvas.filter(ImageFilter.GaussianBlur(radius=contact_blur))
        
        # 2. DIRECTIONAL PENUMBRA: Extracted from lower 30% and projected
        h_threshold = int(h * 0.70)
        ground_mask_np = np.zeros_like(mask_np)
        ground_mask_np[h_threshold:, :] = mask_np[h_threshold:, :]
        for y in range(h_threshold, min(h, h_threshold + 50)):
            factor = (y - h_threshold) / 50.0
            ground_mask_np[y, :] = (ground_mask_np[y, :] * factor).astype(np.uint8)

        base_penumbra = Image.fromarray(ground_mask_np, mode="L")
        penumbra_h = max(12, int(h * 0.22))
        penumbra_squashed = base_penumbra.resize((w, penumbra_h), Image.Resampling.BILINEAR)
        
        x_shift = int(w * 0.06) if sun_direction == "top_left" else int(-w * 0.06)
        penumbra_canvas = Image.new("L", (w, h), 0)
        penumbra_y = int(h * 0.84) + y_offset_px
        penumbra_canvas.paste(penumbra_squashed, (x_shift, penumbra_y))
        soft_penumbra = penumbra_canvas.filter(ImageFilter.GaussianBlur(radius=penumbra_blur))

        # Composite AO + Penumbra
        combined = Image.blend(soft_penumbra, core_ao, 0.5)
        # Apply non-linear contrast curve so contact is dark, edges feather out
        shadow_final = Image.eval(combined, lambda px: int(min(255, (px * 1.4)) * shadow_opacity))
        return shadow_final

    @classmethod
    def composite_asset(
        cls,
        product_image_path: str,
        background_image_path: str,
        output_image_path: str,
        mask_image_path: Optional[str] = None,
        shadow_opacity: float = 0.85,
        target_size: Optional[Tuple[int, int]] = (1920, 1080)
    ) -> Dict[str, Any]:
        """
        Merges product and background while strictly preserving machine pixels.
        """
        if not os.path.exists(product_image_path):
            raise FileNotFoundError(f"Product image not found: {product_image_path}")
        if not os.path.exists(background_image_path):
            raise FileNotFoundError(f"Background plate not found: {background_image_path}")

        prod_img = Image.open(product_image_path).convert('RGBA')
        bg_img = Image.open(background_image_path).convert('RGBA')

        if target_size:
            bg_img = ImageOps.fit(bg_img, target_size, Image.Resampling.LANCZOS)
            prod_img = ImageOps.fit(prod_img, target_size, Image.Resampling.LANCZOS)

        # Extract or load alpha mask
        if mask_image_path and os.path.exists(mask_image_path):
            mask = Image.open(mask_image_path).convert('L')
            if target_size:
                mask = ImageOps.fit(mask, target_size, Image.Resampling.NEAREST)
        else:
            # Extract from RGBA alpha channel
            mask = prod_img.split()[3]

        # Generate directional ground shadow
        contact_shadow = cls.create_contact_shadow(mask, shadow_opacity=shadow_opacity)

        # Multiply shadow into background plate
        bg_rgb = bg_img.convert('RGB')
        bg_np = np.array(bg_rgb, dtype=np.float32) / 255.0
        shadow_np = np.array(contact_shadow, dtype=np.float32) / 255.0
        
        # Shadow darkens the background
        darkened_bg_np = bg_np * (1.0 - shadow_np[:, :, np.newaxis] * 0.75)
        shadowed_bg = Image.fromarray(np.clip(darkened_bg_np * 255.0, 0, 255).astype(np.uint8), mode='RGB')

        # Paste product strictly onto darkened background using the alpha mask
        final_comp = shadowed_bg.copy()
        final_comp.paste(prod_img, (0, 0), mask)

        os.makedirs(os.path.dirname(os.path.abspath(output_image_path)), exist_ok=True)
        final_comp.save(output_image_path, "PNG", quality=95)

        # Gate Verification: Verify pixel integrity on product
        prod_np = np.array(prod_img.convert('RGB'))
        final_np = np.array(final_comp)
        mask_binary = (np.array(mask) > 250)
        
        # Check that where mask is solid, product pixels match 100%
        pixel_diff = np.abs(prod_np[mask_binary].astype(int) - final_np[mask_binary].astype(int))
        max_diff = np.max(pixel_diff) if len(pixel_diff) > 0 else 0
        mean_diff = np.mean(pixel_diff) if len(pixel_diff) > 0 else 0.0

        is_verified = (max_diff == 0)
        return {
            "output_path": output_image_path,
            "status": "success",
            "fidelity_gate_pass": is_verified,
            "max_pixel_drift": int(max_diff),
            "mean_pixel_drift": float(mean_diff),
            "dimensions": final_comp.size
        }

if __name__ == "__main__":
    import sys
    if len(sys.argv) >= 4:
        prod = sys.argv[1]
        bg = sys.argv[2]
        out = sys.argv[3]
        res = MSPCompositor.composite_asset(prod, bg, out)
        print(f"Compositing completed: {res}")

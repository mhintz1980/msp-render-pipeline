# Myers-Seth Pumps (MSP) — Serverless CAD Render & Zero-Loss Compositing Pipeline

An agent-native, deterministic rendering and compositing pipeline built for Myers-Seth Pumps industrial dewatering equipment. Solves the generative AI "geometry drift" problem by keeping CAD assemblies and physical studio photos as the immutable source of mechanical truth, while offloading all heavy 3D rendering and ray-tracing to serverless cloud GPUs.

---

## Architecture Overview

```
                          ┌───────────────────────────┐
                          │   msp-render CLI Harness  │
                          │     (Agent Orchestrator)  │
                          └─────────────┬─────────────┘
                                        │
           ┌────────────────────────────┴────────────────────────────┐
           ▼                                                         ▼
[Track 1: Serverless Cloud Render]                    [Track 2: Zero-Loss Compositor]
Modal GPU Worker (NVIDIA L4 / A10G)                   Local CPU (Instant / Free)
• Headless Blender 4.2 LTS                            • Contact Shadow Penumbra Synthesis
• Ingests V2RL300-SAFE.glb / DD4SE.glb                • Directional Ambient Occlusion
• Calibrated PBR Powder-Coat (MSP / UR)               • Alpha Masking & Background Merging
• Standard Camera Positions (P1–P8)                   • Bit-Exact Product Pixel Gate Check
• Renders: Beauty + Mask + Depth Map                  • Generates 100% CAD-Faithful Assets
```

---

## 1. Quickstart & Installation

```bash
# 1. Install dependencies
pip install numpy pillow modal

# 2. Authenticate with Modal (gives $30/month free serverless compute)
modal setup

# 3. Verify CLI presets
python3 -m msp_render_cli presets
```

---

## 2. Standard Presets & Calibration

### Livery Profiles
* **`msp_standard_yellow`:** RAL 1023 Traffic Yellow (`#F7B500`, roughness 0.35, clearcoat 0.25) with Satin Black chassis frame (`#1B1B1B`).
* **`united_rentals_blue`:** Fleet Safety Blue (`#00529B`, roughness 0.32, clearcoat 0.30) with Satin Black containment base (`#141414`).
* **`sunbelt_green`:** Fleet Green (`#006B3F`) with Slate Frame.
* **`herc_rentals_white`:** Fleet White (`#F2F4F7`) with Safety Yellow accents.

### Camera Rig Presets (Calibrated to MSP Physical Studio Archives)
* **`P1_FRONT_ISO`:** Front 3/4 Isometric (Azimuth 45°, Elevation 14°, 50mm lens). Standard catalog hero angle.
* **`P2_FRONT_ELEVATION`:** Direct Front Head-On (Azimuth 0°, Elevation 4°, 65mm lens). Manifold & door alignment.
* **`P3_RIGHT_THREE_QUARTER`:** Right 3/4 Maintenance Door (Azimuth 65°, Elevation 12°, 50mm lens).
* **`P4_LEFT_THREE_QUARTER`:** Left 3/4 Discharge Manifold (Azimuth -65°, Elevation 12°, 50mm lens).
* **`P5_REAR_THREE_QUARTER`:** Rear 3/4 Radiator Exhaust (Azimuth 135°, Elevation 16°, 50mm lens).
* **`P6_SIDE_PROFILE`:** Orthogonal Side Profile (Azimuth 90°, Elevation 2°, 85mm telephoto).
* **`P7_LOW_HERO`:** Low-Angle Ground Perspective (Azimuth 35°, Elevation 4°, 35mm wide-angle).
* **`P8_OVERHEAD_PLAN`:** Overhead 45° Roof & Lifting Bail (Azimuth 45°, Elevation 45°, 50mm lens).

---

## 3. Workflow Commands

### Step 1: Create a Job Manifest
```bash
python3 -m msp_render_cli new-job \
  --job-id "rl300_hero_yellow" \
  --model "RL300_SAFE" \
  --cad "3D models/V2RL300-SAFE.glb" \
  --camera "P1_FRONT_ISO" \
  --livery "msp_standard_yellow" \
  --lighting "studio_dark" \
  -o "jobs/rl300_hero.json"
```

### Step 2: Validate Manifest Against Schema
```bash
python3 -m msp_render_cli validate jobs/rl300_hero.json
```

### Step 3: Dispatch to Serverless Cloud GPU (Modal)
```bash
python3 -m msp_render_cli dispatch-modal jobs/rl300_hero.json
```
*Dispatches headless Blender Cycles to an NVIDIA L4 GPU. Completes in ~30 seconds, cost <$0.01.*
*Outputs `beauty.png`, `mask.png`, and `depth.png` to `./output/rl300_hero_yellow/`.*

### Step 4: Zero-Loss Environment Compositing
```bash
python3 -m msp_render_cli composite \
  --product "./output/rl300_hero_yellow/beauty.png" \
  --background "Renderings/env_excavationPit-sunlit.png" \
  --output "./output/rl300_hero_yellow/final_excavation_pit.png" \
  --shadow-opacity 0.85
```
*Performs directional ground contact shadow generation and checks the Product Pixel Integrity Gate. If any machine pixel drifted, it flags it immediately.*

---

## 4. Acceptance Gates Verification

Run the automated test suite anytime:
```bash
python3 -m unittest tests/test_pipeline.py
```
* Verifies color space conversions (linear sRGB gamma).
* Verifies 3D spherical camera positioning for all 8 studio presets.
* Verifies schema validation and error reporting.
* Verifies zero-loss compositing (0 pixel drift on product silhouette).

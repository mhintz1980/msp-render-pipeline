"""Composite, verify, and encode a cloud frame sequence - the T-V2 probe.

Consumes a cloud_job_render run directory (cloud/frame-az*/beauty.png +
mask.png), composites every frame through MSPCompositor with the run's own
recorded overrides (request.json), applies the lens pass with a per-frame
seed, and measures what a still pipeline cannot see: whether the sequence
varies smoothly (docs/video-pipeline-brief.md section 7.4 statistics, run on
PRE-lens pixels so grain never pollutes motion measurements), whether every
frame passed the product-integrity gate, whether grain is reproducible, and
whether the encoded loop's decoded frames match the PNGs within a declared
lossy floor.

Not a sequencer: it processes what exists on disk and reports. Exit 0 means
every declared gate passed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np
from PIL import Image

from composite_worker import MSPCompositor

# Declared at probe time per the brief's rule: thresholds are recorded when
# set, never widened because a run missed them.
PSNR_FLOOR_DB = 35.0
NEIGHBOUR_OUTLIER_FACTOR = 3.0


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def load_run(run_dir):
    """The run's compositing settings: source manifest + recorded overrides."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("cloud_job_render",
                                                  ROOT / "scripts/cloud_job_render.py")
    dispatcher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(dispatcher)
    request = json.loads((run_dir / "request.json").read_text(encoding="utf-8"))
    manifest = json.loads((ROOT / "jobs" / (request["job_id"] + ".json")).read_text())
    dispatcher.apply_overrides(manifest, request.get("overrides", []))
    return request, manifest


def frame_scalars(composite_rgb, mask_l):
    """Coverage and interior luminance - the four scalars of section 7.4 (two
    of them live on the mask, two on the pixels)."""
    mask = np.array(mask_l) > 250
    luma = np.array(composite_rgb.convert("L"), dtype=np.float32)
    interior = luma[mask]
    return {"coverage": float(mask.mean()),
            "mean_luma": float(interior.mean()),
            "p95_luma": float(np.percentile(interior, 95))}


def frame_mae(a_rgb, b_rgb, mask_a, mask_b):
    """Mean absolute 8-bit difference over product pixels present in both."""
    both = (np.array(mask_a) > 250) & (np.array(mask_b) > 250)
    diff = np.abs(np.array(a_rgb, dtype=np.float32) - np.array(b_rgb, dtype=np.float32))
    return float(diff[both].mean())


def sequence_report(scalars, maes, digests, azimuths):
    """Section 7.4 sequence gates: smooth variation, bounded change, no
    duplicates, no gaps. Pure; unit-tested."""
    problems = []

    def max_second_diff(values):
        v = np.array(values, dtype=np.float64)
        return float(np.max(np.abs(np.diff(v, n=2)))) if len(v) > 2 else 0.0

    smooth = {"coverage": max_second_diff([s["coverage"] for s in scalars]),
              "mean_luma": max_second_diff([s["mean_luma"] for s in scalars]),
              "p95_luma": max_second_diff([s["p95_luma"] for s in scalars])}
    med = float(np.median(maes)) if maes else 0.0
    outliers = [i for i, mae in enumerate(maes)
                if med > 0 and mae > NEIGHBOUR_OUTLIER_FACTOR * med]
    if outliers:
        problems.append(f"FLICKER_OUTLIER_FRAMES: {outliers}")
    dupes = [i for i in range(1, len(digests)) if digests[i] == digests[i - 1]]
    if dupes:
        problems.append(f"DUPLICATE_CONSECUTIVE_FRAMES: {dupes}")
    steps = [round(b - a, 3) for a, b in zip(azimuths, azimuths[1:])]
    if steps and (abs(steps[0]) < 1e-6 or any(abs(s - steps[0]) > 1e-6 for s in steps)):
        problems.append(f"NON_UNIFORM_AZIMUTH_STEPS: {steps}")
    return {"max_abs_second_difference": smooth, "frame_mae_median": med,
            "frame_mae_max": float(np.max(maes)) if maes else 0.0,
            "outlier_frames": outliers, "problems": problems}


def psnr(a, b):
    mse = float(np.mean((np.array(a, dtype=np.float64) - np.array(b, dtype=np.float64)) ** 2))
    return float("inf") if mse == 0 else 10.0 * np.log10(255.0 ** 2 / mse)


def encoded_frame_count(video_path) -> int:
    """Frames actually present in the encoded file, via ffprobe."""
    def probe(ffprobe_args):
        result = subprocess.run(ffprobe_args, capture_output=True, text=True)
        try:
            return int(result.stdout.strip())
        except ValueError:
            return None

    count = probe(["ffprobe", "-v", "error", "-select_streams", "v:0",
                   "-show_entries", "stream=nb_frames",
                   "-of", "default=noprint_wrappers=1:nokey=1", str(video_path)])
    if count is None:
        # nb_frames is legitimately N/A for some containers; count then.
        count = probe(["ffprobe", "-v", "error", "-select_streams", "v:0",
                       "-count_frames", "-show_entries", "stream=nb_read_frames",
                       "-of", "default=noprint_wrappers=1:nokey=1", str(video_path)])
    if count is None:
        raise RuntimeError(f"FFPROBE_FRAME_COUNT_UNAVAILABLE: {video_path}")
    return count


def frame_azimuth(run_dir, frame_dir) -> float:
    """The frame's true azimuth from its own manifest, not its rounded label."""
    frame_name = frame_dir.name[len("frame-"):]
    manifest_path = Path(run_dir) / f"manifest-{frame_name}.json"
    if not manifest_path.is_file():
        # Older run directories predate per-frame manifests; the rounded
        # directory label is then the best available value.
        return float(frame_dir.name.split("az")[1])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    try:
        return float(manifest["camera"]["azimuth_deg"])
    except KeyError:
        raise RuntimeError(f"FRAME_AZIMUTH_UNAVAILABLE: {manifest_path}") from None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--lens-vignette", type=float, default=0.45)
    parser.add_argument("--lens-bloom", type=float, default=0.3)
    parser.add_argument("--lens-grain", type=float, default=2.2)
    parser.add_argument("--framerate", type=int, default=12)
    parser.add_argument("--no-encode", action="store_true")
    parser.add_argument("--expect-frames", type=int, default=None,
                        help="declare the intended frame count up front; a "
                             "short download or missing frame must not pass quietly")
    args = parser.parse_args()
    run_dir = args.run_dir.resolve()
    request, manifest = load_run(run_dir)
    compositing = {k: v for k, v in manifest["compositing"].items()
                   if k not in ("enabled", "background_plate")}
    plate = str(ROOT / manifest["compositing"]["background_plate"])

    # Sort on the true azimuth: the integer label collides above 360 frames.
    frames = sorted((run_dir / "cloud").glob("frame-az*/beauty.png"),
                    key=lambda p: frame_azimuth(run_dir, p.parent))
    if not frames:
        raise SystemExit("NO_FRAMES: no cloud/frame-az*/beauty.png under " + str(run_dir))

    results, scalars, maes, digests, azimuths = [], [], [], [], []
    pre_lens = []
    for index, beauty in enumerate(frames):
        frame_dir = beauty.parent
        azimuth = frame_azimuth(run_dir, frame_dir)
        azimuths.append(azimuth)
        pre_path = str(frame_dir / "composite-prelens.png")
        result = MSPCompositor.composite_asset(
            str(beauty), plate, pre_path,
            mask_image_path=str(frame_dir / "mask.png"), **compositing)
        results.append(result)
        if not result["fidelity_gate_pass"]:
            print(json.dumps({"status": "failed", "frame": azimuth,
                              "reason": "PRODUCT_INTEGRITY_GATE"}))
            return 1
        mask = Image.open(frame_dir / "mask.png").convert("L")
        rgb = Image.open(pre_path).convert("RGB")
        scalars.append(frame_scalars(rgb, mask))
        pre_lens.append(rgb)
        digests.append(sha(pre_path))
        lensed = MSPCompositor.apply_lens_pass(
            rgb, vignette=args.lens_vignette, bloom=args.lens_bloom,
            grain=args.lens_grain, frame_index=index)
        lensed.save(frame_dir / "composite-lens.png")

    for i in range(1, len(pre_lens)):
        maes.append(frame_mae(pre_lens[i], pre_lens[i - 1],
                              Image.open(frames[i].parent / "mask.png").convert("L"),
                              Image.open(frames[i - 1].parent / "mask.png").convert("L")))

    # Grain determinism, proven adversarially on the middle frame: a rerun
    # must reproduce the delivered bytes exactly.
    mid = len(frames) // 2
    mid_rgb = Image.open(frames[mid].parent / "composite-prelens.png").convert("RGB")
    MSPCompositor.apply_lens_pass(mid_rgb, vignette=args.lens_vignette,
                                  bloom=args.lens_bloom, grain=args.lens_grain,
                                  frame_index=mid).save(run_dir / "determinism-check.png")
    grain_deterministic = sha(run_dir / "determinism-check.png") == \
        sha(frames[mid].parent / "composite-lens.png")

    report = sequence_report(scalars, maes, digests, azimuths)
    report["frames"] = len(frames)
    if args.expect_frames is not None and args.expect_frames != len(frames):
        report["problems"].append(
            f"FRAME_COUNT_NOT_AS_DECLARED: found {len(frames)} expected {args.expect_frames}")
    report["fidelity_gate_all_pass"] = all(r["fidelity_gate_pass"] for r in results)
    report["grain_deterministic"] = grain_deterministic
    if not grain_deterministic:
        report["problems"].append("GRAIN_NOT_DETERMINISTIC")

    if not args.no_encode:
        concat = run_dir / "lens-frames"
        concat.mkdir(exist_ok=True)
        for index, beauty in enumerate(frames):
            (concat / f"f{index:03d}.png").write_bytes(
                (beauty.parent / "composite-lens.png").read_bytes())
        video = run_dir / "turntable-loop.mp4"
        encode = subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error",
             "-framerate", str(args.framerate), "-i", str(concat / "f%03d.png"),
             "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p",
             str(video)], capture_output=True, text=True)
        if encode.returncode:
            print(json.dumps({"status": "failed", "reason": "FFMPEG",
                              "stderr": encode.stderr[-500:]}))
            return 1
        # One pass through unique frames: looping is the player's job (owner
        # ruling 2026-09-20), so the encoded count must equal the source count.
        report["unique_frame_count"] = len(frames)
        try:
            encoded = encoded_frame_count(video)
        except (RuntimeError, OSError) as exc:
            # The encode already succeeded and is paid for; losing the frame
            # count must not discard the report's other measured gates.
            encoded = None
            report["encoded_frame_count"] = None
            report["problems"].append(f"ENCODED_FRAME_COUNT_UNAVAILABLE: {exc}")
        else:
            report["encoded_frame_count"] = encoded
        if encoded is not None and encoded != len(frames):
            report["problems"].append(
                f"ENCODED_FRAME_COUNT_MISMATCH: encoded {encoded} vs unique {len(frames)}")
        # Decode-back integrity on three sampled frames (section 7.5).
        decode = []
        for index in (0, len(frames) // 2, len(frames) - 1):
            out = run_dir / f"decode-f{index:03d}.png"
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(video),
                            "-vf", f"select=eq(n\\,{index})", "-vsync", "0",
                            str(out)], capture_output=True, check=True)
            decode.append(psnr(Image.open(out).convert("RGB"),
                               Image.open(concat / f"f{index:03d}.png").convert("RGB")))
        report["decode_psnr_db"] = [round(p, 2) for p in decode]
        report["decode_floor_db"] = PSNR_FLOOR_DB
        if min(decode) < PSNR_FLOOR_DB:
            report["problems"].append(f"DECODE_BELOW_FLOOR: {min(decode):.2f} dB")

    save = {"status": "passed" if not report["problems"] else "failed", **report}
    (run_dir / "sequence-report.json").write_text(
        json.dumps(save, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(save))
    return 0 if not report["problems"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

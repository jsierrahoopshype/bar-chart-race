"""Orchestrate: ingest → render slides → encode video + export PNGs."""

from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import Iterator

import numpy as np
from PIL import Image

from comparison.config import ComparisonConfig, PRESETS
from comparison.ingest import ComparisonData, load
from comparison.render import SlideRenderer
from comparison.encode import encode


def _split_categories(
    categories: list[str], per_slide: int
) -> list[list[str]]:
    """Split categories into groups for each slide."""
    groups: list[list[str]] = []
    for i in range(0, len(categories), per_slide):
        groups.append(categories[i : i + per_slide])
    return groups


def _crossfade_frames(
    slide_a_bytes: bytes,
    slide_b_bytes: bytes,
    n_frames: int,
    width: int,
    height: int,
) -> Iterator[bytes]:
    """Yield *n_frames* of crossfade transition between two slides."""
    arr_a = np.frombuffer(slide_a_bytes, dtype=np.uint8).reshape((height, width, 3)).astype(np.float32)
    arr_b = np.frombuffer(slide_b_bytes, dtype=np.uint8).reshape((height, width, 3)).astype(np.float32)
    for i in range(n_frames):
        t = (i + 1) / (n_frames + 1)
        blended = ((1 - t) * arr_a + t * arr_b).clip(0, 255).astype(np.uint8)
        yield blended.tobytes()


def run(cfg: ComparisonConfig) -> None:
    """Run the full comparison slideshow pipeline."""
    # Load data.
    print("Loading data...")
    data = load(cfg.input_path)
    print(f"  {len(data.players)} players, {len(data.categories)} categories")

    # Split into slides.
    slide_groups = _split_categories(data.categories, cfg.categories_per_slide)
    n_slides = len(slide_groups)
    print(f"  {n_slides} slides ({cfg.categories_per_slide} categories each)")

    # Generate all three presets.
    presets_to_render = [
        ("square", "output_comparison_square.mp4"),
        ("youtube", "output_comparison_youtube.mp4"),
        ("reels", "output_comparison_reels.mp4"),
    ]

    for preset_idx, (preset_name, output_name) in enumerate(presets_to_render):
        print(f"\n--- Generating {preset_name} ({preset_idx + 1}/{len(presets_to_render)}) ---")

        pcfg = ComparisonConfig(
            input_path=cfg.input_path,
            output=output_name,
            preset=preset_name,
            title=cfg.title,
            subtitle=cfg.subtitle,
            categories_per_slide=cfg.categories_per_slide,
            slide_duration=cfg.slide_duration,
            crossfade_duration=cfg.crossfade_duration,
            outro_hold=cfg.outro_hold,
            fps=cfg.fps,
            highlight_winner=cfg.highlight_winner,
            winner_color=cfg.winner_color,
            runner_up_color=cfg.runner_up_color,
            headshot_dir=cfg.headshot_dir,
            bg_image=cfg.bg_image,
            font_dir=cfg.font_dir,
            lowest_is_better=cfg.lowest_is_better,
        )
        preset = pcfg.get_preset()
        renderer = SlideRenderer(pcfg)

        # Pre-render all slides as RGB bytes.
        print(f"  Rendering {n_slides} slides at {preset.width}x{preset.height}...")
        slide_bytes: list[bytes] = []
        for i, group in enumerate(slide_groups):
            rgb = renderer.render_slide_rgb_bytes(data, group, i + 1, n_slides)
            slide_bytes.append(rgb)

        # Export PNGs (only for square preset to avoid tripling output).
        if preset_name == "square":
            png_dir = Path("output_slides")
            png_dir.mkdir(exist_ok=True)
            for i, group in enumerate(slide_groups):
                slide_img = renderer.render_slide(data, group, i + 1, n_slides)
                png_path = png_dir / f"slide_{i + 1:03d}.png"
                slide_img.save(str(png_path))
            print(f"  Exported {n_slides} PNGs to {png_dir}/")

        # Build frame sequence with crossfades.
        hold_frames = int(pcfg.slide_duration * pcfg.fps)
        fade_frames = max(1, int(pcfg.crossfade_duration * pcfg.fps))
        outro_frames = int(pcfg.outro_hold * pcfg.fps)

        total_frames = 0
        for i in range(n_slides):
            total_frames += hold_frames
            if i < n_slides - 1:
                total_frames += fade_frames
        total_frames += outro_frames

        def frame_gen() -> Iterator[bytes]:
            for i in range(n_slides):
                # Hold current slide.
                for _ in range(hold_frames):
                    yield slide_bytes[i]
                # Crossfade to next slide.
                if i < n_slides - 1:
                    yield from _crossfade_frames(
                        slide_bytes[i], slide_bytes[i + 1],
                        fade_frames, preset.width, preset.height,
                    )
            # Outro hold on last slide.
            if slide_bytes:
                for _ in range(outro_frames):
                    yield slide_bytes[-1]

        print(f"  Encoding {total_frames} frames to {pcfg.output}...")
        try:
            encode(
                frames=frame_gen(),
                total_frames=total_frames,
                preset=preset,
                output=pcfg.output,
                fps=pcfg.fps,
            )
            print(f"  ✓ {pcfg.output}")
        except RuntimeError as e:
            print(f"  ✗ Encoding failed: {e}")

    print("\nDone.")

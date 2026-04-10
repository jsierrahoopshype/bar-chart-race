"""Orchestrate: ingest → render conveyor belt frames → encode video + export PNGs."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Iterator

from comparison.config import ComparisonConfig, PRESETS
from comparison.ingest import load
from comparison.render import ConveyorRenderer
from comparison.encode import encode


def run(cfg: ComparisonConfig) -> None:
    """Run the full comparison conveyor belt pipeline."""
    print("Loading data...")
    data = load(cfg.input_path)
    print(f"  {len(data.players)} players, {len(data.categories)} categories")

    presets_to_render = [
        ("square", "output_comparison_square.mp4"),
        ("youtube", "output_comparison_youtube.mp4"),
        ("reels", "output_comparison_reels.mp4"),
    ]

    for pidx, (preset_name, output_name) in enumerate(presets_to_render):
        print(f"\n--- Generating {preset_name} ({pidx + 1}/{len(presets_to_render)}) ---")

        pcfg = ComparisonConfig(
            input_path=cfg.input_path,
            output=output_name,
            preset=preset_name,
            title=cfg.title,
            subtitle=cfg.subtitle,
            categories_per_slide=cfg.categories_per_slide,
            slide_duration=cfg.slide_duration,
            fps=cfg.fps,
            highlight_winner=cfg.highlight_winner,
            winner_color=cfg.winner_color,
            runner_up_color=cfg.runner_up_color,
            headshot_dir=cfg.headshot_dir,
            bg_image=cfg.bg_image,
            font_dir=cfg.font_dir,
            lowest_is_better=cfg.lowest_is_better,
        )

        renderer = ConveyorRenderer(pcfg, data)
        preset = pcfg.get_preset()
        timing = renderer.compute_timing()
        total_frames = timing["total_frames"]
        card_images = renderer._prerender_cards()

        print(f"  {len(card_images)} cards, {total_frames} frames "
              f"at {preset.width}x{preset.height}, {pcfg.fps}fps")

        # Export individual card PNGs (square preset only).
        if preset_name == "square":
            png_dir = Path("output_slides")
            png_dir.mkdir(exist_ok=True)
            for ci in range(len(renderer.cards)):
                card_png = renderer.render_card_png(ci)
                card_png.save(str(png_dir / f"card_{ci + 1:03d}.png"))
            print(f"  Exported {len(renderer.cards)} card PNGs to {png_dir}/")

        # Frame generator.
        def frame_gen(
            renderer=renderer, timing=timing, card_images=card_images,
            total=total_frames,
        ) -> Iterator[bytes]:
            for fi in range(total):
                yield renderer.render_frame_rgb_bytes(fi, timing, card_images)
                if fi % 30 == 0:
                    sys.stderr.write(f"\r  Rendering: {fi}/{total}")
                    sys.stderr.flush()
            sys.stderr.write(f"\r  Rendering: {total}/{total}\n")

        print(f"  Encoding to {pcfg.output}...")
        try:
            encode(
                frames=frame_gen(),
                total_frames=total_frames,
                preset=preset,
                output=pcfg.output,
                fps=pcfg.fps,
            )
            print(f"  Done: {pcfg.output}")
        except RuntimeError as e:
            print(f"  Encoding failed: {e}")

    print("\nDone.")

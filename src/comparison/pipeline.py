"""Orchestrate: ingest → render conveyor frames → encode video + export PNGs."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Iterator

from comparison.config import ComparisonConfig
from comparison.ingest import load
from comparison.render import ConveyorRenderer
from comparison.encode import encode


def run(cfg: ComparisonConfig) -> None:
    """Run the full comparison conveyor-belt pipeline."""
    print("Loading data...")
    data = load(cfg.input_path)
    print(f"  {len(data.players)} players, {len(data.categories)} categories")

    presets = [
        ("square", "output_comparison_square.mp4"),
        ("youtube", "output_comparison_youtube.mp4"),
        ("reels", "output_comparison_reels.mp4"),
    ]

    for pi, (preset_name, out_name) in enumerate(presets):
        print(f"\n--- {preset_name} ({pi+1}/{len(presets)}) ---")

        pcfg = ComparisonConfig(
            input_path=cfg.input_path, output=out_name, preset=preset_name,
            title=cfg.title, subtitle=cfg.subtitle,
            categories_per_slide=cfg.categories_per_slide,
            slide_duration=cfg.slide_duration, fps=cfg.fps,
            highlight_winner=cfg.highlight_winner,
            winner_color=cfg.winner_color, runner_up_color=cfg.runner_up_color,
            headshot_dir=cfg.headshot_dir, bg_image=cfg.bg_image,
            font_dir=cfg.font_dir, lowest_is_better=cfg.lowest_is_better,
        )

        renderer = ConveyorRenderer(pcfg, data)
        t = renderer.timing()
        total = t["total"]
        preset = pcfg.get_preset()

        print(f"  {len(renderer.card_images)} cards, {total} frames, "
              f"{preset.width}x{preset.height} @ {pcfg.fps}fps "
              f"({total / pcfg.fps:.1f}s)")

        # Export card PNGs (square only).
        if preset_name == "square":
            png_dir = Path("output_slides")
            png_dir.mkdir(exist_ok=True)
            for ci in range(len(renderer.card_images)):
                renderer.render_card_png(ci).save(str(png_dir / f"card_{ci+1:03d}.png"))
            print(f"  Exported {len(renderer.card_images)} PNGs → {png_dir}/")

        def gen(r=renderer, t=t, tot=total) -> Iterator[bytes]:
            for fi in range(tot):
                yield r.render_frame_bytes(fi, t)
                if fi % 30 == 0:
                    sys.stderr.write(f"\r  Frame {fi}/{tot}")
                    sys.stderr.flush()
            sys.stderr.write(f"\r  Frame {tot}/{tot}\n")

        print(f"  Encoding → {pcfg.output}")
        try:
            encode(frames=gen(), total_frames=total, preset=preset,
                   output=pcfg.output, fps=pcfg.fps)
            print(f"  Done: {pcfg.output}")
        except RuntimeError as e:
            print(f"  Encoding failed: {e}")

    print("\nDone.")

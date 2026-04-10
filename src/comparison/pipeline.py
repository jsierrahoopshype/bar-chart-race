"""Orchestrate: ingest → render conveyor frames → encode video + export PNGs."""

from __future__ import annotations

import copy
import sys
from pathlib import Path
from typing import Iterator

from comparison.config import ComparisonConfig
from comparison.ingest import ComparisonData, load
from comparison.render import ConveyorRenderer
from comparison.encode import encode


def _filter_data(data: ComparisonData, cfg: ComparisonConfig) -> ComparisonData:
    """Apply selected_players, selected_categories, categories_order filters."""
    players = data.players
    categories = data.categories
    values = data.values

    if cfg.selected_players:
        players = [p for p in players if p in cfg.selected_players]
    if cfg.selected_categories:
        categories = [c for c in categories if c in cfg.selected_categories]
    if cfg.categories_order:
        ordered = [c for c in cfg.categories_order if c in categories]
        remaining = [c for c in categories if c not in ordered]
        categories = ordered + remaining

    # Rebuild values for filtered players/categories.
    fv: dict[str, dict[str, float]] = {}
    for cat in categories:
        if cat in values:
            fv[cat] = {p: values[cat].get(p, 0.0) for p in players}
    return ComparisonData(players=players, categories=categories, values=fv)


def run(cfg: ComparisonConfig) -> None:
    """Run the full comparison conveyor-belt pipeline."""
    print("Loading data...")
    data = load(cfg.input_path)
    data = _filter_data(data, cfg)
    print(f"  {len(data.players)} players, {len(data.categories)} categories")

    presets = [
        ("square", "output_comparison_square.mp4"),
        ("youtube", "output_comparison_youtube.mp4"),
        ("reels", "output_comparison_reels.mp4"),
    ]

    for pi, (preset_name, out_name) in enumerate(presets):
        print(f"\n--- {preset_name} ({pi+1}/{len(presets)}) ---")

        pcfg = copy.copy(cfg)
        pcfg.output = out_name
        pcfg.preset = preset_name

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


def run_single_preset(cfg: ComparisonConfig, data: ComparisonData) -> None:
    """Run pipeline for a single preset (used by server preview)."""
    renderer = ConveyorRenderer(cfg, data)
    t = renderer.timing()
    total = t["total"]
    preset = cfg.get_preset()

    def gen() -> Iterator[bytes]:
        for fi in range(total):
            yield renderer.render_frame_bytes(fi, t)

    encode(frames=gen(), total_frames=total, preset=preset,
           output=cfg.output, fps=cfg.fps)

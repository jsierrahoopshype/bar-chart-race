"""CLI entry point for the comparison slideshow tool."""

from __future__ import annotations

import argparse
import sys

from comparison.config import ComparisonConfig
from comparison.pipeline import run


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="comparison",
        description="Generate a player comparison slideshow video + PNG slides.",
    )
    parser.add_argument("--input", required=True, dest="input_path",
                        help="Path to CSV or Excel file with comparison data.")
    parser.add_argument("--output", default="comparison.mp4",
                        help="Output video filename (default: comparison.mp4).")
    parser.add_argument("--title", default="", help="Title text shown on every slide.")
    parser.add_argument("--subtitle", default="", help="Subtitle text.")
    parser.add_argument("--categories-per-slide", type=int, default=3,
                        help="Number of stat rows per slide (default: 3).")
    parser.add_argument("--slide-duration", type=float, default=3.0,
                        help="Seconds each slide is shown (default: 3.0).")
    parser.add_argument("--fps", type=int, default=30,
                        help="Frames per second (default: 30).")
    parser.add_argument("--preset", default="square",
                        choices=["square", "youtube", "reels"],
                        help="Preview preset (all three are always generated).")
    parser.add_argument("--headshot-dir", default="assets/headshots",
                        help="Directory containing player headshot images.")
    parser.add_argument("--bg-image", default="assets/backgrounds/mesh3.jpg",
                        help="Background image path.")
    parser.add_argument("--winner-color", default="#CC0000",
                        help="Hex color for winner cell (default: red).")
    parser.add_argument("--runner-up-color", default="#DAA520",
                        help="Hex color for runner-up cell (default: gold).")
    parser.add_argument("--no-highlight", action="store_true",
                        help="Disable winner/runner-up highlighting.")
    parser.add_argument("--lowest-is-better", nargs="*", default=[],
                        help="Category names where lower is better (e.g., Turnovers).")
    parser.add_argument("--comparison-theme", default="dark",
                        choices=["dark", "cream-serif"],
                        help="Visual theme (default: dark).")

    args = parser.parse_args(argv)

    cfg = ComparisonConfig(
        input_path=args.input_path,
        output=args.output,
        preset=args.preset,
        title=args.title,
        subtitle=args.subtitle,
        categories_per_slide=args.categories_per_slide,
        slide_duration=args.slide_duration,
        fps=args.fps,
        highlight_winner=not args.no_highlight,
        winner_color=args.winner_color,
        runner_up_color=args.runner_up_color,
        headshot_dir=args.headshot_dir,
        bg_image=args.bg_image,
        lowest_is_better=args.lowest_is_better or [],
        comparison_theme=args.comparison_theme,
    )

    run(cfg)


if __name__ == "__main__":
    main()

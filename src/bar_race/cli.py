"""Argparse CLI for bar-chart-race."""

from __future__ import annotations

import argparse
import sys

from bar_race.config import Config, PRESETS
from bar_race.pipeline import run
from bar_race.themes import list_themes


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="bar-chart-race",
        description="Generate animated bar-chart-race MP4 videos from NBA stats data.",
    )

    # --- config file -------------------------------------------------------
    p.add_argument(
        "--config", "-c",
        metavar="YAML",
        help="Path to a YAML config file. CLI flags override file values.",
    )

    # --- data source -------------------------------------------------------
    src = p.add_argument_group("data source")
    src.add_argument("--input", "-i", dest="input_path", help="Excel or CSV file path.")
    src.add_argument("--gsheet-url", dest="gsheet_url", help="Public Google Sheets URL.")
    src.add_argument("--sheet-name", dest="sheet_name", help="Sheet/tab name (Excel).")
    src.add_argument("--stat-column", dest="stat_column", help="Column name for the stat value (long format).")

    # --- date filtering ----------------------------------------------------
    dt = p.add_argument_group("date filtering")
    dt.add_argument("--date-start", dest="date_start", help="Start date filter (inclusive).")
    dt.add_argument("--date-end", dest="date_end", help="End date filter (inclusive).")

    # --- output ------------------------------------------------------------
    out = p.add_argument_group("output")
    out.add_argument("--output", "-o", default=None, help="Output file path (default: output.mp4).")
    out.add_argument(
        "--preset", "-p",
        choices=list(PRESETS.keys()),
        default=None,
        help="Video resolution preset.",
    )

    # --- video params ------------------------------------------------------
    vid = p.add_argument_group("video parameters")
    vid.add_argument("--fps", type=int, default=None)
    vid.add_argument("--duration", dest="duration_sec", type=float, default=None, help="Body duration in seconds.")
    vid.add_argument("--bitrate", default=None, help="Target bitrate, e.g. 12M.")
    vid.add_argument("--top-n", dest="top_n", type=int, default=None, help="Number of bars to show.")

    # --- titles ------------------------------------------------------------
    txt = p.add_argument_group("titles & branding")
    txt.add_argument("--title", default=None)
    txt.add_argument("--subtitle", default=None)
    txt.add_argument("--watermark", default=None)

    # --- theme -------------------------------------------------------------
    theme_grp = p.add_argument_group("theme")
    theme_grp.add_argument(
        "--theme", "-t",
        default=None,
        help="Visual theme slug (e.g. espn-broadcast, midnight-premium).",
    )
    theme_grp.add_argument(
        "--list-themes",
        action="store_true",
        default=False,
        help="Print all available themes and exit.",
    )

    # --- visual tweaks -----------------------------------------------------
    vis = p.add_argument_group("visual tweaks")
    vis.add_argument("--bg-gradient", dest="bg_gradient", nargs=2, metavar=("C1", "C2"), default=None)
    vis.add_argument("--no-team-colors", dest="use_team_colors", action="store_false", default=None)
    vis.add_argument("--no-vignette", dest="vignette", action="store_false", default=None)
    vis.add_argument("--no-noise", dest="noise", action="store_false", default=None)
    vis.add_argument("--no-leader-glow", dest="leader_glow", action="store_false", default=None)
    vis.add_argument("--no-rounded-bars", dest="rounded_bars", action="store_false", default=None)
    vis.add_argument("--no-bar-shadow", dest="bar_shadow", action="store_false", default=None)

    # --- assets ------------------------------------------------------------
    assets = p.add_argument_group("assets")
    assets.add_argument("--headshot-dir", dest="headshot_dir", default=None)
    assets.add_argument("--logo-dir", dest="logo_dir", default=None)

    # --- axis --------------------------------------------------------------
    p.add_argument("--axis-mode", dest="axis_mode", choices=["auto", "locked"], default=None)

    # --- fonts -------------------------------------------------------------
    fonts = p.add_argument_group("fonts")
    fonts.add_argument("--font-bold", dest="font_bold", default=None)
    fonts.add_argument("--font-medium", dest="font_medium", default=None)
    fonts.add_argument("--font-regular", dest="font_regular", default=None)
    fonts.add_argument("--font-light", dest="font_light", default=None)

    # --- intro / outro -----------------------------------------------------
    hold = p.add_argument_group("intro / outro")
    hold.add_argument("--intro-hold", dest="intro_hold_sec", type=float, default=None)
    hold.add_argument("--outro-hold", dest="outro_hold_sec", type=float, default=None)

    return p


def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)

    # --list-themes: print and exit.
    if args.list_themes:
        print(f"\nAvailable themes:\n")
        print(list_themes())
        print()
        sys.exit(0)

    # Start from YAML config if provided, else defaults.
    if args.config:
        cfg = Config.from_yaml(args.config)
    else:
        cfg = Config()

    # Override with any CLI flags that were explicitly set.
    cli_vals = vars(args)
    for key, val in cli_vals.items():
        if key in ("config", "list_themes"):
            continue
        if val is None:
            continue
        if key == "bg_gradient":
            val = tuple(val)
        setattr(cfg, key, val)

    # Validate that we have a data source.
    if not cfg.input_path and not cfg.gsheet_url:
        parser.error("Provide --input or --gsheet-url.")

    run(cfg)

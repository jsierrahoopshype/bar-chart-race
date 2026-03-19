"""Download NBA team logos for use in bar-chart-race renders.

Source: NBA CDN

Usage:
    python scripts/fetch_team_logos.py
    python scripts/fetch_team_logos.py --teams LAL GSW BOS
    python scripts/fetch_team_logos.py --force
"""

from __future__ import annotations

import argparse
import io
import time
from pathlib import Path

import requests
from PIL import Image

# ---------------------------------------------------------------------------
# Team abbreviation → NBA team ID mapping (all 30 teams)
# ---------------------------------------------------------------------------

TEAM_IDS: dict[str, int] = {
    "ATL": 1610612737,
    "BOS": 1610612738,
    "BKN": 1610612751,
    "CHA": 1610612766,
    "CHI": 1610612741,
    "CLE": 1610612739,
    "DAL": 1610612742,
    "DEN": 1610612743,
    "DET": 1610612765,
    "GSW": 1610612744,
    "HOU": 1610612745,
    "IND": 1610612754,
    "LAC": 1610612746,
    "LAL": 1610612747,
    "MEM": 1610612763,
    "MIA": 1610612748,
    "MIL": 1610612749,
    "MIN": 1610612750,
    "NOP": 1610612740,
    "NYK": 1610612752,
    "OKC": 1610612760,
    "ORL": 1610612753,
    "PHI": 1610612755,
    "PHX": 1610612756,
    "POR": 1610612757,
    "SAC": 1610612758,
    "SAS": 1610612759,
    "TOR": 1610612761,
    "UTA": 1610612762,
    "WAS": 1610612764,
}

# ESPN uses slightly different abbreviations for some teams.
ESPN_ABBR_MAP: dict[str, str] = {
    "BKN": "bkn",
    "CHA": "cha",
    "NOP": "no",
    "NYK": "ny",
    "PHX": "phx",
    "SAS": "sa",
    "GSW": "gs",
}

ESPN_LOGO_TEMPLATE = (
    "https://a.espncdn.com/combiner/i"
    "?img=/i/teamlogos/nba/500/{abbr_lower}.png&w=256&h=256"
)
NBA_LOGO_TEMPLATE = (
    "https://cdn.nba.com/logos/nba/{team_id}/global/L/logo.png"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.nba.com",
}

OUTPUT_DIR = Path("assets/logos")
TARGET_SIZE = (256, 256)


# ---------------------------------------------------------------------------
# Download + process
# ---------------------------------------------------------------------------


def _try_url(url: str) -> bytes | None:
    """GET *url* and return content bytes, or None on failure."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code == 200 and len(resp.content) > 500:
            return resp.content
    except requests.RequestException:
        pass
    return None


def download_logo(
    abbr: str,
    team_id: int,
    output_dir: Path,
    force: bool = False,
) -> bool:
    """Download and save a team logo. Return True on success."""
    out_path = output_dir / f"{abbr}.png"
    if out_path.exists() and not force:
        print(f"  SKIP  {abbr} (already exists)")
        return True

    # Try ESPN CDN first (more reliable).
    espn_abbr = ESPN_ABBR_MAP.get(abbr, abbr.lower())
    espn_url = ESPN_LOGO_TEMPLATE.format(abbr_lower=espn_abbr)
    raw = _try_url(espn_url)
    source = "ESPN CDN"

    # Fallback to NBA CDN.
    if raw is None:
        nba_url = NBA_LOGO_TEMPLATE.format(team_id=team_id)
        raw = _try_url(nba_url)
        source = "NBA CDN"

    if raw is None:
        print(f"  MISS  {abbr}")
        return False

    # Open, resize, preserve transparency.
    img = Image.open(io.BytesIO(raw)).convert("RGBA")
    img = img.resize(TARGET_SIZE, Image.LANCZOS)
    img.save(str(out_path), "PNG")
    print(f"  OK    {abbr} (ID {team_id}) — from {source}")
    return True


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download NBA team logos.",
    )
    parser.add_argument(
        "--teams",
        nargs="*",
        metavar="ABBR",
        help="Team abbreviations to download (default: all 30).",
    )
    parser.add_argument(
        "--force", "-f",
        action="store_true",
        help="Re-download even if file already exists.",
    )
    parser.add_argument(
        "--output-dir", "-o",
        default=str(OUTPUT_DIR),
        help=f"Output directory (default: {OUTPUT_DIR}).",
    )

    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    teams = args.teams if args.teams else list(TEAM_IDS.keys())
    # Validate abbreviations.
    for t in teams:
        if t.upper() not in TEAM_IDS:
            parser.error(f"Unknown team abbreviation: {t}")

    print(f"Downloading logos for {len(teams)} teams ...\n")

    found = 0
    missing: list[str] = []

    for i, abbr in enumerate(teams):
        abbr = abbr.upper()
        ok = download_logo(abbr, TEAM_IDS[abbr], output_dir, force=args.force)
        if ok:
            found += 1
        else:
            missing.append(abbr)

        if i < len(teams) - 1:
            time.sleep(1)

    print(f"\n{'='*50}")
    print(f"  Found:   {found}")
    print(f"  Missing: {len(missing)}")
    if missing:
        print(f"  Missing: {', '.join(missing)}")
    print(f"  Output:  {output_dir.resolve()}")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()

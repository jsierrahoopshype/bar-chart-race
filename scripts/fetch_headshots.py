"""Download NBA player headshots for use in bar-chart-race renders.

Sources (tried in order):
1. GitHub repo with AI background-removed PNGs
2. NBA CDN fallback

Usage:
    python scripts/fetch_headshots.py --input sample_data/nba_points_2024_long.xlsx
    python scripts/fetch_headshots.py "Shai Gilgeous-Alexander" "LeBron James"
    python scripts/fetch_headshots.py --input data.xlsx --force
"""

from __future__ import annotations

import argparse
import io
import sys
import time
from pathlib import Path

import pandas as pd
import requests
from PIL import Image

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

GITHUB_BASE = (
    "https://raw.githubusercontent.com/"
    "jsierrahoopshype/nba-headshots/main/"
)
NBA_CDN_TEMPLATE = (
    "https://cdn.nba.com/headshots/nba/latest/1040x760/{player_id}.png"
)
NBA_PLAYERS_URL = (
    "https://stats.nba.com/stats/commonallplayers"
    "?LeagueID=00&Season=2024-25&IsOnlyCurrentSeason=1"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.nba.com",
    "Origin": "https://www.nba.com",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
}

OUTPUT_DIR = Path("assets/headshots")
TARGET_SIZE = (256, 256)

# ---------------------------------------------------------------------------
# Hardcoded player ID fallback for common players
# ---------------------------------------------------------------------------

# This avoids depending on the NBA stats API, which is frequently
# rate-limited or blocks automated requests.  IDs sourced from nba.com.
KNOWN_PLAYER_IDS: dict[str, int] = {
    "Shai Gilgeous-Alexander": 1628983,
    "Luka Doncic": 1629029,
    "Giannis Antetokounmpo": 203507,
    "Jayson Tatum": 1628369,
    "Anthony Edwards": 1630162,
    "Donovan Mitchell": 1628378,
    "Trae Young": 1629027,
    "Kevin Durant": 201142,
    "Karl-Anthony Towns": 1626157,
    "Jaylen Brown": 1627759,
    "LeBron James": 2544,
    "Nikola Jokic": 203999,
    "De'Aaron Fox": 1628368,
    "Anthony Davis": 203076,
    "Devin Booker": 1626164,
    "Stephen Curry": 201939,
    "James Harden": 201935,
    "Joel Embiid": 203954,
    "Damian Lillard": 203081,
    "Kyrie Irving": 202681,
    "Kawhi Leonard": 202695,
    "Paul George": 202331,
    "Jimmy Butler": 202710,
    "Bam Adebayo": 1628389,
    "Domantas Sabonis": 1627734,
    "Tyrese Haliburton": 1630169,
    "Jalen Brunson": 1628973,
    "Tyrese Maxey": 1630178,
    "Paolo Banchero": 1631094,
    "Victor Wembanyama": 1641705,
    "Chet Holmgren": 1631096,
    "Ja Morant": 1629630,
    "Zion Williamson": 1629627,
    "Brandon Ingram": 1627742,
    "DeMar DeRozan": 201942,
    "Lauri Markkanen": 1628374,
    "Tyler Herro": 1629639,
    "Scottie Barnes": 1630567,
    "Franz Wagner": 1630532,
    "Alperen Sengun": 1630578,
}

# ---------------------------------------------------------------------------
# NBA API: player name → player ID mapping
# ---------------------------------------------------------------------------


def fetch_player_roster() -> dict[str, int]:
    """Return a mapping of player name → NBA player ID.

    Starts from the hardcoded lookup, then tries the NBA stats API
    to fill in any gaps.  If the API is unavailable the hardcoded
    mapping is returned as-is.
    """
    # Seed with known IDs.
    roster: dict[str, int] = {}
    for name, pid in KNOWN_PLAYER_IDS.items():
        roster[name] = pid
        roster[name.lower()] = pid

    # Try the NBA API for a full roster (may time out / be blocked).
    print("Fetching NBA player roster from stats.nba.com ...")
    for attempt in range(3):
        try:
            resp = requests.get(
                NBA_PLAYERS_URL, headers=HEADERS, timeout=45,
            )
            resp.raise_for_status()
            data = resp.json()

            headers_row = data["resultSets"][0]["headers"]
            rows = data["resultSets"][0]["rowSet"]

            id_idx = headers_row.index("PERSON_ID")
            name_idx = headers_row.index("DISPLAY_FIRST_LAST")

            for row in rows:
                name = str(row[name_idx]).strip()
                pid = int(row[id_idx])
                roster[name.lower()] = pid
                roster[name] = pid

            print(f"  API returned {len(rows)} players.")
            return roster

        except (requests.RequestException, KeyError, ValueError) as exc:
            wait = 3 * (attempt + 1)
            print(f"  Attempt {attempt + 1}/3 failed: {exc}")
            if attempt < 2:
                print(f"  Retrying in {wait}s ...")
                time.sleep(wait)

    print("  NBA API unavailable — falling back to hardcoded player IDs.")
    return roster


# ---------------------------------------------------------------------------
# Image processing
# ---------------------------------------------------------------------------


def _crop_to_face(img: Image.Image) -> Image.Image:
    """Crop image to the upper-center region where the face typically is.

    NBA headshots are roughly upper-body; we take the top ~75 % and
    centre-crop to a square.
    """
    w, h = img.size

    # Take top 75 % of image (face area).
    crop_bottom = int(h * 0.75)
    img = img.crop((0, 0, w, crop_bottom))

    # Centre-crop to square.
    w, h = img.size
    side = min(w, h)
    left = (w - side) // 2
    top = 0
    img = img.crop((left, top, left + side, top + side))

    return img


def _process_image(raw_bytes: bytes) -> Image.Image:
    """Open, crop, and resize a headshot image to TARGET_SIZE."""
    img = Image.open(io.BytesIO(raw_bytes)).convert("RGBA")
    img = _crop_to_face(img)
    img = img.resize(TARGET_SIZE, Image.LANCZOS)
    return img


# ---------------------------------------------------------------------------
# Download logic
# ---------------------------------------------------------------------------


def _try_github(player_id: int) -> bytes | None:
    """Try downloading from the GitHub repo (background-removed PNGs)."""
    url = f"{GITHUB_BASE}{player_id}.png"
    try:
        resp = requests.get(url, timeout=15)
        if resp.status_code == 200 and len(resp.content) > 1000:
            return resp.content
    except requests.RequestException:
        pass
    return None


def _try_nba_cdn(player_id: int) -> bytes | None:
    """Fallback: download from NBA CDN."""
    url = NBA_CDN_TEMPLATE.format(player_id=player_id)
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code == 200 and len(resp.content) > 1000:
            return resp.content
    except requests.RequestException:
        pass
    return None


def download_headshot(
    name: str,
    player_id: int,
    output_dir: Path,
    force: bool = False,
) -> bool:
    """Download and save a headshot for *name*. Return True on success."""
    out_path = output_dir / f"{name}.png"
    if out_path.exists() and not force:
        print(f"  SKIP  {name} (already exists)")
        return True

    # Try GitHub first (background-removed).
    raw = _try_github(player_id)
    source = "GitHub"

    if raw is None:
        raw = _try_nba_cdn(player_id)
        source = "NBA CDN"

    if raw is None:
        print(f"  MISS  {name} (ID {player_id}) — not found on either source")
        return False

    img = _process_image(raw)
    img.save(str(out_path), "PNG")
    print(f"  OK    {name} (ID {player_id}) — from {source}")
    return True


# ---------------------------------------------------------------------------
# Player list from input
# ---------------------------------------------------------------------------


def players_from_excel(path: str) -> list[str]:
    """Read unique player names from an Excel/CSV file."""
    p = Path(path)
    if p.suffix.lower() in (".xlsx", ".xls"):
        df = pd.read_excel(p, engine="openpyxl")
    else:
        df = pd.read_csv(p)

    # Find the player column.
    for col in df.columns:
        if col.strip().lower() in ("player", "name", "athlete", "player_name"):
            names = df[col].dropna().astype(str).str.strip().unique().tolist()
            print(f"Found {len(names)} unique players in column '{col}'")
            return names

    raise ValueError(
        f"No player column found in {path}. "
        f"Columns: {list(df.columns)}"
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download NBA player headshots.",
    )
    parser.add_argument(
        "players",
        nargs="*",
        help="Player names to download (e.g. 'LeBron James').",
    )
    parser.add_argument(
        "--input", "-i",
        dest="input_path",
        help="Excel/CSV file to read player names from.",
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

    # Collect player names.
    names: list[str] = list(args.players) if args.players else []
    if args.input_path:
        names.extend(players_from_excel(args.input_path))
    # Deduplicate while preserving order.
    seen: set[str] = set()
    unique: list[str] = []
    for n in names:
        if n not in seen:
            seen.add(n)
            unique.append(n)
    names = unique

    if not names:
        parser.error("Provide player names as arguments or via --input.")

    print(f"\nWill fetch headshots for {len(names)} players.\n")

    # Build name → ID mapping from NBA API.
    roster = fetch_player_roster()
    time.sleep(1)

    found = 0
    skipped = 0
    missing: list[str] = []

    for i, name in enumerate(names):
        pid = roster.get(name) or roster.get(name.lower())
        if pid is None:
            print(f"  ???   {name} — not found in NBA roster")
            missing.append(name)
            continue

        ok = download_headshot(name, pid, output_dir, force=args.force)
        if ok:
            found += 1
        else:
            missing.append(name)

        # Rate limiting between downloads.
        if i < len(names) - 1:
            time.sleep(1.5)

    # Summary.
    print(f"\n{'='*50}")
    print(f"  Found:   {found}")
    print(f"  Missing: {len(missing)}")
    if missing:
        print(f"  Missing players: {', '.join(missing)}")
    print(f"  Output:  {output_dir.resolve()}")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()

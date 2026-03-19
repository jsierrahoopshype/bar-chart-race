"""Download NBA player headshots for use in bar-chart-race renders.

Sources (tried in order):
1. GitHub repo with AI background-removed PNGs (players/headshots/face/)
2. NBA CDN fallback

Usage:
    python scripts/fetch_headshots.py --from-repo
    python scripts/fetch_headshots.py --input sample_data/nba_points_2024_long.xlsx
    python scripts/fetch_headshots.py "Shai Gilgeous-Alexander" "LeBron James"
    python scripts/fetch_headshots.py --input data.xlsx --force
"""

from __future__ import annotations

import argparse
import io
import re
import sys
import time
from pathlib import Path

import pandas as pd
import requests
from PIL import Image

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

GITHUB_REPO = "jsierrahoopshype/nba-headshots"
GITHUB_RAW_BASE = (
    f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/"
)
GITHUB_TREE_API = (
    f"https://api.github.com/repos/{GITHUB_REPO}/git/trees/main?recursive=1"
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
# Hardcoded player ID → display name mapping
# ---------------------------------------------------------------------------

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

# Reverse lookup: ID → display name.
_ID_TO_NAME: dict[int, str] = {v: k for k, v in KNOWN_PLAYER_IDS.items()}

# ---------------------------------------------------------------------------
# Slug → display name conversion
# ---------------------------------------------------------------------------

# Special-case overrides where the slug doesn't titlecase correctly.
_SLUG_OVERRIDES: dict[str, str] = {
    "lebron-james": "LeBron James",
    "demar-derozan": "DeMar DeRozan",
    "de-aaron-fox": "De'Aaron Fox",
    "deaaron-fox": "De'Aaron Fox",
    "karl-anthony-towns": "Karl-Anthony Towns",
    "shai-gilgeous-alexander": "Shai Gilgeous-Alexander",
    "cj-mccollum": "CJ McCollum",
    "og-anunoby": "OG Anunoby",
    "rj-barrett": "RJ Barrett",
    "pj-washington": "PJ Washington",
    "tj-mcconnell": "TJ McConnell",
    "tj-warren": "TJ Warren",
    "jt-thor": "JT Thor",
    "aj-griffin": "AJ Griffin",
    "giannis-antetokounmpo": "Giannis Antetokounmpo",
    "luka-doncic": "Luka Doncic",
    "nikola-jokic": "Nikola Jokic",
    "nikola-vucevic": "Nikola Vucevic",
    "bogdan-bogdanovic": "Bogdan Bogdanovic",
    "bojan-bogdanovic": "Bojan Bogdanovic",
    "jonas-valanciunas": "Jonas Valanciunas",
    "kristaps-porzingis": "Kristaps Porzingis",
    "domantas-sabonis": "Domantas Sabonis",
    "alperen-sengun": "Alperen Sengun",
    "victor-wembanyama": "Victor Wembanyama",
    "jaime-jaquez-jr": "Jaime Jaquez Jr.",
    "jabari-smith-jr": "Jabari Smith Jr.",
    "jaren-jackson-jr": "Jaren Jackson Jr.",
    "larry-nance-jr": "Larry Nance Jr.",
    "gary-trent-jr": "Gary Trent Jr.",
    "wendell-carter-jr": "Wendell Carter Jr.",
    "tim-hardaway-jr": "Tim Hardaway Jr.",
    "kelly-oubre-jr": "Kelly Oubre Jr.",
    "marcus-morris-sr": "Marcus Morris Sr.",
    "derrick-jones-jr": "Derrick Jones Jr.",
    "kobe-bryant": "Kobe Bryant",
    "michael-jordan": "Michael Jordan",
    "shaquille-oneal": "Shaquille O'Neal",
    "charles-barkley": "Charles Barkley",
}


def _slug_to_display_name(slug: str) -> str:
    """Convert a filename slug like ``lebron-james`` to ``LeBron James``.

    Uses overrides for names that don't titlecase correctly, then falls
    back to simple title-casing of each hyphen-separated part.
    """
    if slug in _SLUG_OVERRIDES:
        return _SLUG_OVERRIDES[slug]
    # General case: title-case each word.
    parts = slug.split("-")
    return " ".join(p.capitalize() for p in parts)


def _parse_repo_filename(filename: str) -> tuple[int, str]:
    """Parse ``{player_id}-{slug}.png`` → ``(player_id, slug)``.

    Returns (player_id, slug) where slug is e.g. ``lebron-james``.
    """
    stem = filename.removesuffix(".png")
    # Split on first hyphen group — ID is pure digits at the start.
    m = re.match(r"^(\d+)-(.+)$", stem)
    if not m:
        raise ValueError(f"Cannot parse filename: {filename}")
    return int(m.group(1)), m.group(2)


# ---------------------------------------------------------------------------
# NBA API: player ID ↔ name mapping
# ---------------------------------------------------------------------------


def fetch_player_roster() -> dict[str, int]:
    """Return a mapping of player name → NBA player ID.

    Starts from the hardcoded lookup, then tries the NBA stats API
    to fill in any gaps.
    """
    roster: dict[str, int] = {}
    for name, pid in KNOWN_PLAYER_IDS.items():
        roster[name] = pid
        roster[name.lower()] = pid

    print("Fetching NBA player roster from stats.nba.com ...")
    for attempt in range(2):
        try:
            resp = requests.get(
                NBA_PLAYERS_URL, headers=HEADERS, timeout=20,
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
                _ID_TO_NAME.setdefault(pid, name)

            print(f"  API returned {len(rows)} players.")
            return roster

        except (requests.RequestException, KeyError, ValueError) as exc:
            print(f"  Attempt {attempt + 1}/2 failed: {exc}")
            if attempt < 1:
                time.sleep(3)

    print("  NBA API unavailable — using hardcoded player IDs only.")
    return roster


# ---------------------------------------------------------------------------
# Image processing
# ---------------------------------------------------------------------------


def _process_image(raw_bytes: bytes, crop: bool = True) -> Image.Image:
    """Open, optionally crop, and resize a headshot image to TARGET_SIZE."""
    img = Image.open(io.BytesIO(raw_bytes)).convert("RGBA")
    if crop:
        w, h = img.size
        # Take top 75 % of image (face area), then centre-crop to square.
        crop_bottom = int(h * 0.75)
        img = img.crop((0, 0, w, crop_bottom))
        w, h = img.size
        side = min(w, h)
        left = (w - side) // 2
        img = img.crop((left, 0, left + side, side))
    img = img.resize(TARGET_SIZE, Image.LANCZOS)
    return img


# ---------------------------------------------------------------------------
# Download logic (per-player mode)
# ---------------------------------------------------------------------------


def _try_github(player_id: int) -> bytes | None:
    """Try downloading from the GitHub repo (background-removed PNGs)."""
    url = f"{GITHUB_RAW_BASE}players/headshots/face/{player_id}.png"
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

    raw = _try_github(player_id)
    source = "GitHub"

    if raw is None:
        raw = _try_nba_cdn(player_id)
        source = "NBA CDN"

    if raw is None:
        print(f"  MISS  {name} (ID {player_id})")
        return False

    # Repo images are already face-cropped; NBA CDN images need cropping.
    img = _process_image(raw, crop=(source == "NBA CDN"))
    img.save(str(out_path), "PNG")
    print(f"  OK    {name} (ID {player_id}) — from {source}")
    return True


# ---------------------------------------------------------------------------
# --from-repo mode: bulk download from GitHub repo
# ---------------------------------------------------------------------------


def _list_repo_headshots() -> list[str]:
    """Return list of filenames in ``players/headshots/face/`` via Git tree API."""
    print("Fetching file list from GitHub repo ...")
    resp = requests.get(GITHUB_TREE_API, timeout=30)
    resp.raise_for_status()
    tree = resp.json()["tree"]

    prefix = "players/headshots/face/"
    files = [
        t["path"].split("/")[-1]
        for t in tree
        if t["path"].startswith(prefix) and t["path"].endswith(".png")
    ]
    print(f"  Found {len(files)} headshot PNGs in repo.")
    return files


def run_from_repo(output_dir: Path, force: bool = False) -> None:
    """Bulk-download all headshots from the GitHub repo."""
    output_dir.mkdir(parents=True, exist_ok=True)
    unmapped_dir = output_dir / "_unmapped"
    unmapped_dir.mkdir(parents=True, exist_ok=True)

    files = _list_repo_headshots()

    # Try to get the NBA API roster for better name mapping.
    fetch_player_roster()

    mapped = 0
    unmapped = 0
    skipped = 0
    errors = 0

    for i, filename in enumerate(files):
        try:
            player_id, slug = _parse_repo_filename(filename)
        except ValueError:
            print(f"  ???   Cannot parse: {filename}")
            errors += 1
            continue

        # Resolve display name: ID lookup → slug conversion.
        display_name = _ID_TO_NAME.get(player_id) or _slug_to_display_name(slug)
        is_mapped = player_id in _ID_TO_NAME or slug in _SLUG_OVERRIDES

        if is_mapped:
            out_path = output_dir / f"{display_name}.png"
        else:
            # Also save to main dir with titlecased name.
            out_path = output_dir / f"{display_name}.png"

        if out_path.exists() and not force:
            skipped += 1
            if (i + 1) % 200 == 0:
                print(f"  ... {i + 1}/{len(files)} processed ({skipped} skipped)")
            continue

        # Download from GitHub.
        url = f"{GITHUB_RAW_BASE}players/headshots/face/{filename}"
        try:
            resp = requests.get(url, timeout=15)
            if resp.status_code != 200 or len(resp.content) < 500:
                print(f"  MISS  {display_name} ({filename})")
                errors += 1
                continue
        except requests.RequestException as exc:
            print(f"  ERR   {display_name}: {exc}")
            errors += 1
            continue

        # These are already face-cropped by the repo pipeline — just resize.
        img = _process_image(resp.content, crop=False)
        img.save(str(out_path), "PNG")

        # If not confidently mapped, also save to _unmapped.
        if not is_mapped:
            unmapped_path = unmapped_dir / f"{player_id}.png"
            img.save(str(unmapped_path), "PNG")
            unmapped += 1
        else:
            mapped += 1

        if (i + 1) % 50 == 0:
            print(f"  ... {i + 1}/{len(files)} downloaded")

        # Light rate limiting.
        if (i + 1) % 10 == 0:
            time.sleep(0.5)

    print(f"\n{'='*55}")
    print(f"  Total in repo:    {len(files)}")
    print(f"  Mapped (named):   {mapped}")
    print(f"  Unmapped (slug):  {unmapped}")
    print(f"  Skipped (exist):  {skipped}")
    print(f"  Errors:           {errors}")
    print(f"  Output:           {output_dir.resolve()}")
    print(f"  Unmapped saved:   {unmapped_dir.resolve()}")
    print(f"{'='*55}")


# ---------------------------------------------------------------------------
# Player list from input file
# ---------------------------------------------------------------------------


def players_from_excel(path: str) -> list[str]:
    """Read unique player names from an Excel/CSV file."""
    p = Path(path)
    if p.suffix.lower() in (".xlsx", ".xls"):
        df = pd.read_excel(p, engine="openpyxl")
    else:
        df = pd.read_csv(p)

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
        "--from-repo",
        dest="from_repo",
        action="store_true",
        help="Download ALL headshots from the GitHub repo.",
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

    # --from-repo mode: bulk download everything.
    if args.from_repo:
        run_from_repo(output_dir, force=args.force)
        return

    # Per-player mode.
    output_dir.mkdir(parents=True, exist_ok=True)

    names: list[str] = list(args.players) if args.players else []
    if args.input_path:
        names.extend(players_from_excel(args.input_path))
    # Deduplicate.
    seen: set[str] = set()
    unique: list[str] = []
    for n in names:
        if n not in seen:
            seen.add(n)
            unique.append(n)
    names = unique

    if not names:
        parser.error("Provide player names, --input, or --from-repo.")

    print(f"\nWill fetch headshots for {len(names)} players.\n")

    roster = fetch_player_roster()
    time.sleep(1)

    found = 0
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

        if i < len(names) - 1:
            time.sleep(1.5)

    print(f"\n{'='*50}")
    print(f"  Found:   {found}")
    print(f"  Missing: {len(missing)}")
    if missing:
        print(f"  Missing players: {', '.join(missing)}")
    print(f"  Output:  {output_dir.resolve()}")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()

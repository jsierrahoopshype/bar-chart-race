#!/usr/bin/env python3
"""Bulk-download NBA headshots from a CSV of player IDs and URLs.

Usage:
    python scripts/bulk_download_headshots.py \
        --input "path/to/Players ID _ Headshots - Sheet1.csv"

The CSV must have columns: PLAYER, HEADSHOT (URL).

Downloads missing headshots to assets/headshots/{PLAYER}.png, skipping
players that already have a file (checked via the same fuzzy matching
used by the renderer).
"""

from __future__ import annotations

import argparse
import time
import unicodedata
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

import pandas as pd
from PIL import Image
import io as _io


# ---------------------------------------------------------------------------
# Fuzzy name matching (mirrors render.py logic)
# ---------------------------------------------------------------------------

def _to_ascii(s: str) -> str:
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")


def _normalize_key(name: str) -> str:
    s = _to_ascii(name)
    s = s.replace("'", "").replace("-", " ").replace(".", "")
    return " ".join(s.lower().split())


def build_existing_index(directory: Path) -> set[str]:
    """Return a set of normalised keys for every headshot already on disk."""
    keys: set[str] = set()
    for f in directory.iterdir():
        if not f.is_file() or f.suffix.lower() not in (".png", ".jpg", ".jpeg", ".webp"):
            continue
        stem = f.stem
        keys.add(stem)                # exact
        keys.add(_normalize_key(stem)) # normalised
        keys.add(stem.lower())         # case-insensitive
        # suffix-stripped
        nk = _normalize_key(stem)
        for suffix in (" jr", " sr", " iii", " ii", " iv"):
            if nk.endswith(suffix):
                keys.add(nk[: -len(suffix)].rstrip())
    return keys


def already_exists(player: str, index: set[str]) -> bool:
    if player in index:
        return True
    if _normalize_key(player) in index:
        return True
    if player.lower() in index:
        return True
    nk = _normalize_key(player)
    for suffix in (" jr", " sr", " iii", " ii", " iv"):
        if nk.endswith(suffix) and nk[: -len(suffix)].rstrip() in index:
            return True
    return False


# ---------------------------------------------------------------------------
# Download helpers
# ---------------------------------------------------------------------------

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36",
}

MIN_REAL_HEADSHOT_BYTES = 5_000  # below this → generic silhouette


def download_headshot(url: str, dest: Path, size: int = 256) -> str:
    """Download, resize to *size*×*size* RGBA PNG.  Returns status string."""
    try:
        req = Request(url, headers=_HEADERS)
        resp = urlopen(req, timeout=15)
        data = resp.read()
    except HTTPError as e:
        return f"http_{e.code}"
    except (URLError, TimeoutError, OSError) as e:
        return f"network_error"

    if len(data) < MIN_REAL_HEADSHOT_BYTES:
        return "placeholder"

    try:
        img = Image.open(_io.BytesIO(data)).convert("RGBA")
        img = img.resize((size, size), Image.LANCZOS)
        img.save(dest, "PNG")
        return "ok"
    except Exception:
        return "bad_image"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Bulk download NBA headshots")
    parser.add_argument("--input", required=True, help="Path to CSV with PLAYER and HEADSHOT columns")
    parser.add_argument("--output", default="assets/headshots", help="Headshot output directory")
    parser.add_argument("--size", type=int, default=256, help="Output image size (square)")
    parser.add_argument("--delay", type=float, default=0.3, help="Delay between downloads (seconds)")
    parser.add_argument("--batch", type=int, default=50, help="Batch size before longer pause")
    parser.add_argument("--batch-pause", type=float, default=2.0, help="Pause between batches (seconds)")
    args = parser.parse_args()

    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(args.input)
    if "PLAYER" not in df.columns or "HEADSHOT" not in df.columns:
        raise ValueError(f"CSV must have PLAYER and HEADSHOT columns. Found: {list(df.columns)}")

    # Drop rows with missing data.
    df = df.dropna(subset=["PLAYER", "HEADSHOT"]).reset_index(drop=True)
    total = len(df)
    print(f"CSV has {total} players")

    # Build index of existing headshots.
    existing = build_existing_index(out_dir)
    print(f"Existing headshots indexed: {len(existing)} keys")

    stats = {"downloaded": 0, "skipped_exists": 0, "skipped_placeholder": 0, "failed": 0}
    download_count = 0

    for i, row in df.iterrows():
        player = str(row["PLAYER"]).strip()
        url = str(row["HEADSHOT"]).strip()

        if already_exists(player, existing):
            stats["skipped_exists"] += 1
            continue

        dest = out_dir / f"{player}.png"
        status = download_headshot(url, dest, args.size)

        if status == "ok":
            stats["downloaded"] += 1
            # Add to index so duplicates in CSV don't re-download.
            existing.add(player)
            existing.add(_normalize_key(player))
        elif status == "placeholder":
            stats["skipped_placeholder"] += 1
        else:
            stats["failed"] += 1

        download_count += 1

        if download_count % args.batch == 0:
            print(
                f"  [{i+1}/{total}] downloaded={stats['downloaded']} "
                f"placeholder={stats['skipped_placeholder']} "
                f"failed={stats['failed']}"
            )
            time.sleep(args.batch_pause)
        else:
            time.sleep(args.delay)

    print()
    print("=" * 50)
    print(f"  Total in CSV:          {total}")
    print(f"  Already existed:       {stats['skipped_exists']}")
    print(f"  Downloaded:            {stats['downloaded']}")
    print(f"  Skipped (placeholder): {stats['skipped_placeholder']}")
    print(f"  Failed:                {stats['failed']}")
    print("=" * 50)


if __name__ == "__main__":
    main()

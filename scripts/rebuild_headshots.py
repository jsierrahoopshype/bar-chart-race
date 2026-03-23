#!/usr/bin/env python3
"""Rebuild the entire headshots directory from the authoritative CSV.

Usage:
    python scripts/rebuild_headshots.py \
        --input "path/to/Players ID _ Headshots - Sheet1.csv"

This script:
  1. Reads the CSV (columns: PLAYER, HEADSHOT url)
  2. Downloads EVERY headshot from the NBA CDN, overwriting existing files
  3. Detects and removes silhouette/placeholder images
  4. Deletes any files NOT in the CSV
  5. Saves as assets/headshots/{PLAYER}.png (256x256 RGBA)
"""

from __future__ import annotations

import argparse
import os
import time
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

import numpy as np
import pandas as pd
from PIL import Image
import io as _io


_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36",
}


def download_image(url: str, timeout: int = 15) -> bytes | None:
    """Download raw bytes from URL, return None on failure."""
    try:
        req = Request(url, headers=_HEADERS)
        return urlopen(req, timeout=timeout).read()
    except (HTTPError, URLError, TimeoutError, OSError):
        return None


def is_silhouette(img: Image.Image) -> bool:
    """Detect if an image is a generic NBA CDN silhouette placeholder.

    Silhouettes are mostly one uniform gray color with very low variance.
    """
    gray = np.array(img.convert("L"), dtype=np.float32)
    std = float(np.std(gray))
    if std >= 25:
        return False

    # Check if >70% of pixels are within 30 values of the mode.
    hist, _ = np.histogram(gray.ravel(), bins=256, range=(0, 256))
    mode_val = int(np.argmax(hist))
    low = max(0, mode_val - 30)
    high = min(255, mode_val + 30)
    in_range = hist[low:high + 1].sum()
    total = gray.size
    if in_range / total > 0.70:
        return True

    return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Rebuild headshots from CSV")
    parser.add_argument("--input", required=True, help="Path to CSV")
    parser.add_argument("--output", default="assets/headshots", help="Output dir")
    parser.add_argument("--size", type=int, default=256, help="Output size")
    parser.add_argument("--delay", type=float, default=0.2, help="Delay between downloads")
    args = parser.parse_args()

    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(args.input)
    df = df.dropna(subset=["PLAYER", "HEADSHOT"]).reset_index(drop=True)

    # Build set of valid player names from CSV.
    csv_players = {str(row["PLAYER"]).strip(): str(row["HEADSHOT"]).strip()
                   for _, row in df.iterrows()}
    print(f"CSV has {len(csv_players)} players")

    # Phase 1: Delete files NOT in the CSV.
    existing = list(out_dir.glob("*.png")) + list(out_dir.glob("*.jpg"))
    deleted = 0
    for f in existing:
        if f.stem not in csv_players:
            f.unlink()
            deleted += 1
    print(f"Deleted {deleted} files not in CSV")

    # Phase 2: Download all headshots from CSV, overwriting existing.
    stats = {"downloaded": 0, "silhouette": 0, "failed": 0}

    for i, (player, url) in enumerate(csv_players.items()):
        dest = out_dir / f"{player}.png"

        data = download_image(url)
        if data is None:
            stats["failed"] += 1
            if dest.exists():
                dest.unlink()
        else:
            try:
                img = Image.open(_io.BytesIO(data)).convert("RGBA")
                if is_silhouette(img):
                    stats["silhouette"] += 1
                    if dest.exists():
                        dest.unlink()
                else:
                    img = img.resize((args.size, args.size), Image.LANCZOS)
                    img.save(dest, "PNG")
                    stats["downloaded"] += 1
            except Exception:
                stats["failed"] += 1
                if dest.exists():
                    dest.unlink()

        if (i + 1) % 100 == 0:
            print(f"  [{i+1}/{len(csv_players)}] "
                  f"ok={stats['downloaded']} sil={stats['silhouette']} "
                  f"fail={stats['failed']}")
        time.sleep(args.delay)

    print()
    print("=" * 50)
    print(f"  Total in CSV:     {len(csv_players)}")
    print(f"  Downloaded:       {stats['downloaded']}")
    print(f"  Silhouettes:      {stats['silhouette']}")
    print(f"  Failed:           {stats['failed']}")
    print(f"  Deleted (stale):  {deleted}")
    print("=" * 50)

    # Phase 3: Final count.
    final = len(list(out_dir.glob("*.png")))
    print(f"  Final headshots:  {final}")


if __name__ == "__main__":
    main()

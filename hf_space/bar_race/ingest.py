"""Data ingestion — load from Excel, CSV, or public Google Sheets URL."""

from __future__ import annotations

import io
import re
from pathlib import Path
from typing import Optional

import pandas as pd
import requests


def _gsheet_csv_url(url: str) -> str:
    """Convert a public Google Sheets URL to its CSV export variant.

    Supports both ``/edit`` and ``/pub`` style links.  If a ``gid=`` param
    is present it is preserved.
    """
    # Extract spreadsheet ID.
    m = re.search(r"/spreadsheets/d/([a-zA-Z0-9_-]+)", url)
    if not m:
        raise ValueError(f"Cannot parse Google Sheets ID from URL: {url}")
    sheet_id = m.group(1)

    # Extract optional gid.
    gid_match = re.search(r"[?&#]gid=(\d+)", url)
    gid = gid_match.group(1) if gid_match else "0"

    return (
        f"https://docs.google.com/spreadsheets/d/{sheet_id}"
        f"/export?format=csv&gid={gid}"
    )


def load(
    path: Optional[str] = None,
    gsheet_url: Optional[str] = None,
    sheet_name: Optional[str] = None,
) -> pd.DataFrame:
    """Return a :class:`~pandas.DataFrame` from the given source.

    Exactly one of *path* or *gsheet_url* must be provided.
    """
    if path and gsheet_url:
        raise ValueError("Provide either path or gsheet_url, not both.")
    if not path and not gsheet_url:
        raise ValueError("Provide at least one of path or gsheet_url.")

    if gsheet_url:
        csv_url = _gsheet_csv_url(gsheet_url)
        resp = requests.get(csv_url, timeout=30)
        resp.raise_for_status()
        return pd.read_csv(io.StringIO(resp.text))

    p = Path(path)  # type: ignore[arg-type]
    suffix = p.suffix.lower()
    if suffix in (".xlsx", ".xls"):
        return pd.read_excel(p, sheet_name=sheet_name or 0, engine="openpyxl")
    if suffix == ".csv":
        return pd.read_csv(p)

    raise ValueError(f"Unsupported file type: {suffix}")

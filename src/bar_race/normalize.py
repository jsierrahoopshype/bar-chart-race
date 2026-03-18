"""Auto-detect wide vs long/tidy format and normalize to canonical schema.

Canonical columns: ``date``, ``player``, ``value``, ``team``.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Format detection
# ---------------------------------------------------------------------------

# Heuristic column-name sets that identify long (tidy) format.
_DATE_NAMES = {"date", "game_date", "period", "month", "year", "week", "day", "season"}
_PLAYER_NAMES = {"player", "name", "athlete", "player_name"}
_VALUE_NAMES = {"value", "stat", "score", "pts", "points", "count", "total"}

_LONG_REQUIRED = (_DATE_NAMES, _PLAYER_NAMES, _VALUE_NAMES)


def _match_col(columns: list[str], candidates: set[str]) -> Optional[str]:
    """Return the first column whose lower-cased name appears in *candidates*."""
    for c in columns:
        if c.strip().lower() in candidates:
            return c
    return None


def detect_format(df: pd.DataFrame) -> str:
    """Return ``'long'`` or ``'wide'`` based on column heuristics."""
    cols = list(df.columns)
    matched = [_match_col(cols, s) for s in _LONG_REQUIRED]
    if all(m is not None for m in matched):
        return "long"
    return "wide"


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------

def _normalize_long(
    df: pd.DataFrame,
    stat_column: Optional[str] = None,
) -> pd.DataFrame:
    cols = list(df.columns)
    date_col = _match_col(cols, _DATE_NAMES)
    player_col = _match_col(cols, _PLAYER_NAMES)

    if stat_column:
        value_col = stat_column
    else:
        value_col = _match_col(cols, _VALUE_NAMES)

    if date_col is None or player_col is None or value_col is None:
        raise ValueError(
            "Long-format data must contain recognisable date, player, "
            "and value columns.  Found columns: " + ", ".join(cols)
        )

    team_col = _match_col(cols, {"team", "team_abbr", "tm"})

    out = pd.DataFrame({
        "date": pd.to_datetime(df[date_col], errors="coerce"),
        "player": df[player_col].astype(str).str.strip(),
        "value": pd.to_numeric(df[value_col], errors="coerce"),
    })

    if team_col is not None:
        out["team"] = df[team_col].astype(str).str.strip().str.upper()
    else:
        out["team"] = ""

    return out


def _normalize_wide(df: pd.DataFrame) -> pd.DataFrame:
    """First column is treated as the date; remaining columns are player names."""
    cols = list(df.columns)
    date_col = cols[0]
    player_cols = cols[1:]

    records: list[dict] = []
    for _, row in df.iterrows():
        d = row[date_col]
        for pc in player_cols:
            records.append({
                "date": d,
                "player": str(pc).strip(),
                "value": row[pc],
                "team": "",
            })

    out = pd.DataFrame(records)
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    out["value"] = pd.to_numeric(out["value"], errors="coerce")
    return out


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def normalize(
    df: pd.DataFrame,
    stat_column: Optional[str] = None,
    date_start: Optional[str] = None,
    date_end: Optional[str] = None,
) -> pd.DataFrame:
    """Return a cleaned DataFrame with columns ``date, player, value, team``.

    * Auto-detects wide vs long format.
    * Drops rows with NaN date or value.
    * Applies optional date range filtering.
    * Validates that at least 2 distinct time steps remain.
    """
    fmt = detect_format(df)

    if fmt == "long":
        out = _normalize_long(df, stat_column=stat_column)
    else:
        out = _normalize_wide(df)

    # Drop invalid rows.
    out = out.dropna(subset=["date", "value"]).copy()

    # Date filtering.
    if date_start:
        out = out[out["date"] >= pd.to_datetime(date_start)]
    if date_end:
        out = out[out["date"] <= pd.to_datetime(date_end)]

    out = out.sort_values(["date", "player"]).reset_index(drop=True)

    n_dates = out["date"].nunique()
    if n_dates < 2:
        raise ValueError(
            f"Need at least 2 distinct time steps after filtering; got {n_dates}."
        )

    return out

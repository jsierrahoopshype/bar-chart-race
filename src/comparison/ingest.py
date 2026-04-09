"""Load and normalise comparison CSV data.

Supports two layouts:

1. **Standard** — first column is category names, remaining columns are
   player names with numeric values.
2. **Transposed** — first column is player names, remaining columns are
   category names.

Auto-detects which layout is used.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd


@dataclass
class ComparisonData:
    """Normalised comparison data."""

    players: list[str]
    categories: list[str]
    # values[category][player] = numeric value
    values: dict[str, dict[str, float]] = field(default_factory=dict)


def load(path: str | Path) -> ComparisonData:
    """Load a CSV and return normalised ComparisonData."""
    p = Path(path)
    if p.suffix.lower() in (".xlsx", ".xls"):
        df = pd.read_excel(p)
    else:
        df = pd.read_csv(p)

    df.columns = [str(c).strip() for c in df.columns]

    # Detect layout: if first column values are mostly non-numeric strings
    # and other columns are mostly numeric, it's standard layout.
    first_col = df.columns[0]
    other_cols = df.columns[1:]

    first_col_numeric = pd.to_numeric(df[first_col], errors="coerce").notna().mean()
    other_numeric = 0.0
    for c in other_cols:
        other_numeric += pd.to_numeric(df[c], errors="coerce").notna().mean()
    if other_cols.size > 0:
        other_numeric /= len(other_cols)

    if first_col_numeric < 0.5 and other_numeric > 0.5:
        # Standard: categories as rows, players as columns.
        return _load_standard(df, first_col, list(other_cols))
    else:
        # Try transposed: players as rows, categories as columns.
        return _load_transposed(df, first_col, list(other_cols))


def _load_standard(
    df: pd.DataFrame, cat_col: str, player_cols: list[str]
) -> ComparisonData:
    players = player_cols
    categories: list[str] = []
    values: dict[str, dict[str, float]] = {}

    for _, row in df.iterrows():
        cat = str(row[cat_col]).strip()
        if not cat:
            continue
        categories.append(cat)
        vals: dict[str, float] = {}
        for p in players:
            v = pd.to_numeric(row[p], errors="coerce")
            vals[p] = float(v) if pd.notna(v) else 0.0
        values[cat] = vals

    return ComparisonData(players=players, categories=categories, values=values)


def _load_transposed(
    df: pd.DataFrame, player_col: str, cat_cols: list[str]
) -> ComparisonData:
    players: list[str] = []
    categories = cat_cols
    values: dict[str, dict[str, float]] = {c: {} for c in categories}

    for _, row in df.iterrows():
        player = str(row[player_col]).strip()
        if not player:
            continue
        players.append(player)
        for c in categories:
            v = pd.to_numeric(row[c], errors="coerce")
            values[c][player] = float(v) if pd.notna(v) else 0.0

    return ComparisonData(players=players, categories=categories, values=values)

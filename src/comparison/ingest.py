"""Load and normalise comparison CSV data.

Supports three input formats:

1. **Standard (Format A/C)** — first column is category names, remaining
   columns are player names with numeric values.
2. **Embedded names (Format B)** — cells contain "Name: Value" pairs.
   Player names are extracted from cells, not column headers.
3. **Transposed** — first column is player names, remaining columns are
   category names.
"""

from __future__ import annotations

import re
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


def _parse_numeric(s: str) -> float:
    """Parse a number string, handling commas: '42,184' → 42184.0."""
    s = str(s).strip().replace(",", "")
    try:
        return float(s)
    except (ValueError, TypeError):
        return 0.0


def _is_name_value_cell(cell: str) -> bool:
    """Check if a cell matches 'Name: Value' pattern."""
    if ":" not in cell:
        return False
    # Split on last colon.
    parts = cell.rsplit(":", 1)
    if len(parts) != 2:
        return False
    name_part = parts[0].strip()
    val_part = parts[1].strip().replace(",", "")
    # Name should have letters, value should be numeric.
    if not name_part or not re.search(r"[a-zA-Z]", name_part):
        return False
    try:
        float(val_part)
        return True
    except ValueError:
        return False


def _detect_format_b(df: pd.DataFrame) -> bool:
    """Check if >50% of non-first-column cells match 'Name: Value'."""
    if len(df.columns) < 2:
        return False
    hits = 0
    total = 0
    for col in df.columns[1:]:
        for val in df[col].dropna():
            total += 1
            if _is_name_value_cell(str(val)):
                hits += 1
    return total > 0 and hits / total > 0.5


def _load_format_b(df: pd.DataFrame) -> ComparisonData:
    """Parse 'Name: Value' format."""
    cat_col = df.columns[0]
    players_set: dict[str, None] = {}  # ordered set
    categories: list[str] = []
    raw_rows: list[dict[str, float]] = []

    for _, row in df.iterrows():
        cat = str(row[cat_col]).strip()
        if not cat:
            continue
        categories.append(cat)
        row_vals: dict[str, float] = {}
        for col in df.columns[1:]:
            cell = str(row[col]).strip()
            if ":" in cell:
                name, val_s = cell.rsplit(":", 1)
                name = name.strip()
                val = _parse_numeric(val_s)
                if name:
                    players_set[name] = None
                    row_vals[name] = val
        raw_rows.append(row_vals)

    players = list(players_set)
    values: dict[str, dict[str, float]] = {}
    for cat, rv in zip(categories, raw_rows):
        values[cat] = {p: rv.get(p, 0.0) for p in players}

    return ComparisonData(players=players, categories=categories, values=values)


def load(path: str | Path) -> ComparisonData:
    """Load a CSV/Excel and return normalised ComparisonData."""
    p = Path(path)
    if p.suffix.lower() in (".xlsx", ".xls"):
        df = pd.read_excel(p)
    else:
        df = pd.read_csv(p)

    df.columns = [str(c).strip() for c in df.columns]

    # Check for Format B (embedded "Name: Value" cells).
    if _detect_format_b(df):
        return _load_format_b(df)

    # Detect standard vs transposed.
    first_col = df.columns[0]
    other_cols = df.columns[1:]

    first_col_numeric = pd.to_numeric(df[first_col], errors="coerce").notna().mean()
    other_numeric = 0.0
    for c in other_cols:
        other_numeric += pd.to_numeric(df[c], errors="coerce").notna().mean()
    if other_cols.size > 0:
        other_numeric /= len(other_cols)

    if first_col_numeric < 0.5 and other_numeric > 0.5:
        return _load_standard(df, first_col, list(other_cols))
    else:
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

"""Auto-detect wide vs long/tidy format and normalize to canonical schema.

Canonical columns: ``date``, ``player``, ``value``, ``team``.

Supports three input shapes:

1. **Long / tidy** — columns for date, player, value (and optionally team).
2. **Wide** — first column is the date; remaining columns are player names.
3. **Transposed wide** — first column is player names; remaining columns
   are numeric time labels (ages, years, etc.).  Column headers may be
   pure numbers (``18``, ``2001``) or descriptive strings containing a
   number (``"Points scored at age 18"``).
"""

from __future__ import annotations

import re
import sys
from datetime import datetime
from typing import Optional

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Format detection
# ---------------------------------------------------------------------------

# Heuristic column-name sets that identify long (tidy) format.
_DATE_NAMES = {"date", "game_date", "period", "month", "year", "week", "day", "season"}
_PLAYER_NAMES = {"player", "name", "athlete", "player_name", "team", "country", "city", "entity"}
_VALUE_NAMES = {"value", "stat", "score", "pts", "points", "count", "total"}

_LONG_REQUIRED = (_DATE_NAMES, _PLAYER_NAMES, _VALUE_NAMES)


def _match_col(columns: list[str], candidates: set[str]) -> Optional[str]:
    """Return the first column whose lower-cased name appears in *candidates*."""
    for c in columns:
        if c.strip().lower() in candidates:
            return c
    return None


def _extract_numeric_label(s: str) -> Optional[str]:
    """Extract a numeric label from a column header.

    Returns the number as a string, or *None* if no number is found.

    Examples::

        "18"                       → "18"
        "Points scored at age 18"  → "18"
        "2001"                     → "2001"
        "Player"                   → None
    """
    s = str(s).strip()
    # Pure numeric.
    if re.fullmatch(r'\d+', s):
        return s
    # Last number inside a descriptive header.
    m = re.findall(r'\d+', s)
    return m[-1] if m else None


def _try_parse_date_col(col: str) -> bool:
    """Return True if *col* looks like a month-day name (e.g. "October 21")."""
    s = str(col).strip()
    for fmt in ("%B %d", "%b %d"):
        try:
            datetime.strptime(s, fmt)
            return True
        except ValueError:
            continue
    return False


def _has_date_name_columns(cols: list[str]) -> bool:
    """Return True if ≥80 % of *cols* parse as "Month Day" strings."""
    if not cols:
        return False
    hits = sum(1 for c in cols if _try_parse_date_col(c))
    return hits >= len(cols) * 0.8


# Age-month column patterns: "18 years", "18 years, 1 month", "30 years (alt)"
_AGE_MONTH_RE = re.compile(
    r"(\d+)\s*years?(?:,\s*(\d+)\s*months?)?", re.IGNORECASE
)


def _parse_age_month(col: str) -> Optional[float]:
    """Parse "X years, Y months" → decimal age, or None."""
    s = str(col).strip()
    # Skip columns with parenthetical notes like "(alt)".
    if "(" in s:
        return None
    m = _AGE_MONTH_RE.search(s)
    if m:
        years = int(m.group(1))
        months = int(m.group(2)) if m.group(2) else 0
        return years + months / 12.0
    return None


def _has_age_month_columns(cols: list[str]) -> bool:
    """Return True if ≥80 % of *cols* contain the word 'year(s)'."""
    if not cols:
        return False
    hits = sum(1 for c in cols if _AGE_MONTH_RE.search(str(c).strip())
               and "(" not in str(c))
    return hits >= len(cols) * 0.8


# Plain-year headers must fall inside a believable calendar range, otherwise
# "10000 points" would be mistaken for the year 10000.
_YEAR_MIN = 1900
_YEAR_MAX = 2100
# Small numbers (ages, rounds, game numbers) are mapped to year 2000 + n.
_AGE_OFFSET_MAX = 200
# Season-style headers: "2024-25", "2024–2025", "2024/25".
_SEASON_RE = re.compile(r'^\s*(\d{4})\s*[-–/]\s*\d{2,4}\s*$')


def _is_plain_year(s: str) -> bool:
    """Return True if *s* is nothing but a believable year (or season)."""
    s = str(s).strip()
    m = _SEASON_RE.match(s)
    if m:
        return _YEAR_MIN <= int(m.group(1)) <= _YEAR_MAX
    if re.fullmatch(r'\d{4}', s):
        return _YEAR_MIN <= int(s) <= _YEAR_MAX
    return False


def _numeric_timeline_ok(time_cols: list) -> bool:
    """Return True if *time_cols* can safely become timestamps.

    Guards the numeric branch against headers like ``"43000 points"``,
    whose extracted number would overflow :class:`pandas.Timestamp`.
    """
    nums: list[int] = []
    for c in time_cols:
        label = _extract_numeric_label(str(c))
        if label is None:
            return False
        try:
            nums.append(int(label))
        except ValueError:
            return False
    if not nums:
        return False
    # Bare years / seasons.
    if all(_is_plain_year(c) for c in time_cols):
        return True
    lo, hi = min(nums), max(nums)
    # Year branch (mirrors _normalize_transposed_wide's own thresholds).
    if lo >= _YEAR_MIN and hi <= 2200:
        return True
    # Age / round branch: mapped to year 2000 + n, so n must stay small.
    return hi <= _AGE_OFFSET_MAX


def _format_label(text: str) -> str:
    """Pretty-print a free-form timeline label.

    Adds thousands separators to bare numbers ("1000 points" →
    "1,000 points") while leaving years untouched.  Idempotent.
    """
    text = str(text).strip()
    if _is_plain_year(text):
        return text
    return re.sub(
        r'(?<![\d,])\d+(?![\d,])',
        lambda m: f"{int(m.group()):,}",
        text,
    )


def _is_transposed_wide(df: pd.DataFrame) -> bool:
    """Detect transposed wide format (players as rows, time periods as cols).

    Heuristic: the first column contains strings (player names) and ≥80 % of
    the remaining column headers contain an extractable number **or** parse
    as "Month Day" date names (e.g. "October 21", "Jan 5").
    """
    cols = list(df.columns)
    if len(cols) < 3:
        return False

    first = str(cols[0]).strip().lower()
    first_is_player = (
        first in _PLAYER_NAMES
        or first.startswith("unnamed")
        or first == ""
    )
    if not first_is_player:
        return False

    other_cols = cols[1:]

    # Check for age-month columns ("18 years", "18 years, 1 month").
    if _has_age_month_columns(other_cols):
        return True

    # Check for date-name columns ("October 21", "Nov 5").
    if _has_date_name_columns(other_cols):
        return True

    # Existing check: numeric column headers.
    numeric_count = sum(
        1 for c in other_cols if _extract_numeric_label(c) is not None
    )
    if numeric_count >= len(other_cols) * 0.8:
        return True

    # Fallback: the first column is *explicitly* named like an entity column,
    # so the remaining headers are arbitrary timeline labels (milestones,
    # rounds, stages...) that column order alone can sequence.
    return first in _PLAYER_NAMES


def detect_format(df: pd.DataFrame) -> str:
    """Return ``'long'``, ``'wide'``, or ``'transposed_wide'``."""
    cols = list(df.columns)
    matched = [_match_col(cols, s) for s in _LONG_REQUIRED]
    if all(m is not None for m in matched):
        return "long"
    if _is_transposed_wide(df):
        return "transposed_wide"
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


def _normalize_transposed_wide(
    df: pd.DataFrame,
    timeline_type: str = "auto",
) -> pd.DataFrame:
    """Players as rows, time periods (ages / years) as columns.

    Melts the data to long format, converts numeric column headers to
    timestamps for pipeline compatibility, and stores a label map in
    ``df.attrs["date_label_map"]`` so that downstream code can display
    original labels (e.g. ``"18"`` instead of ``"Jan 01, 2018"``).

    Also supports date-name columns like "October 21", "January 5" where
    the column header itself is used as the display label, and — as a
    final fallback — arbitrary text headers ("1000 points") sequenced by
    column order (*labels* mode).

    *timeline_type* forces a branch: ``"dates"``, ``"ages"``, ``"years"``,
    ``"labels"``, or ``"auto"`` (detect, the default).
    """
    cols = list(df.columns)
    player_col = cols[0]
    time_cols = cols[1:]

    tt = (timeline_type or "auto").strip().lower()

    if tt == "labels":
        return _normalize_labels_timeline(df, player_col, time_cols)

    if tt == "auto" or tt == "ages":
        # Branch: age-month columns ("18 years", "18 years, 1 month").
        if _has_age_month_columns(time_cols):
            return _normalize_transposed_wide_age_months(
                df, player_col, time_cols)

    if tt == "auto" or tt == "dates":
        # Branch: date-name columns ("October 21", "Nov 5").
        if _has_date_name_columns(time_cols):
            return _normalize_transposed_wide_date_names(
                df, player_col, time_cols)

    # Numeric branch — only when the headers really are numbers that fit in
    # a timestamp.  Otherwise fall through to labels mode.
    if not _numeric_timeline_ok(time_cols):
        if tt not in ("auto", ""):
            sys.stderr.write(
                f"  Timeline type {tt!r} requested, but these column headers "
                f"are not usable dates; using column order instead.\n"
            )
        return _normalize_labels_timeline(df, player_col, time_cols)

    records: list[dict] = []
    for _, row in df.iterrows():
        player = str(row[player_col]).strip()
        for tc in time_cols:
            val = row[tc]
            if pd.isna(val):
                continue
            val = float(val)
            if val == 0:
                continue
            label = _extract_numeric_label(str(tc))
            if label is not None:
                records.append({
                    "date_num": int(label),
                    "date_label": label,
                    "player": player,
                    "value": val,
                    "team": "",
                })

    if not records:
        raise ValueError("No non-zero data found in transposed wide format.")

    out = pd.DataFrame(records)

    # Convert numeric labels to timestamps.
    # Years (≥1900): use Jan 1 of that year.
    # Small numbers (ages, rounds, etc.): offset by 2000.
    min_num = out["date_num"].min()
    max_num = out["date_num"].max()

    if min_num >= 1900 and max_num <= 2200:
        out["date"] = out["date_num"].apply(
            lambda y: pd.Timestamp(year=int(y), month=1, day=1)
        )
    else:
        out["date"] = out["date_num"].apply(
            lambda a: pd.Timestamp(year=2000 + int(a), month=1, day=1)
        )

    # Build a map from timestamp → original label for display.
    label_map: dict[pd.Timestamp, str] = {}
    for _, row in out.drop_duplicates("date_num").iterrows():
        label_map[row["date"]] = str(row["date_label"])

    out["value"] = pd.to_numeric(out["value"], errors="coerce")
    result = out[["date", "player", "value", "team"]].copy()
    result.attrs["date_label_map"] = label_map
    return result


def _normalize_transposed_wide_date_names(
    df: pd.DataFrame,
    player_col: str,
    time_cols: list[str],
) -> pd.DataFrame:
    """Handle transposed wide where columns are "Month Day" strings.

    Infers a sports-season year: Oct-Dec → 2025, Jan-Sep → 2026.
    Column headers are preserved as display labels.
    """
    # Parse each column header into a (month, day) and assign a year.
    col_dates: list[tuple[str, pd.Timestamp]] = []
    for idx, tc in enumerate(time_cols):
        s = str(tc).strip()
        parsed = None
        for fmt in ("%B %d", "%b %d"):
            try:
                parsed = datetime.strptime(s, fmt)
                break
            except ValueError:
                continue
        if parsed is None:
            # Skip unparseable columns.
            continue
        month, day = parsed.month, parsed.day
        # Sports season heuristic: Oct-Dec → 2025, Jan-Sep → 2026.
        year = 2025 if month >= 10 else 2026
        ts = pd.Timestamp(year=year, month=month, day=day)
        col_dates.append((str(tc), ts))

    if not col_dates:
        raise ValueError("No parseable date-name columns found.")

    records: list[dict] = []
    for _, row in df.iterrows():
        player = str(row[player_col]).strip()
        for col_name, ts in col_dates:
            val = row[col_name]
            if pd.isna(val):
                continue
            val = float(val)
            if val == 0:
                continue
            records.append({
                "date": ts,
                "date_label": str(col_name).strip(),
                "player": player,
                "value": val,
                "team": "",
            })

    if not records:
        raise ValueError("No non-zero data found in date-name columns.")

    out = pd.DataFrame(records)
    out["value"] = pd.to_numeric(out["value"], errors="coerce")

    # Build label map: timestamp → original column header for display.
    label_map: dict[pd.Timestamp, str] = {}
    for col_name, ts in col_dates:
        label_map[ts] = col_name.strip()

    result = out[["date", "player", "value", "team"]].copy()
    result.attrs["date_label_map"] = label_map
    return result


def _normalize_transposed_wide_age_months(
    df: pd.DataFrame,
    player_col: str,
    time_cols: list[str],
) -> pd.DataFrame:
    """Handle transposed wide where columns are "X years, Y months".

    Converts to decimal ages, maps to synthetic timestamps for the
    pipeline, and uses "Age N" as the display label (changes only when
    the integer year part changes).
    """
    # Parse each column into (col_name, decimal_age, year_part).
    col_ages: list[tuple[str, float, int]] = []
    for tc in time_cols:
        age = _parse_age_month(tc)
        if age is not None:
            col_ages.append((str(tc), age, int(age)))

    if not col_ages:
        raise ValueError("No parseable age-month columns found.")

    # Sort by decimal age to ensure correct ordering.
    col_ages.sort(key=lambda x: x[1])

    # Map decimal age → synthetic timestamp (base date + age * 365.25 days).
    base = pd.Timestamp("2000-01-01")

    records: list[dict] = []
    for _, row in df.iterrows():
        player = str(row[player_col]).strip()
        for col_name, age, year_part in col_ages:
            val = row[col_name]
            if pd.isna(val):
                continue
            val = float(val)
            if val == 0:
                continue
            ts = base + pd.Timedelta(days=age * 365.25)
            records.append({
                "date": ts,
                "player": player,
                "value": val,
                "team": "",
                "_year_part": year_part,
            })

    if not records:
        raise ValueError("No non-zero data found in age-month columns.")

    out = pd.DataFrame(records)
    out["value"] = pd.to_numeric(out["value"], errors="coerce")

    # Build label map: timestamp → original column header for display.
    label_map: dict[pd.Timestamp, str] = {}
    for col_name, age, year_part in col_ages:
        ts = base + pd.Timedelta(days=age * 365.25)
        label_map[ts] = col_name.strip()

    result = out[["date", "player", "value", "team"]].copy()
    result.attrs["date_label_map"] = label_map
    return result


def _normalize_labels_timeline(
    df: pd.DataFrame,
    player_col: str,
    time_cols: list[str],
) -> pd.DataFrame:
    """Handle transposed wide where columns are arbitrary text labels.

    Column *order* is the timeline: each column gets a synthetic timestamp
    (base date + column index days) that exists purely for ordering, while
    the original header text is kept in ``date_label_map`` so it is what
    appears on screen.  Labels are never parsed as dates.

    Blank cells mean "not present at this step" — the entity simply drops
    out of the race rather than being treated as zero or forward-filled.
    """
    if not time_cols:
        raise ValueError("No timeline columns found.")

    base = pd.Timestamp("2000-01-01")
    col_dates: list[tuple[str, pd.Timestamp]] = [
        (str(tc), base + pd.Timedelta(days=i))
        for i, tc in enumerate(time_cols)
    ]

    records: list[dict] = []
    for _, row in df.iterrows():
        player = str(row[player_col]).strip()
        for col_name, ts in col_dates:
            val = pd.to_numeric(row[col_name], errors="coerce")
            if pd.isna(val):
                continue  # blank → not present at this step
            val = float(val)
            if val == 0:
                continue
            records.append({
                "date": ts,
                "player": player,
                "value": val,
                "team": "",
            })

    if not records:
        raise ValueError("No non-zero data found in the timeline columns.")

    out = pd.DataFrame(records)
    out["value"] = pd.to_numeric(out["value"], errors="coerce")

    # Display labels: original header text, prettified ("1,000 points").
    label_map: dict[pd.Timestamp, str] = {
        ts: _format_label(col_name) for col_name, ts in col_dates
    }

    result = out[["date", "player", "value", "team"]].copy()
    result.attrs["date_label_map"] = label_map
    result.attrs["timeline_mode"] = "labels"
    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def normalize(
    df: pd.DataFrame,
    stat_column: Optional[str] = None,
    date_start: Optional[str] = None,
    date_end: Optional[str] = None,
    timeline_type: str = "auto",
) -> pd.DataFrame:
    """Return a cleaned DataFrame with columns ``date, player, value, team``.

    * Auto-detects wide, transposed wide, and long format.
    * Drops rows with NaN date or value.
    * Applies optional date range filtering.
    * Validates that at least 2 distinct time steps remain.
    """
    fmt = detect_format(df)

    if fmt == "long":
        out = _normalize_long(df, stat_column=stat_column)
    elif fmt == "transposed_wide":
        out = _normalize_transposed_wide(df, timeline_type=timeline_type)
    else:
        out = _normalize_wide(df)

    # Preserve attrs (e.g. date_label_map) through operations.
    saved_attrs = out.attrs.copy()

    # Drop invalid rows.
    out = out.dropna(subset=["date", "value"]).copy()
    out.attrs.update(saved_attrs)

    # Date filtering.
    if date_start:
        out = out[out["date"] >= pd.to_datetime(date_start)]
        out.attrs.update(saved_attrs)
    if date_end:
        out = out[out["date"] <= pd.to_datetime(date_end)]
        out.attrs.update(saved_attrs)

    out = out.sort_values(["date", "player"]).reset_index(drop=True)
    out.attrs.update(saved_attrs)

    n_dates = out["date"].nunique()
    if n_dates < 2:
        raise ValueError(
            f"Need at least 2 distinct time steps after filtering; got {n_dates}."
        )

    return out

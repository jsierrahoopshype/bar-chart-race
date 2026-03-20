"""Build keyframes from normalised data and interpolate between them.

Each *keyframe* corresponds to one unique date in the data.  Between
consecutive keyframes we generate ``frames_per_step`` intermediate frames
using cubic ease-in-out interpolation so that bars slide smoothly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Easing
# ---------------------------------------------------------------------------

def ease_in_out_cubic(t: float) -> float:
    """Cubic ease-in-out: smooth start and stop in [0, 1]."""
    t = max(0.0, min(1.0, t))
    if t < 0.5:
        return 4.0 * t * t * t
    return 1.0 - (-2.0 * t + 2.0) ** 3 / 2.0


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class BarState:
    """Snapshot of a single bar in one frame."""

    player: str
    value: float
    rank: float  # may be fractional during interpolation
    team: str = ""

    # Visual state flags
    entering: bool = False
    exiting: bool = False
    alpha: float = 1.0  # 0→1 entering, 1→0 exiting


@dataclass
class FrameState:
    """Complete state for a single rendered frame."""

    bars: list[BarState]
    date_label: str
    progress: float  # 0‥1 overall animation progress
    max_value: float


@dataclass
class Keyframe:
    """One per unique date — raw snapshot from the data."""

    date: datetime
    entries: list[BarState]  # sorted descending by value
    label: str = ""  # original label (e.g. "18" for age-based data)


# ---------------------------------------------------------------------------
# Keyframe building
# ---------------------------------------------------------------------------

def build_keyframes(df: pd.DataFrame, top_n: int = 10) -> list[Keyframe]:
    """Build one :class:`Keyframe` per unique date, keeping *top_n* entries."""
    label_map: dict = df.attrs.get("date_label_map", {})
    keyframes: list[Keyframe] = []

    for date, grp in df.groupby("date"):
        # Aggregate duplicates (same player on same date).
        agg = grp.groupby("player", as_index=False).agg(
            {"value": "max", "team": "first"}
        )
        agg = agg.sort_values("value", ascending=False).head(top_n).reset_index(drop=True)

        entries = [
            BarState(
                player=row["player"],
                value=float(row["value"]),
                rank=float(i),
                team=str(row["team"]),
            )
            for i, row in agg.iterrows()
        ]
        ts = pd.Timestamp(date).to_pydatetime()
        label = label_map.get(pd.Timestamp(date), "")
        keyframes.append(Keyframe(date=ts, entries=entries, label=label))

    keyframes.sort(key=lambda k: k.date)
    return keyframes


# ---------------------------------------------------------------------------
# Interpolation
# ---------------------------------------------------------------------------

def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _interpolate_date(
    d1: datetime,
    d2: datetime,
    t: float,
    label_a: str = "",
    label_b: str = "",
) -> str:
    """Linearly interpolate between two dates and return a label string.

    When *label_a* / *label_b* are provided (numeric label data such as
    ages or years) the function interpolates between the numeric values
    and returns the rounded integer as a string.
    """
    if label_a and label_b:
        try:
            na, nb = float(label_a), float(label_b)
            return str(int(round(na + (nb - na) * t)))
        except ValueError:
            return label_a if t < 0.5 else label_b

    delta = (d2 - d1).total_seconds()
    result = d1 + timedelta(seconds=delta * t)
    return result.strftime("%b %d, %Y")


def interpolate_frames(
    keyframes: list[Keyframe],
    total_frames: int,
    top_n: int = 10,
) -> list[FrameState]:
    """Generate *total_frames* :class:`FrameState` objects by interpolating.

    Bars that appear in the next keyframe but not the current one *enter*
    from below; bars disappearing *exit* downward.
    """
    if len(keyframes) < 2:
        raise ValueError("Need at least 2 keyframes to interpolate.")

    n_steps = len(keyframes) - 1
    frames_per_step = max(1, total_frames // n_steps)
    frames: list[FrameState] = []

    for step_idx in range(n_steps):
        kf_a = keyframes[step_idx]
        kf_b = keyframes[step_idx + 1]

        map_a = {b.player: b for b in kf_a.entries}
        map_b = {b.player: b for b in kf_b.entries}
        all_players = list(dict.fromkeys(
            [b.player for b in kf_a.entries] + [b.player for b in kf_b.entries]
        ))

        n_frames = frames_per_step if step_idx < n_steps - 1 else (total_frames - len(frames))
        n_frames = max(n_frames, 1)

        for fi in range(n_frames):
            raw_t = fi / max(n_frames - 1, 1)
            t = ease_in_out_cubic(raw_t)

            bars: list[BarState] = []

            for player in all_players:
                a = map_a.get(player)
                b = map_b.get(player)

                entering = a is None
                exiting = b is None

                val_a = a.value if a else 0.0
                val_b = b.value if b else 0.0
                rank_a = a.rank if a else float(top_n)
                rank_b = b.rank if b else float(top_n)
                team = (a.team if a else b.team) if (a or b) else ""  # type: ignore[union-attr]

                value = _lerp(val_a, val_b, t)
                rank = _lerp(rank_a, rank_b, t)

                alpha = t if entering else (1.0 - t if exiting else 1.0)

                bars.append(BarState(
                    player=player,
                    value=value,
                    rank=rank,
                    team=team,
                    entering=entering,
                    exiting=exiting,
                    alpha=alpha,
                ))

            # Keep only visible bars (rank < top_n).
            bars = [b for b in bars if b.rank < top_n]
            bars.sort(key=lambda b: b.rank)

            date_label = _interpolate_date(
                kf_a.date, kf_b.date, raw_t,
                label_a=kf_a.label, label_b=kf_b.label,
            )

            max_value = max((b.value for b in bars), default=1.0)

            overall_progress = (step_idx + raw_t) / n_steps

            frames.append(FrameState(
                bars=bars,
                date_label=date_label,
                progress=overall_progress,
                max_value=max_value,
            ))

    return frames

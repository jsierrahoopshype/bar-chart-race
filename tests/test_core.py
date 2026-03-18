"""Comprehensive tests for bar-chart-race core modules."""

from __future__ import annotations

import os
import tempfile
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from bar_race.animate import (
    BarState,
    Keyframe,
    build_keyframes,
    ease_in_out_cubic,
    interpolate_frames,
)
from bar_race.config import (
    FALLBACK_PALETTE,
    NBA_TEAM_COLORS,
    PRESETS,
    Config,
    VideoPreset,
)
from bar_race.normalize import detect_format, normalize


# =========================================================================
# Config & Presets
# =========================================================================


class TestPresets:
    def test_reels_dimensions(self) -> None:
        p = PRESETS["reels"]
        assert p.width == 1080
        assert p.height == 1920

    def test_youtube_dimensions(self) -> None:
        p = PRESETS["youtube"]
        assert p.width == 1920
        assert p.height == 1080

    def test_square_dimensions(self) -> None:
        p = PRESETS["square"]
        assert p.width == 1080
        assert p.height == 1080

    def test_preset_aspect_ratio(self) -> None:
        assert PRESETS["reels"].aspect == "9:16"
        assert PRESETS["youtube"].aspect == "16:9"
        assert PRESETS["square"].aspect == "1:1"

    def test_all_presets_present(self) -> None:
        assert set(PRESETS.keys()) == {"reels", "youtube", "square"}


class TestConfig:
    def test_defaults(self) -> None:
        cfg = Config()
        assert cfg.fps == 60
        assert cfg.duration_sec == 30.0
        assert cfg.bitrate == "12M"
        assert cfg.top_n == 10
        assert cfg.preset == "reels"
        assert cfg.vignette is True
        assert cfg.noise is True
        assert cfg.leader_glow is True
        assert cfg.rounded_bars is True
        assert cfg.bar_shadow is True
        assert cfg.use_team_colors is True
        assert cfg.axis_mode == "auto"
        assert cfg.intro_hold_sec == 0.0
        assert cfg.outro_hold_sec == 0.0

    def test_get_preset_valid(self) -> None:
        cfg = Config(preset="youtube")
        p = cfg.get_preset()
        assert p.width == 1920
        assert p.height == 1080

    def test_get_preset_invalid(self) -> None:
        cfg = Config(preset="widescreen")
        with pytest.raises(ValueError, match="Unknown preset"):
            cfg.get_preset()

    def test_bg_gradient_default(self) -> None:
        cfg = Config()
        assert len(cfg.bg_gradient) == 2
        assert cfg.bg_gradient[0].startswith("#")

    def test_from_yaml(self, tmp_path: Path) -> None:
        yaml_file = tmp_path / "test.yaml"
        yaml_file.write_text(
            "preset: youtube\nfps: 30\ntop_n: 5\ntitle: Test\n"
            "bg_gradient:\n  - '#000000'\n  - '#ffffff'\n"
        )
        cfg = Config.from_yaml(str(yaml_file))
        assert cfg.preset == "youtube"
        assert cfg.fps == 30
        assert cfg.top_n == 5
        assert cfg.title == "Test"
        assert cfg.bg_gradient == ("#000000", "#ffffff")

    def test_from_yaml_ignores_unknown_keys(self, tmp_path: Path) -> None:
        yaml_file = tmp_path / "test.yaml"
        yaml_file.write_text("unknown_key: 42\nfps: 24\n")
        cfg = Config.from_yaml(str(yaml_file))
        assert cfg.fps == 24
        assert not hasattr(cfg, "unknown_key")

    def test_fonts_populated(self) -> None:
        cfg = Config()
        assert cfg.font_bold != ""
        assert cfg.font_medium != ""


class TestNBAColors:
    def test_all_30_teams(self) -> None:
        assert len(NBA_TEAM_COLORS) == 30

    def test_colors_are_hex(self) -> None:
        for team, color in NBA_TEAM_COLORS.items():
            assert color.startswith("#"), f"{team} color {color} is not hex"
            assert len(color) == 7, f"{team} color {color} has wrong length"

    def test_known_teams(self) -> None:
        assert "LAL" in NBA_TEAM_COLORS
        assert "GSW" in NBA_TEAM_COLORS
        assert "BOS" in NBA_TEAM_COLORS


class TestFallbackPalette:
    def test_length(self) -> None:
        assert len(FALLBACK_PALETTE) >= 10

    def test_hex_format(self) -> None:
        for c in FALLBACK_PALETTE:
            assert c.startswith("#")


# =========================================================================
# Format detection & Normalization
# =========================================================================


def _make_long_df() -> pd.DataFrame:
    """Minimal long-format DataFrame."""
    return pd.DataFrame({
        "date": ["2024-01-01", "2024-01-01", "2024-02-01", "2024-02-01"],
        "player": ["LeBron", "Curry", "LeBron", "Curry"],
        "value": [30, 28, 32, 35],
        "team": ["LAL", "GSW", "LAL", "GSW"],
    })


def _make_wide_df() -> pd.DataFrame:
    """Minimal wide-format DataFrame."""
    return pd.DataFrame({
        "date": ["2024-01-01", "2024-02-01", "2024-03-01"],
        "LeBron": [30, 32, 34],
        "Curry": [28, 35, 33],
    })


class TestFormatDetection:
    def test_detect_long(self) -> None:
        assert detect_format(_make_long_df()) == "long"

    def test_detect_wide(self) -> None:
        assert detect_format(_make_wide_df()) == "wide"

    def test_detect_long_case_insensitive(self) -> None:
        df = _make_long_df().rename(columns={"date": "Date", "player": "Player", "value": "Value"})
        assert detect_format(df) == "long"

    def test_detect_wide_no_player_column(self) -> None:
        df = pd.DataFrame({"month": ["Jan", "Feb"], "A": [1, 2], "B": [3, 4]})
        assert detect_format(df) == "wide"


class TestNormalizeLong:
    def test_basic(self) -> None:
        out = normalize(_make_long_df())
        assert list(out.columns) == ["date", "player", "value", "team"]
        assert len(out) == 4

    def test_nan_dropped(self) -> None:
        df = _make_long_df()
        df.loc[0, "value"] = np.nan
        out = normalize(df)
        assert len(out) == 3

    def test_date_parsing(self) -> None:
        out = normalize(_make_long_df())
        assert pd.api.types.is_datetime64_any_dtype(out["date"])

    def test_team_uppercased(self) -> None:
        df = _make_long_df()
        df["team"] = ["lal", "gsw", "lal", "gsw"]
        out = normalize(df)
        assert all(t == t.upper() for t in out["team"])

    def test_stat_column_override(self) -> None:
        df = _make_long_df().rename(columns={"value": "pts"})
        out = normalize(df, stat_column="pts")
        assert "value" in out.columns
        assert out["value"].sum() > 0

    def test_date_filtering_start(self) -> None:
        df = pd.DataFrame({
            "date": ["2024-01-01", "2024-01-01", "2024-02-01", "2024-02-01",
                     "2024-03-01", "2024-03-01"],
            "player": ["LeBron", "Curry"] * 3,
            "value": [30, 28, 32, 35, 34, 33],
            "team": ["LAL", "GSW"] * 3,
        })
        out = normalize(df, date_start="2024-01-15")
        assert out["date"].min() >= pd.Timestamp("2024-01-15")

    def test_date_filtering_end(self) -> None:
        df = pd.DataFrame({
            "date": ["2024-01-01", "2024-01-01", "2024-02-01", "2024-02-01",
                     "2024-03-01", "2024-03-01"],
            "player": ["LeBron", "Curry"] * 3,
            "value": [30, 28, 32, 35, 34, 33],
            "team": ["LAL", "GSW"] * 3,
        })
        out = normalize(df, date_end="2024-02-15")
        assert out["date"].max() <= pd.Timestamp("2024-02-15")

    def test_fewer_than_2_dates_raises(self) -> None:
        df = pd.DataFrame({
            "date": ["2024-01-01"],
            "player": ["LeBron"],
            "value": [30],
        })
        with pytest.raises(ValueError, match="at least 2"):
            normalize(df)


class TestNormalizeWide:
    def test_basic(self) -> None:
        out = normalize(_make_wide_df())
        assert list(out.columns) == ["date", "player", "value", "team"]
        assert set(out["player"]) == {"LeBron", "Curry"}
        assert len(out) == 6

    def test_nan_in_wide(self) -> None:
        df = _make_wide_df()
        df.loc[0, "LeBron"] = np.nan
        out = normalize(df)
        assert len(out) == 5


# =========================================================================
# Excel loading (integration-ish)
# =========================================================================


class TestExcelLoading:
    def test_load_xlsx(self, tmp_path: Path) -> None:
        from bar_race.ingest import load

        df = _make_long_df()
        xlsx_path = tmp_path / "test.xlsx"
        df.to_excel(str(xlsx_path), index=False, engine="openpyxl")

        loaded = load(path=str(xlsx_path))
        assert len(loaded) == len(df)
        assert list(loaded.columns) == list(df.columns)

    def test_load_csv(self, tmp_path: Path) -> None:
        from bar_race.ingest import load

        df = _make_long_df()
        csv_path = tmp_path / "test.csv"
        df.to_csv(str(csv_path), index=False)

        loaded = load(path=str(csv_path))
        assert len(loaded) == len(df)

    def test_load_no_source_raises(self) -> None:
        from bar_race.ingest import load

        with pytest.raises(ValueError, match="at least one"):
            load()

    def test_load_both_sources_raises(self) -> None:
        from bar_race.ingest import load

        with pytest.raises(ValueError, match="not both"):
            load(path="a.csv", gsheet_url="https://example.com")


# =========================================================================
# Animation: keyframes, interpolation, easing
# =========================================================================


class TestEasing:
    def test_bounds(self) -> None:
        assert ease_in_out_cubic(0.0) == pytest.approx(0.0)
        assert ease_in_out_cubic(1.0) == pytest.approx(1.0)

    def test_midpoint(self) -> None:
        assert ease_in_out_cubic(0.5) == pytest.approx(0.5)

    def test_clamp_below(self) -> None:
        assert ease_in_out_cubic(-0.5) == pytest.approx(0.0)

    def test_clamp_above(self) -> None:
        assert ease_in_out_cubic(1.5) == pytest.approx(1.0)

    def test_monotonic(self) -> None:
        vals = [ease_in_out_cubic(t / 100) for t in range(101)]
        for a, b in zip(vals, vals[1:]):
            assert b >= a - 1e-9


class TestKeyframes:
    def test_build(self) -> None:
        df = normalize(_make_long_df())
        kfs = build_keyframes(df, top_n=10)
        assert len(kfs) == 2  # two unique dates
        assert all(isinstance(k, Keyframe) for k in kfs)

    def test_sorted_by_date(self) -> None:
        df = normalize(_make_long_df())
        kfs = build_keyframes(df)
        dates = [k.date for k in kfs]
        assert dates == sorted(dates)

    def test_entries_sorted_desc(self) -> None:
        df = normalize(_make_long_df())
        kfs = build_keyframes(df)
        for kf in kfs:
            vals = [e.value for e in kf.entries]
            assert vals == sorted(vals, reverse=True)

    def test_top_n_limit(self) -> None:
        rows = []
        for i in range(20):
            rows.append({"date": "2024-01-01", "player": f"P{i}", "value": i, "team": ""})
            rows.append({"date": "2024-02-01", "player": f"P{i}", "value": i + 5, "team": ""})
        df = normalize(pd.DataFrame(rows))
        kfs = build_keyframes(df, top_n=5)
        for kf in kfs:
            assert len(kf.entries) <= 5


class TestInterpolation:
    def _two_keyframes(self) -> list[Keyframe]:
        return [
            Keyframe(
                date=datetime(2024, 1, 1),
                entries=[
                    BarState(player="A", value=100, rank=0.0, team="LAL"),
                    BarState(player="B", value=80, rank=1.0, team="GSW"),
                ],
            ),
            Keyframe(
                date=datetime(2024, 2, 1),
                entries=[
                    BarState(player="B", value=110, rank=0.0, team="GSW"),
                    BarState(player="A", value=90, rank=1.0, team="LAL"),
                ],
            ),
        ]

    def test_frame_count(self) -> None:
        frames = interpolate_frames(self._two_keyframes(), total_frames=60, top_n=10)
        assert len(frames) == 60

    def test_first_frame_matches_kf1(self) -> None:
        frames = interpolate_frames(self._two_keyframes(), total_frames=60, top_n=10)
        first = frames[0]
        a = next(b for b in first.bars if b.player == "A")
        assert a.value == pytest.approx(100, abs=1)

    def test_last_frame_matches_kf2(self) -> None:
        frames = interpolate_frames(self._two_keyframes(), total_frames=60, top_n=10)
        last = frames[-1]
        b = next(bar for bar in last.bars if bar.player == "B")
        assert b.value == pytest.approx(110, abs=1)

    def test_rank_changes(self) -> None:
        """A starts rank 0, B starts rank 1 — by end they should swap."""
        frames = interpolate_frames(self._two_keyframes(), total_frames=60, top_n=10)
        first_a = next(b for b in frames[0].bars if b.player == "A")
        last_a = next(b for b in frames[-1].bars if b.player == "A")
        assert first_a.rank < last_a.rank  # A drops in rank

    def test_requires_two_keyframes(self) -> None:
        with pytest.raises(ValueError, match="at least 2"):
            interpolate_frames(
                [Keyframe(date=datetime(2024, 1, 1), entries=[])],
                total_frames=10,
            )

    def test_progress_range(self) -> None:
        frames = interpolate_frames(self._two_keyframes(), total_frames=30, top_n=10)
        assert frames[0].progress == pytest.approx(0.0, abs=0.01)
        assert frames[-1].progress == pytest.approx(1.0, abs=0.05)

    def test_entering_bar(self) -> None:
        """A bar that only appears in the second keyframe should be entering."""
        kfs = [
            Keyframe(
                date=datetime(2024, 1, 1),
                entries=[BarState(player="A", value=100, rank=0.0)],
            ),
            Keyframe(
                date=datetime(2024, 2, 1),
                entries=[
                    BarState(player="A", value=110, rank=0.0),
                    BarState(player="NEW", value=90, rank=1.0),
                ],
            ),
        ]
        frames = interpolate_frames(kfs, total_frames=20, top_n=10)
        mid = frames[len(frames) // 2]
        new_bar = next((b for b in mid.bars if b.player == "NEW"), None)
        if new_bar:
            assert new_bar.entering is True

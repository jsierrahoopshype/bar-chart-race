"""Configuration dataclasses, video presets, NBA team colours, and helpers."""

from __future__ import annotations

import os
import platform
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Video presets
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class VideoPreset:
    """Resolution preset for output video."""

    name: str
    width: int
    height: int

    @property
    def aspect(self) -> str:
        from math import gcd
        g = gcd(self.width, self.height)
        return f"{self.width // g}:{self.height // g}"


PRESETS: dict[str, VideoPreset] = {
    "reels": VideoPreset("reels", 1080, 1920),
    "youtube": VideoPreset("youtube", 1920, 1080),
    "square": VideoPreset("square", 1080, 1080),
}

# ---------------------------------------------------------------------------
# NBA team colour hex map (all 30 teams — primary colour)
# ---------------------------------------------------------------------------

NBA_TEAM_COLORS: dict[str, str] = {
    "ATL": "#E03A3E",
    "BOS": "#007A33",
    "BKN": "#000000",
    "CHA": "#1D1160",
    "CHI": "#CE1141",
    "CLE": "#860038",
    "DAL": "#00538C",
    "DEN": "#0E2240",
    "DET": "#C8102E",
    "GSW": "#1D428A",
    "HOU": "#CE1141",
    "IND": "#002D62",
    "LAC": "#C8102E",
    "LAL": "#552583",
    "MEM": "#5D76A9",
    "MIA": "#98002E",
    "MIL": "#00471B",
    "MIN": "#0C2340",
    "NOP": "#0C2340",
    "NYK": "#006BB6",
    "OKC": "#007AC1",
    "ORL": "#0077C0",
    "PHI": "#006BB6",
    "PHX": "#1D1160",
    "POR": "#E03A3E",
    "SAC": "#5A2D81",
    "SAS": "#C4CED4",
    "TOR": "#CE1141",
    "UTA": "#002B5C",
    "WAS": "#002B5C",
}

# Fallback palette used when no team mapping exists.
FALLBACK_PALETTE: list[str] = [
    "#4E79A7", "#F28E2B", "#E15759", "#76B7B2", "#59A14F",
    "#EDC948", "#B07AA1", "#FF9DA7", "#9C755F", "#BAB0AC",
    "#AF7AA1", "#D37295", "#FABFD2", "#B6992D", "#499894",
    "#86BCB6", "#8CD17D", "#F1CE63", "#A0CBE8", "#FFBE7D",
]

# ---------------------------------------------------------------------------
# Font resolution helpers
# ---------------------------------------------------------------------------

_LINUX_FONT_DIR = Path("/usr/share/fonts/truetype/google-fonts")
_WIN_FONT_DIR = Path("C:/Windows/Fonts")


_WINDOWS_FALLBACKS: dict[str, str] = {
    "bold": "arialbd.ttf",
    "medium": "arial.ttf",
    "regular": "arial.ttf",
    "light": "arial.ttf",
}


def _find_font(name: str, weight: str = "") -> str:
    """Return an absolute path to *name* (e.g. ``Poppins-Bold.ttf``).

    Search order: Linux google-fonts dir → Windows Fonts dir (Poppins)
    → Windows Fonts dir (Arial fallback) → bare name.
    """
    for base in (_LINUX_FONT_DIR, _WIN_FONT_DIR):
        candidate = base / name
        if candidate.is_file():
            return str(candidate)

    # Windows Arial fallback when Poppins is not installed.
    if weight and weight in _WINDOWS_FALLBACKS:
        fallback = _WIN_FONT_DIR / _WINDOWS_FALLBACKS[weight]
        if fallback.is_file():
            return str(fallback)

    return name  # last resort — let PIL try its own lookup


def default_fonts() -> dict[str, str]:
    """Return a mapping of weight → font file path."""
    return {
        "bold": _find_font("Poppins-Bold.ttf", "bold"),
        "medium": _find_font("Poppins-Medium.ttf", "medium"),
        "regular": _find_font("Poppins-Regular.ttf", "regular"),
        "light": _find_font("Poppins-Light.ttf", "light"),
    }


# ---------------------------------------------------------------------------
# Main Config dataclass
# ---------------------------------------------------------------------------

@dataclass
class Config:
    """Full configuration for a bar-chart-race render."""

    # --- data source (one of these should be set) -------------------------
    input_path: Optional[str] = None
    gsheet_url: Optional[str] = None
    sheet_name: Optional[str] = None
    stat_column: Optional[str] = None

    # --- date filtering ----------------------------------------------------
    date_start: Optional[str] = None
    date_end: Optional[str] = None

    # --- output ------------------------------------------------------------
    output: str = "output.mp4"
    preset: str = "reels"

    # --- video parameters --------------------------------------------------
    fps: int = 60
    duration_sec: float = 30.0
    bitrate: str = "12M"
    top_n: int = 10

    # --- titles & branding -------------------------------------------------
    title: str = ""
    subtitle: str = ""
    watermark: str = ""

    # --- theme -------------------------------------------------------------
    theme: str = "midnight-premium"

    # --- visual tweaks -----------------------------------------------------
    bg_gradient: tuple[str, str] = ("#0f0c29", "#302b63")
    use_team_colors: bool = True
    vignette: bool = True
    noise: bool = True
    leader_glow: bool = True
    rounded_bars: bool = True
    bar_shadow: bool = True

    # --- assets directories ------------------------------------------------
    headshot_dir: Optional[str] = None
    logo_dir: Optional[str] = None

    # --- axis --------------------------------------------------------------
    axis_mode: str = "auto"  # "auto" or "locked"

    # --- fonts (resolved at runtime) ---------------------------------------
    font_bold: str = ""
    font_medium: str = ""
    font_regular: str = ""
    font_light: str = ""

    # --- intro / outro holds -----------------------------------------------
    intro_hold_sec: float = 0.0
    outro_hold_sec: float = 5.0

    # --- overlays -------------------------------------------------------------
    show_gap_alerts: bool = True
    gap_alert_threshold: float = 0.15   # 15 %

    def __post_init__(self) -> None:
        fonts = default_fonts()
        if not self.font_bold:
            self.font_bold = fonts["bold"]
        if not self.font_medium:
            self.font_medium = fonts["medium"]
        if not self.font_regular:
            self.font_regular = fonts["regular"]
        if not self.font_light:
            self.font_light = fonts["light"]

    # -- helpers -----------------------------------------------------------

    def get_preset(self) -> VideoPreset:
        """Return the resolved :class:`VideoPreset`."""
        key = self.preset.lower()
        if key not in PRESETS:
            raise ValueError(
                f"Unknown preset {self.preset!r}. "
                f"Choose from: {', '.join(PRESETS)}"
            )
        return PRESETS[key]

    @classmethod
    def from_yaml(cls, path: str | Path) -> "Config":
        """Load config from a YAML file, ignoring unknown keys."""
        import yaml  # deferred so yaml is only needed when used

        with open(path, "r", encoding="utf-8") as fh:
            raw: dict = yaml.safe_load(fh) or {}

        # Only pass keys that match Config fields.
        valid = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {}
        for k, v in raw.items():
            if k in valid:
                # Special handling for bg_gradient (list → tuple).
                if k == "bg_gradient" and isinstance(v, list):
                    v = tuple(v)
                filtered[k] = v
        return cls(**filtered)

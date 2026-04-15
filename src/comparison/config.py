"""Configuration for the comparison slideshow tool."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Reuse VideoPreset from bar_race.
from bar_race.config import VideoPreset, PRESETS  # noqa: F401


# ---------------------------------------------------------------------------
# Comparison themes
# ---------------------------------------------------------------------------

COMPARISON_THEMES: dict[str, dict[str, str | int]] = {
    "dark": {
        "category_bg": "#f0f0f0",
        "category_text_color": "#000000",
        "category_font_size": 22,
        "winner_bg": "#CC0000",
        "winner_text_color": "#FFFFFF",
        "winner_font_size": 24,
        "other_bg": "#2a2a2a",
        "other_text_color": "#FFFFFF",
        "other_font_size": 24,
        "headshot_bg": "#0097a7",
        "card_border_color": "#333333",
        "frame_bg": "",
    },
    "cream-serif": {
        "category_bg": "#F0E4C8",
        "category_text_color": "#1a1a1a",
        "category_font_size": 22,
        "winner_bg": "#8B7535",
        "winner_text_color": "#FFFFFF",
        "winner_font_size": 24,
        "other_bg": "#F0E4C8",
        "other_text_color": "#1a1a1a",
        "other_font_size": 24,
        "headshot_bg": "#F0E4C8",
        "card_border_color": "#D4C49A",
        "frame_bg": "#F0E4C8",
    },
}


@dataclass
class ComparisonConfig:
    """Full configuration for a comparison slideshow."""

    input_path: str = ""
    output: str = "comparison.mp4"
    preset: str = "square"

    title: str = ""
    subtitle: str = ""

    categories_per_slide: int = 3
    slide_duration: float = 3.0
    crossfade_duration: float = 0.3
    outro_hold: float = 5.0
    fps: int = 30

    highlight_winner: bool = True
    winner_color: str = "#CC0000"
    runner_up_color: str = "#DAA520"
    loser_color: str = "#2a2a2a"

    headshot_dir: str = "assets/headshots"
    bg_image: str = "assets/backgrounds/mesh3.jpg"
    font_dir: str = "assets/fonts"

    lowest_is_better: list[str] = field(default_factory=list)

    # Filtering / ordering.
    selected_players: list[str] = field(default_factory=list)
    selected_categories: list[str] = field(default_factory=list)
    categories_order: list[str] = field(default_factory=list)

    # Visual tuning.
    cards_visible: int = 4
    scroll_speed: float = 1.5

    # Theme.
    comparison_theme: str = "dark"
    frame_bg: str = ""  # empty = use bg_image or dark fallback

    # Card style — colors, fonts.
    category_bg: str = "#f0f0f0"
    category_text_color: str = "#000000"
    category_font_size: int = 22
    winner_bg: str = "#CC0000"
    winner_text_color: str = "#FFFFFF"
    winner_font_size: int = 24
    other_bg: str = "#2a2a2a"
    other_text_color: str = "#FFFFFF"
    other_font_size: int = 24
    headshot_bg: str = "#0097a7"
    card_border_color: str = "#333333"

    def __post_init__(self) -> None:
        # Apply theme defaults for any fields still at their default.
        if self.comparison_theme in COMPARISON_THEMES:
            theme = COMPARISON_THEMES[self.comparison_theme]
            defaults = COMPARISON_THEMES["dark"]
            for key, val in theme.items():
                current = getattr(self, key, None)
                default_val = defaults.get(key)
                # Only override if the field is still at its dark-theme default.
                if current is not None and current == default_val:
                    setattr(self, key, val)

    def get_preset(self) -> VideoPreset:
        key = self.preset.lower()
        if key not in PRESETS:
            raise ValueError(f"Unknown preset {self.preset!r}. Choose from: {', '.join(PRESETS)}")
        return PRESETS[key]

    def resolve_path(self, relative: str) -> str:
        """Resolve a relative asset path against PROJECT_ROOT."""
        if os.path.isabs(relative):
            return relative
        return os.path.join(PROJECT_ROOT, relative)

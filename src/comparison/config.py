"""Configuration for the comparison slideshow tool."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Reuse VideoPreset from bar_race.
from bar_race.config import VideoPreset, PRESETS  # noqa: F401


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
    scroll_speed: float = 1.5  # seconds per card crossing center

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

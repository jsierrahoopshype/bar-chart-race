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

    headshot_dir: str = "assets/headshots"
    bg_image: str = "assets/backgrounds/mesh3.jpg"
    font_dir: str = "assets/fonts"

    lowest_is_better: list[str] = field(default_factory=list)

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

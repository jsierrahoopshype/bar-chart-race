"""Pillow-based slide renderer for comparison slideshows."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from comparison.config import ComparisonConfig, PROJECT_ROOT
from comparison.ingest import ComparisonData

# Reuse headshot matching from bar_race.
from bar_race.render import _find_headshot_file, _load_font


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _load_bg(path: str, width: int, height: int) -> Image.Image:
    """Load a background image with cover-crop to exact size."""
    img = Image.open(path).convert("RGB")
    src_w, src_h = img.size
    scale = max(width / src_w, height / src_h)
    new_w, new_h = int(src_w * scale), int(src_h * scale)
    img = img.resize((new_w, new_h), Image.LANCZOS)
    left = (new_w - width) // 2
    top = (new_h - height) // 2
    return img.crop((left, top, left + width, top + height)).convert("RGBA")


def _resolve_fonts(font_dir: str) -> dict[str, str]:
    """Resolve font paths with fallback to system fonts."""
    base = font_dir if os.path.isabs(font_dir) else os.path.join(PROJECT_ROOT, font_dir)
    custom = {
        "bold": os.path.join(base, "Futura_Today_Bold.otf"),
        "medium": os.path.join(base, "Futura_Today_DemiBold.otf"),
        "regular": os.path.join(base, "Futura_Today_Normal.otf"),
        "light": os.path.join(base, "Futura_Today_Light.otf"),
    }
    # Use custom if files exist and are non-empty, else fall back.
    result: dict[str, str] = {}
    for weight, path in custom.items():
        if os.path.isfile(path) and os.path.getsize(path) > 0:
            result[weight] = path
        else:
            result[weight] = ""  # _load_font will use default
    return result


def _text_size(
    draw: ImageDraw.Draw,
    text: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
) -> tuple[int, int]:
    try:
        bbox = font.getbbox(text)
        return bbox[2] - bbox[0], bbox[3] - bbox[1]
    except AttributeError:
        return draw.textsize(text, font=font)  # type: ignore[attr-defined]


def _draw_rounded_rect(
    draw: ImageDraw.Draw,
    xy: tuple[int, int, int, int],
    radius: int,
    fill: tuple[int, ...] | None = None,
) -> None:
    x1, y1, x2, y2 = xy
    if x2 <= x1 or y2 <= y1:
        return
    r = min(radius, (y2 - y1) // 2, (x2 - x1) // 2)
    if r < 1:
        draw.rectangle(xy, fill=fill)
    else:
        draw.rounded_rectangle(xy, radius=r, fill=fill)


# ---------------------------------------------------------------------------
# Slide renderer
# ---------------------------------------------------------------------------

class SlideRenderer:
    """Renders individual comparison slides."""

    def __init__(self, cfg: ComparisonConfig) -> None:
        self.cfg = cfg
        self.preset = cfg.get_preset()
        self.W = self.preset.width
        self.H = self.preset.height

        # Resolve fonts.
        fonts = _resolve_fonts(cfg.font_dir)
        scale = min(self.W, self.H) / 1080

        self.font_title = _load_font(fonts["bold"], max(12, int(40 * scale)))
        self.font_subtitle = _load_font(fonts["medium"], max(10, int(22 * scale)))
        self.font_player_name = _load_font(fonts["bold"], max(10, int(20 * scale)))
        self.font_cat_label = _load_font(fonts["medium"], max(10, int(22 * scale)))
        self.font_cat_value = _load_font(fonts["bold"], max(12, int(28 * scale)))
        self.font_small = _load_font(fonts["regular"], max(8, int(14 * scale)))

        # Load background.
        bg_path = cfg.resolve_path(cfg.bg_image)
        if os.path.isfile(bg_path):
            self._bg = _load_bg(bg_path, self.W, self.H)
        else:
            self._bg = Image.new("RGBA", (self.W, self.H), (26, 26, 26, 255))

        # Resolve headshot directory.
        self._hs_dir = cfg.resolve_path(cfg.headshot_dir)

        # Colors.
        self._winner_rgb = _hex_to_rgb(cfg.winner_color)
        self._runner_up_rgb = _hex_to_rgb(cfg.runner_up_color)

    def _load_headshot(self, player: str, size: int) -> Optional[Image.Image]:
        """Load and resize a player headshot."""
        if not os.path.isdir(self._hs_dir):
            return None
        path = _find_headshot_file(player, self._hs_dir)
        if path is None:
            return None
        try:
            img = Image.open(str(path)).convert("RGBA")
            img = img.resize((size, size), Image.LANCZOS)
            return img
        except Exception:
            return None

    def render_slide(
        self,
        data: ComparisonData,
        categories: list[str],
        slide_num: int,
        total_slides: int,
    ) -> Image.Image:
        """Render a single comparison slide."""
        img = self._bg.copy()
        draw = ImageDraw.Draw(img)

        W, H = self.W, self.H
        players = data.players
        n_players = len(players)
        n_cats = len(categories)

        # --- Layout zones (percentages of height) ---
        title_zone_top = int(H * 0.02)
        headshot_zone_top = int(H * 0.10)
        headshot_zone_h = int(H * 0.35)
        name_zone_top = headshot_zone_top + headshot_zone_h + int(H * 0.01)
        cat_zone_top = name_zone_top + int(H * 0.05)
        cat_zone_bottom = int(H * 0.95)

        margin_x = int(W * 0.06)
        content_w = W - margin_x * 2

        # --- Title + subtitle ---
        if self.cfg.title:
            tw, _ = _text_size(draw, self.cfg.title, self.font_title)
            tx = (W - tw) // 2
            draw.text((tx, title_zone_top), self.cfg.title,
                      fill=(255, 255, 255, 240), font=self.font_title)
        if self.cfg.subtitle:
            sw, _ = _text_size(draw, self.cfg.subtitle, self.font_subtitle)
            sx = (W - sw) // 2
            draw.text((sx, title_zone_top + int(H * 0.04)), self.cfg.subtitle,
                      fill=(200, 200, 200, 200), font=self.font_subtitle)

        # --- Player columns ---
        col_w = content_w // max(n_players, 1)

        # Headshots.
        hs_size = min(int(headshot_zone_h * 0.9), col_w - 20)
        for i, player in enumerate(players):
            col_center = margin_x + col_w * i + col_w // 2
            hs = self._load_headshot(player, hs_size)
            if hs is not None:
                hs_x = col_center - hs_size // 2
                hs_y = headshot_zone_top + (headshot_zone_h - hs_size) // 2
                img.paste(hs, (hs_x, hs_y), hs)
                draw = ImageDraw.Draw(img)

        # Player names.
        for i, player in enumerate(players):
            col_center = margin_x + col_w * i + col_w // 2
            nw, nh = _text_size(draw, player, self.font_player_name)
            nx = col_center - nw // 2
            draw.text((nx, name_zone_top), player,
                      fill=(255, 255, 255, 230), font=self.font_player_name)

        # --- Category rows ---
        if n_cats > 0:
            cat_avail_h = cat_zone_bottom - cat_zone_top
            row_h = min(cat_avail_h // n_cats, int(H * 0.12))
            row_gap = max(4, int(row_h * 0.12))

            for ci, cat in enumerate(categories):
                row_y = cat_zone_top + ci * (row_h + row_gap)
                if row_y + row_h > cat_zone_bottom:
                    break

                cat_vals = data.values.get(cat, {})

                # Determine winner and runner-up.
                player_vals = [(p, cat_vals.get(p, 0.0)) for p in players]
                is_lower_better = cat in self.cfg.lowest_is_better

                sorted_vals = sorted(
                    player_vals, key=lambda x: x[1],
                    reverse=not is_lower_better,
                )
                winner = sorted_vals[0][0] if sorted_vals else ""
                runner_up = sorted_vals[1][0] if len(sorted_vals) > 1 else ""
                # Only mark runner-up if their value differs from winner.
                if sorted_vals and len(sorted_vals) > 1:
                    if sorted_vals[0][1] == sorted_vals[1][1]:
                        runner_up = ""  # tie — both are winners
                        winner = ""  # highlight neither on tie

                # Category label (left side).
                cat_label_w = int(content_w * 0.28)
                cat_label_x = margin_x
                _draw_rounded_rect(
                    draw,
                    (cat_label_x, row_y, cat_label_x + cat_label_w, row_y + row_h),
                    radius=6,
                    fill=(40, 40, 40, 200),
                )
                lw, lh = _text_size(draw, cat, self.font_cat_label)
                draw.text(
                    (cat_label_x + 12, row_y + (row_h - lh) // 2),
                    cat, fill=(255, 255, 255, 220), font=self.font_cat_label,
                )

                # Value cells.
                val_area_x = cat_label_x + cat_label_w + 8
                val_area_w = content_w - cat_label_w - 8
                cell_w = val_area_w // max(n_players, 1)
                cell_gap = 6

                for pi, player in enumerate(players):
                    cx = val_area_x + cell_w * pi + cell_gap // 2
                    cw = cell_w - cell_gap

                    val = cat_vals.get(player, 0.0)
                    val_text = f"{val:,.0f}" if val == int(val) else f"{val:,.1f}"

                    # Cell color based on ranking.
                    if self.cfg.highlight_winner and player == winner:
                        cell_fill = (*self._winner_rgb, 230)
                        text_fill = (255, 255, 255, 255)
                    elif self.cfg.highlight_winner and player == runner_up:
                        cell_fill = (*self._runner_up_rgb, 200)
                        text_fill = (30, 30, 30, 255)
                    else:
                        cell_fill = (60, 60, 60, 180)
                        text_fill = (200, 200, 200, 230)

                    _draw_rounded_rect(
                        draw,
                        (cx, row_y, cx + cw, row_y + row_h),
                        radius=6,
                        fill=cell_fill,
                    )

                    vw, vh = _text_size(draw, val_text, self.font_cat_value)
                    draw.text(
                        (cx + (cw - vw) // 2, row_y + (row_h - vh) // 2),
                        val_text, fill=text_fill, font=self.font_cat_value,
                    )

        # --- Slide indicator ---
        if total_slides > 1:
            ind_text = f"{slide_num}/{total_slides}"
            iw, ih = _text_size(draw, ind_text, self.font_small)
            draw.text(
                (W - margin_x - iw, H - int(H * 0.03)),
                ind_text, fill=(150, 150, 150, 120), font=self.font_small,
            )

        return img

    def render_slide_rgb_bytes(
        self,
        data: ComparisonData,
        categories: list[str],
        slide_num: int,
        total_slides: int,
    ) -> bytes:
        """Render a slide and return raw RGB bytes."""
        return self.render_slide(data, categories, slide_num, total_slides).convert("RGB").tobytes()

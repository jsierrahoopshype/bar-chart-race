"""Pillow-based frame renderer — horizontal conveyor belt of stat cards."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from comparison.config import ComparisonConfig, PROJECT_ROOT
from comparison.ingest import ComparisonData

from bar_race.render import _find_headshot_file, _load_font


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _load_bg(path: str, width: int, height: int) -> Image.Image:
    """Load background image, cover-crop to exact size."""
    img = Image.open(path).convert("RGB")
    src_w, src_h = img.size
    scale = max(width / src_w, height / src_h)
    new_w, new_h = int(src_w * scale), int(src_h * scale)
    img = img.resize((new_w, new_h), Image.LANCZOS)
    left = (new_w - width) // 2
    top = (new_h - height) // 2
    return img.crop((left, top, left + width, top + height)).convert("RGBA")


def _resolve_fonts(font_dir: str) -> dict[str, str]:
    base = font_dir if os.path.isabs(font_dir) else os.path.join(PROJECT_ROOT, font_dir)
    custom = {
        "bold": os.path.join(base, "Futura_Today_Bold.otf"),
        "medium": os.path.join(base, "Futura_Today_DemiBold.otf"),
        "regular": os.path.join(base, "Futura_Today_Normal.otf"),
        "light": os.path.join(base, "Futura_Today_Light.otf"),
    }
    result: dict[str, str] = {}
    for weight, path in custom.items():
        if os.path.isfile(path) and os.path.getsize(path) > 0:
            result[weight] = path
        else:
            result[weight] = ""
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
    outline: tuple[int, ...] | None = None,
    width: int = 1,
) -> None:
    x1, y1, x2, y2 = xy
    if x2 <= x1 or y2 <= y1:
        return
    r = min(radius, (y2 - y1) // 2, (x2 - x1) // 2)
    if r < 1:
        draw.rectangle(xy, fill=fill, outline=outline, width=width)
    else:
        draw.rounded_rectangle(xy, radius=r, fill=fill, outline=outline, width=width)


def _interleave_categories(
    data: ComparisonData,
    lowest_is_better: list[str],
) -> list[str]:
    """Re-order categories to alternate wins between players."""
    players = data.players
    if len(players) < 2:
        return list(data.categories)

    p0, p1 = players[0], players[1]
    p0_wins: list[str] = []
    p1_wins: list[str] = []
    ties: list[str] = []

    for cat in data.categories:
        vals = data.values.get(cat, {})
        v0, v1 = vals.get(p0, 0.0), vals.get(p1, 0.0)
        lower = cat in lowest_is_better
        if (not lower and v0 > v1) or (lower and v0 < v1):
            p0_wins.append(cat)
        elif (not lower and v1 > v0) or (lower and v1 < v0):
            p1_wins.append(cat)
        else:
            ties.append(cat)

    # Alternate: p0, p1, p0, p1, ..., then ties at the end.
    result: list[str] = []
    i0, i1 = 0, 0
    turn = 0  # 0 = p0, 1 = p1
    while i0 < len(p0_wins) or i1 < len(p1_wins):
        if turn == 0 and i0 < len(p0_wins):
            result.append(p0_wins[i0])
            i0 += 1
        elif turn == 1 and i1 < len(p1_wins):
            result.append(p1_wins[i1])
            i1 += 1
        elif i0 < len(p0_wins):
            result.append(p0_wins[i0])
            i0 += 1
        else:
            result.append(p1_wins[i1])
            i1 += 1
        turn = 1 - turn
    result.extend(ties)
    return result


# ---------------------------------------------------------------------------
# Card data (precomputed per category)
# ---------------------------------------------------------------------------

class _CardData:
    """Precomputed data for one stat card."""

    __slots__ = ("category", "player_vals", "winner", "runner_up")

    def __init__(
        self,
        category: str,
        player_vals: list[tuple[str, float]],
        winner: str,
        runner_up: str,
    ):
        self.category = category
        self.player_vals = player_vals
        self.winner = winner
        self.runner_up = runner_up


# ---------------------------------------------------------------------------
# ConveyorRenderer
# ---------------------------------------------------------------------------

class ConveyorRenderer:
    """Renders frames of the horizontal conveyor belt animation."""

    def __init__(self, cfg: ComparisonConfig, data: ComparisonData) -> None:
        self.cfg = cfg
        self.data = data
        self.preset = cfg.get_preset()
        self.W = self.preset.width
        self.H = self.preset.height

        fonts = _resolve_fonts(cfg.font_dir)
        s = min(self.W, self.H) / 1080  # base scale

        self.font_title = _load_font(fonts["bold"], max(14, int(40 * s)))
        self.font_subtitle = _load_font(fonts["medium"], max(10, int(22 * s)))
        self.font_cat = _load_font(fonts["bold"], max(10, int(22 * s)))
        self.font_name = _load_font(fonts["bold"], max(10, int(24 * s)))
        self.font_value = _load_font(fonts["bold"], max(16, int(56 * s)))
        self.font_small = _load_font(fonts["regular"], max(8, int(14 * s)))

        # Background.
        bg_path = cfg.resolve_path(cfg.bg_image)
        if os.path.isfile(bg_path):
            self._bg = _load_bg(bg_path, self.W, self.H)
        else:
            self._bg = Image.new("RGBA", (self.W, self.H), (26, 26, 26, 255))

        # Headshot directory.
        self._hs_dir = cfg.resolve_path(cfg.headshot_dir)

        # Colors.
        self._winner_rgb = _hex_to_rgb(cfg.winner_color)
        self._runner_up_rgb = _hex_to_rgb(cfg.runner_up_color)

        # Card layout constants.
        self.card_w = int(self.W * 0.32)
        self.card_gap = int(self.W * 0.02)
        self.card_stride = self.card_w + self.card_gap
        self.card_top = int(self.H * 0.12)
        self.card_h = int(self.H * 0.83)
        self.card_radius = 12

        # Precompute cards in display order.
        ordered = _interleave_categories(data, cfg.lowest_is_better)
        self.cards: list[_CardData] = []
        for cat in ordered:
            vals = data.values.get(cat, {})
            player_vals = [(p, vals.get(p, 0.0)) for p in data.players]
            lower = cat in cfg.lowest_is_better
            ranked = sorted(player_vals, key=lambda x: x[1], reverse=not lower)
            winner = ranked[0][0] if ranked else ""
            runner_up = ranked[1][0] if len(ranked) > 1 else ""
            if len(ranked) >= 2 and ranked[0][1] == ranked[1][1]:
                winner = ""
                runner_up = ""
            self.cards.append(_CardData(cat, player_vals, winner, runner_up))

        # Headshot cache.
        self._hs_cache: dict[str, Optional[Image.Image]] = {}

        # Pre-render static title area onto background.
        self._bg_with_title = self._bg.copy()
        draw = ImageDraw.Draw(self._bg_with_title)
        title_y = int(self.H * 0.02)
        if cfg.title:
            tw, _ = _text_size(draw, cfg.title, self.font_title)
            draw.text(((self.W - tw) // 2, title_y), cfg.title,
                      fill=(255, 255, 255, 240), font=self.font_title)
        if cfg.subtitle:
            sw, _ = _text_size(draw, cfg.subtitle, self.font_subtitle)
            sub_y = title_y + int(self.H * 0.045)
            draw.text(((self.W - sw) // 2, sub_y), cfg.subtitle,
                      fill=(200, 200, 200, 200), font=self.font_subtitle)
        # Thin accent line.
        line_y = int(self.H * 0.10)
        draw.line([(int(self.W * 0.1), line_y), (int(self.W * 0.9), line_y)],
                  fill=(255, 255, 255, 40), width=1)

    def _get_headshot(self, player: str, size: int) -> Optional[Image.Image]:
        key = f"{player}_{size}"
        if key in self._hs_cache:
            return self._hs_cache[key]
        hs = None
        if os.path.isdir(self._hs_dir):
            path = _find_headshot_file(player, self._hs_dir)
            if path is not None:
                try:
                    raw = Image.open(str(path)).convert("RGBA")
                    # Crop to top 75% (face focus), then resize to square.
                    w, h = raw.size
                    crop_h = int(h * 0.75)
                    raw = raw.crop((0, 0, w, crop_h))
                    raw = raw.resize((size, size), Image.LANCZOS)
                    hs = raw
                except Exception:
                    pass
        self._hs_cache[key] = hs
        return hs

    def _render_card(self, card: _CardData, card_img: Image.Image) -> None:
        """Draw one stat card onto card_img (RGBA, size card_w x card_h)."""
        draw = ImageDraw.Draw(card_img)
        cw, ch = card_img.size
        players = self.data.players
        n_players = len(players)

        # Card background.
        _draw_rounded_rect(draw, (0, 0, cw - 1, ch - 1), self.card_radius,
                           fill=(255, 255, 255, 20),
                           outline=(255, 255, 255, 38), width=1)

        # Top accent bar (winner's color).
        accent_rgb = self._winner_rgb if card.winner else (180, 180, 180)
        _draw_rounded_rect(draw, (0, 0, cw - 1, 5), self.card_radius,
                           fill=(*accent_rgb, 180))

        # Category title.
        cat_text = card.category.upper()
        ct_w, ct_h = _text_size(draw, cat_text, self.font_cat)
        draw.text(((cw - ct_w) // 2, 16), cat_text,
                  fill=(255, 255, 255, 200), font=self.font_cat)

        # Player sections: divide remaining height evenly.
        section_top = 16 + ct_h + 12
        section_h = (ch - section_top - 10) // max(n_players, 1)

        hs_size = min(int(section_h * 0.50), cw - 40)

        for pi, (player, val) in enumerate(card.player_vals):
            sy = section_top + pi * section_h
            mid_x = cw // 2

            # Winner / runner-up background strip.
            strip_y = sy + 2
            strip_h = section_h - 4
            if self.cfg.highlight_winner and player == card.winner:
                _draw_rounded_rect(
                    draw, (6, strip_y, cw - 6, strip_y + strip_h), 8,
                    fill=(*self._winner_rgb, 50))
            elif self.cfg.highlight_winner and player == card.runner_up:
                _draw_rounded_rect(
                    draw, (6, strip_y, cw - 6, strip_y + strip_h), 8,
                    fill=(*self._runner_up_rgb, 40))

            # Headshot.
            hs = self._get_headshot(player, hs_size)
            if hs is not None:
                hx = mid_x - hs_size // 2
                hy = sy + 8
                card_img.paste(hs, (hx, hy), hs)
                draw = ImageDraw.Draw(card_img)

            # Player name.
            name_y = sy + 8 + hs_size + 4
            nw, nh = _text_size(draw, player, self.font_name)
            draw.text(((cw - nw) // 2, name_y), player,
                      fill=(255, 255, 255, 230), font=self.font_name)

            # Value.
            val_text = f"{val:,.0f}" if val == int(val) else f"{val:,.1f}"
            vw, vh = _text_size(draw, val_text, self.font_value)
            val_y = name_y + nh + 4
            # Winner value in accent color.
            if self.cfg.highlight_winner and player == card.winner:
                val_color = (*self._winner_rgb, 255)
            elif self.cfg.highlight_winner and player == card.runner_up:
                val_color = (*self._runner_up_rgb, 255)
            else:
                val_color = (200, 200, 200, 220)
            draw.text(((cw - vw) // 2, val_y), val_text,
                      fill=val_color, font=self.font_value)

    def _prerender_cards(self) -> list[Image.Image]:
        """Pre-render all card images."""
        card_images: list[Image.Image] = []
        for card in self.cards:
            card_img = Image.new("RGBA", (self.card_w, self.card_h), (0, 0, 0, 0))
            self._render_card(card, card_img)
            card_images.append(card_img)
        return card_images

    def compute_timing(self) -> dict:
        """Compute animation timing parameters."""
        n_cards = len(self.cards)
        fps = self.cfg.fps

        # Scroll speed: each card is fully visible for ~1.8 seconds.
        # A card enters from the right, crosses the frame, exits left.
        # Distance from right edge entering to left edge exiting:
        #   frame_width + card_width
        # Time to cross: ~(card_stride / pixels_per_frame)
        # We want card visible ~1.8s → pixels_per_frame = card_stride / (1.8 * fps)
        card_visible_sec = 1.8
        pixels_per_frame = self.card_stride / (card_visible_sec * fps)

        # Total scroll distance: all cards need to pass through.
        # First card starts at right edge (x = W), last card exits at left (x = -card_w).
        total_scroll = self.W + n_cards * self.card_stride
        scroll_frames = int(total_scroll / pixels_per_frame)

        intro_frames = int(5.0 * fps)
        outro_frames = int(3.0 * fps)
        total_frames = intro_frames + scroll_frames + outro_frames

        return {
            "pixels_per_frame": pixels_per_frame,
            "intro_frames": intro_frames,
            "scroll_frames": scroll_frames,
            "outro_frames": outro_frames,
            "total_frames": total_frames,
        }

    def render_frame(
        self,
        frame_idx: int,
        timing: dict,
        card_images: list[Image.Image],
    ) -> Image.Image:
        """Render a single animation frame."""
        img = self._bg_with_title.copy()

        intro = timing["intro_frames"]
        ppf = timing["pixels_per_frame"]

        if frame_idx < intro:
            # Intro: just title, no cards.
            return img

        scroll_idx = frame_idx - intro
        scroll_offset = scroll_idx * ppf

        for ci, card_img in enumerate(card_images):
            # Card x: starts at right edge, moves left.
            card_x = int(self.W - scroll_offset + ci * self.card_stride)

            # Only render if card is at least partially visible.
            if card_x > self.W:
                continue
            if card_x + self.card_w < 0:
                continue

            img.paste(card_img, (card_x, self.card_top), card_img)

        return img

    def render_frame_rgb_bytes(
        self,
        frame_idx: int,
        timing: dict,
        card_images: list[Image.Image],
    ) -> bytes:
        return self.render_frame(frame_idx, timing, card_images).convert("RGB").tobytes()

    def render_card_png(self, card_idx: int) -> Image.Image:
        """Render a single card as a standalone PNG with background."""
        # Create a card-sized frame with background.
        pad = 40
        out_w = self.card_w + pad * 2
        out_h = self.card_h + pad * 2
        bg_path = self.cfg.resolve_path(self.cfg.bg_image)
        if os.path.isfile(bg_path):
            bg = _load_bg(bg_path, out_w, out_h)
        else:
            bg = Image.new("RGBA", (out_w, out_h), (26, 26, 26, 255))
        card_img = Image.new("RGBA", (self.card_w, self.card_h), (0, 0, 0, 0))
        self._render_card(self.cards[card_idx], card_img)
        bg.paste(card_img, (pad, pad), card_img)
        return bg

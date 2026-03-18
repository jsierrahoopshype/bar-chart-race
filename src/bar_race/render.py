"""Pillow/PIL frame renderer — NO matplotlib.

Renders each :class:`~bar_race.animate.FrameState` into a raw RGBA
:class:`PIL.Image.Image`.
"""

from __future__ import annotations

import math
import os
import random
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from bar_race.animate import BarState, FrameState
from bar_race.config import (
    Config,
    FALLBACK_PALETTE,
    NBA_TEAM_COLORS,
    VideoPreset,
)

# ---------------------------------------------------------------------------
# Colour helpers
# ---------------------------------------------------------------------------

def _hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _rgb_to_hex(r: int, g: int, b: int) -> str:
    return f"#{r:02x}{g:02x}{b:02x}"


def _lerp_color(
    c1: tuple[int, int, int],
    c2: tuple[int, int, int],
    t: float,
) -> tuple[int, int, int]:
    return (
        int(c1[0] + (c2[0] - c1[0]) * t),
        int(c1[1] + (c2[1] - c1[1]) * t),
        int(c1[2] + (c2[2] - c1[2]) * t),
    )


def _smoothstep(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return t * t * (3.0 - 2.0 * t)


def _lighten(rgb: tuple[int, int, int], amount: float = 0.3) -> tuple[int, int, int]:
    return tuple(min(255, int(c + (255 - c) * amount)) for c in rgb)  # type: ignore[return-value]


def _darken(rgb: tuple[int, int, int], amount: float = 0.3) -> tuple[int, int, int]:
    return tuple(max(0, int(c * (1 - amount))) for c in rgb)  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Player colour lookup
# ---------------------------------------------------------------------------

_player_color_cache: dict[str, str] = {}
_palette_idx = 0


def _color_for_bar(bar: BarState, use_team: bool) -> str:
    global _palette_idx
    if bar.player in _player_color_cache:
        return _player_color_cache[bar.player]

    if use_team and bar.team and bar.team in NBA_TEAM_COLORS:
        color = NBA_TEAM_COLORS[bar.team]
    else:
        color = FALLBACK_PALETTE[_palette_idx % len(FALLBACK_PALETTE)]
        _palette_idx += 1

    _player_color_cache[bar.player] = color
    return color


# ---------------------------------------------------------------------------
# Font loading
# ---------------------------------------------------------------------------

def _load_font(path: str, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    try:
        return ImageFont.truetype(path, size)
    except (OSError, IOError):
        return ImageFont.load_default()


# ---------------------------------------------------------------------------
# Background generation
# ---------------------------------------------------------------------------

def _render_gradient(
    width: int,
    height: int,
    c1: tuple[int, int, int],
    c2: tuple[int, int, int],
) -> Image.Image:
    """Vertical gradient using smoothstep interpolation."""
    img = Image.new("RGBA", (width, height))
    pixels = img.load()
    for y in range(height):
        t = _smoothstep(y / max(height - 1, 1))
        r, g, b = _lerp_color(c1, c2, t)
        for x in range(width):
            pixels[x, y] = (r, g, b, 255)  # type: ignore[index]
    return img


def _render_gradient_np(
    width: int,
    height: int,
    c1: tuple[int, int, int],
    c2: tuple[int, int, int],
) -> Image.Image:
    """Vectorised gradient — much faster than per-pixel loop."""
    ys = np.linspace(0, 1, height, dtype=np.float32)
    ts = ys * ys * (3.0 - 2.0 * ys)  # smoothstep
    ts = ts[:, None]  # (H, 1)
    c1a = np.array(c1, dtype=np.float32)
    c2a = np.array(c2, dtype=np.float32)
    rgb = (c1a + (c2a - c1a) * ts).clip(0, 255).astype(np.uint8)
    # Expand to (H, W, 3)
    rgb = np.broadcast_to(rgb[:, None, :], (height, width, 3)).copy()
    alpha = np.full((height, width, 1), 255, dtype=np.uint8)
    rgba = np.concatenate([rgb, alpha], axis=2)
    return Image.fromarray(rgba, "RGBA")


# ---------------------------------------------------------------------------
# Overlays
# ---------------------------------------------------------------------------

def _apply_vignette(img: Image.Image) -> Image.Image:
    w, h = img.size
    vignette = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(vignette)
    cx, cy = w / 2, h / 2
    max_r = math.sqrt(cx * cx + cy * cy)
    steps = 40
    for i in range(steps, 0, -1):
        frac = i / steps
        r = int(max_r * frac)
        alpha = int(80 * (1 - (1 - frac) ** 2))
        draw.ellipse(
            [int(cx - r), int(cy - r), int(cx + r), int(cy + r)],
            fill=(0, 0, 0, alpha),
        )
    return Image.alpha_composite(img, vignette)


def _apply_noise(img: Image.Image, strength: int = 8) -> Image.Image:
    w, h = img.size
    noise_arr = np.random.randint(0, strength, (h, w), dtype=np.uint8)
    noise_rgba = np.stack([noise_arr, noise_arr, noise_arr,
                           np.full((h, w), 20, dtype=np.uint8)], axis=2)
    noise_img = Image.fromarray(noise_rgba, "RGBA")
    return Image.alpha_composite(img, noise_img)


# ---------------------------------------------------------------------------
# Rounded-rect bar drawing
# ---------------------------------------------------------------------------

def _draw_rounded_rect(
    draw: ImageDraw.Draw,
    xy: tuple[int, int, int, int],
    radius: int,
    fill: tuple[int, ...],
) -> None:
    x1, y1, x2, y2 = xy
    r = min(radius, (y2 - y1) // 2, (x2 - x1) // 2)
    if r < 1:
        draw.rectangle(xy, fill=fill)
        return
    draw.rounded_rectangle(xy, radius=r, fill=fill)


# ---------------------------------------------------------------------------
# Headshot helpers
# ---------------------------------------------------------------------------

def _load_headshot(player: str, directory: str, size: int) -> Optional[Image.Image]:
    """Load and circularly crop a headshot image for *player*."""
    base = Path(directory)
    for ext in (".png", ".jpg", ".jpeg", ".webp"):
        candidate = base / f"{player}{ext}"
        if candidate.is_file():
            img = Image.open(candidate).convert("RGBA").resize(
                (size, size), Image.LANCZOS
            )
            # Circular mask.
            mask = Image.new("L", (size, size), 0)
            ImageDraw.Draw(mask).ellipse([0, 0, size, size], fill=255)
            img.putalpha(mask)
            return img
    return None


# ---------------------------------------------------------------------------
# Frame renderer
# ---------------------------------------------------------------------------

class FrameRenderer:
    """Renders individual frames given config and preset."""

    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.preset: VideoPreset = cfg.get_preset()
        self.W = self.preset.width
        self.H = self.preset.height

        # Precompute fonts
        scale = self.H / 1080
        self.font_title = _load_font(cfg.font_bold, max(12, int(42 * scale)))
        self.font_subtitle = _load_font(cfg.font_medium, max(10, int(26 * scale)))
        self.font_name = _load_font(cfg.font_medium, max(10, int(22 * scale)))
        self.font_value = _load_font(cfg.font_regular, max(10, int(20 * scale)))
        self.font_date = _load_font(cfg.font_bold, max(14, int(72 * scale)))
        self.font_watermark = _load_font(cfg.font_light, max(10, int(18 * scale)))

        # Precompute background (cached — same for every frame).
        c1 = _hex_to_rgb(cfg.bg_gradient[0])
        c2 = _hex_to_rgb(cfg.bg_gradient[1])
        self._bg = _render_gradient_np(self.W, self.H, c1, c2)
        if cfg.vignette:
            self._bg = _apply_vignette(self._bg)

        # Layout constants
        self._margin_left = int(self.W * 0.22)
        self._margin_right = int(self.W * 0.05)
        self._bar_area_top = int(self.H * 0.15)
        self._bar_area_bottom = int(self.H * 0.85)

    # -- public API --------------------------------------------------------

    def render(self, state: FrameState) -> Image.Image:
        """Return an RGBA :class:`PIL.Image.Image` for the given frame."""
        img = self._bg.copy()
        if self.cfg.noise:
            img = _apply_noise(img)

        draw = ImageDraw.Draw(img)

        bar_area_h = self._bar_area_bottom - self._bar_area_top
        n_bars = self.cfg.top_n
        bar_gap = max(4, int(bar_area_h * 0.02))
        bar_h = max(8, (bar_area_h - bar_gap * (n_bars + 1)) // n_bars)

        max_bar_w = self.W - self._margin_left - self._margin_right

        for bar in state.bars:
            if bar.rank >= n_bars:
                continue

            y_center = (
                self._bar_area_top
                + bar_gap
                + bar.rank * (bar_h + bar_gap)
                + bar_h / 2
            )
            y1 = int(y_center - bar_h / 2)
            y2 = int(y_center + bar_h / 2)

            bar_w = int((bar.value / max(state.max_value, 1e-9)) * max_bar_w)
            bar_w = max(bar_w, 1)

            x1 = self._margin_left
            x2 = x1 + bar_w

            color_hex = _color_for_bar(bar, self.cfg.use_team_colors)
            base_rgb = _hex_to_rgb(color_hex)
            alpha = int(255 * bar.alpha)

            # --- bar shadow -----------------------------------------------
            if self.cfg.bar_shadow:
                sh_off = max(2, int(bar_h * 0.08))
                _draw_rounded_rect(
                    draw,
                    (x1 + sh_off, y1 + sh_off, x2 + sh_off, y2 + sh_off),
                    radius=int(bar_h * 0.25) if self.cfg.rounded_bars else 0,
                    fill=(0, 0, 0, min(alpha, 60)),
                )

            # --- main bar fill --------------------------------------------
            fill = (*base_rgb, alpha)
            radius = int(bar_h * 0.25) if self.cfg.rounded_bars else 0
            _draw_rounded_rect(draw, (x1, y1, x2, y2), radius=radius, fill=fill)

            # --- highlight strip (top 30%) --------------------------------
            highlight_h = max(1, int(bar_h * 0.30))
            hl_rgb = _lighten(base_rgb, 0.25)
            _draw_rounded_rect(
                draw,
                (x1, y1, x2, y1 + highlight_h),
                radius=min(radius, highlight_h // 2),
                fill=(*hl_rgb, alpha),
            )

            # --- shadow strip (bottom 18%) --------------------------------
            shadow_h = max(1, int(bar_h * 0.18))
            sh_rgb = _darken(base_rgb, 0.25)
            _draw_rounded_rect(
                draw,
                (x1, y2 - shadow_h, x2, y2),
                radius=min(radius, shadow_h // 2),
                fill=(*sh_rgb, alpha),
            )

            # --- leader glow on rank 0 ------------------------------------
            if self.cfg.leader_glow and bar.rank < 0.5:
                glow = Image.new("RGBA", (bar_w + 20, bar_h + 20), (0, 0, 0, 0))
                gd = ImageDraw.Draw(glow)
                gd.rounded_rectangle(
                    [0, 0, bar_w + 19, bar_h + 19],
                    radius=radius + 5,
                    fill=(*base_rgb, 40),
                )
                glow = glow.filter(ImageFilter.GaussianBlur(radius=10))
                img.paste(
                    glow,
                    (x1 - 10, y1 - 10),
                    glow,
                )
                # Re-acquire draw after paste.
                draw = ImageDraw.Draw(img)

            # --- edge fade for entering / exiting bars --------------------
            if bar.entering or bar.exiting:
                fade_alpha = max(0, min(255, int(255 * bar.alpha)))
                if fade_alpha < 200:
                    fade = Image.new("RGBA", (bar_w, bar_h), (0, 0, 0, 0))
                    fd = ImageDraw.Draw(fade)
                    fd.rectangle([0, 0, bar_w, bar_h], fill=(*base_rgb, fade_alpha))
                    img.paste(fade, (x1, y1), fade)
                    draw = ImageDraw.Draw(img)

            # --- headshot inside bar --------------------------------------
            if self.cfg.headshot_dir:
                hs_size = max(16, bar_h - 4)
                hs = _load_headshot(bar.player, self.cfg.headshot_dir, hs_size)
                if hs is not None:
                    hs_x = x1 + 4
                    hs_y = y1 + (bar_h - hs_size) // 2
                    img.paste(hs, (hs_x, hs_y), hs)
                    draw = ImageDraw.Draw(img)

            # --- player name (right-aligned, left of bar) -----------------
            name_text = bar.player
            try:
                name_bbox = self.font_name.getbbox(name_text)
                tw = name_bbox[2] - name_bbox[0]
                th = name_bbox[3] - name_bbox[1]
            except AttributeError:
                tw, th = draw.textsize(name_text, font=self.font_name)  # type: ignore[attr-defined]

            name_x = x1 - tw - 10
            name_y = y1 + (bar_h - th) // 2
            draw.text(
                (name_x, name_y),
                name_text,
                fill=(255, 255, 255, alpha),
                font=self.font_name,
            )

            # --- value label (inside bar if room, else outside) -----------
            val_text = f"{bar.value:,.0f}"
            try:
                val_bbox = self.font_value.getbbox(val_text)
                vw = val_bbox[2] - val_bbox[0]
                vh = val_bbox[3] - val_bbox[1]
            except AttributeError:
                vw, vh = draw.textsize(val_text, font=self.font_value)  # type: ignore[attr-defined]

            if bar_w > vw + 16:
                val_x = x2 - vw - 8
                val_color = (255, 255, 255, alpha)
            else:
                val_x = x2 + 8
                val_color = (220, 220, 220, alpha)
            val_y = y1 + (bar_h - vh) // 2
            draw.text((val_x, val_y), val_text, fill=val_color, font=self.font_value)

        # --- date label (large, translucent, bottom-right) ----------------
        draw.text(
            (self.W - self._margin_right - 10, self._bar_area_bottom + 20),
            state.date_label,
            fill=(255, 255, 255, 50),
            font=self.font_date,
            anchor="rt",
        )

        # --- title + subtitle (top-left) ----------------------------------
        if self.cfg.title:
            draw.text(
                (self._margin_right + 10, int(self.H * 0.04)),
                self.cfg.title,
                fill=(255, 255, 255, 230),
                font=self.font_title,
            )
        if self.cfg.subtitle:
            draw.text(
                (self._margin_right + 10, int(self.H * 0.04 + 50)),
                self.cfg.subtitle,
                fill=(200, 200, 200, 200),
                font=self.font_subtitle,
            )

        # --- watermark (bottom-right) -------------------------------------
        if self.cfg.watermark:
            draw.text(
                (self.W - self._margin_right - 10, self.H - int(self.H * 0.03)),
                self.cfg.watermark,
                fill=(255, 255, 255, 80),
                font=self.font_watermark,
                anchor="rb",
            )

        return img

    def render_rgb_bytes(self, state: FrameState) -> bytes:
        """Render a frame and return raw RGB bytes (for ffmpeg pipe)."""
        return self.render(state).convert("RGB").tobytes()

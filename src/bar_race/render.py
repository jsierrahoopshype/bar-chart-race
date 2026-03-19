"""Pillow/PIL frame renderer — NO matplotlib.

Renders each :class:`~bar_race.animate.FrameState` into a raw RGBA
:class:`PIL.Image.Image`.  All visual decisions are driven by the
:class:`~bar_race.themes.Theme` object.
"""

from __future__ import annotations

import math
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
from bar_race.themes import Theme, get_theme

# ---------------------------------------------------------------------------
# Colour helpers
# ---------------------------------------------------------------------------

def _hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


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


def _text_size(
    draw: ImageDraw.Draw,
    text: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
) -> tuple[int, int]:
    """Return (width, height) of *text* rendered with *font*."""
    try:
        bbox = font.getbbox(text)
        return bbox[2] - bbox[0], bbox[3] - bbox[1]
    except AttributeError:
        return draw.textsize(text, font=font)  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Background generation
# ---------------------------------------------------------------------------

def _render_gradient_np(
    width: int,
    height: int,
    c1: tuple[int, int, int],
    c2: tuple[int, int, int],
) -> Image.Image:
    ys = np.linspace(0, 1, height, dtype=np.float32)
    ts = ys * ys * (3.0 - 2.0 * ys)
    ts = ts[:, None]
    c1a = np.array(c1, dtype=np.float32)
    c2a = np.array(c2, dtype=np.float32)
    rgb = (c1a + (c2a - c1a) * ts).clip(0, 255).astype(np.uint8)
    rgb = np.broadcast_to(rgb[:, None, :], (height, width, 3)).copy()
    alpha = np.full((height, width, 1), 255, dtype=np.uint8)
    return Image.fromarray(np.concatenate([rgb, alpha], axis=2), "RGBA")


def _render_split_bg(
    width: int,
    height: int,
    c1: tuple[int, int, int],
    c2: tuple[int, int, int],
) -> Image.Image:
    """Split background: left half is c1 gradient, right half is c2 gradient."""
    img = Image.new("RGBA", (width, height))
    left = _render_gradient_np(width // 2, height, c1, _darken(c1, 0.3))
    right = _render_gradient_np(width - width // 2, height, c2, _darken(c2, 0.3))
    img.paste(left, (0, 0))
    img.paste(right, (width // 2, 0))
    return img


def _build_background(theme: Theme, width: int, height: int) -> Image.Image:
    colors = [_hex_to_rgb(c) for c in theme.bg_colors]
    c1 = colors[0]
    c2 = colors[1] if len(colors) > 1 else c1

    if theme.bg_type == "solid":
        img = Image.new("RGBA", (width, height), (*c1, 255))
    elif theme.bg_type == "split":
        img = _render_split_bg(width, height, c1, c2)
    else:
        img = _render_gradient_np(width, height, c1, c2)
    return img


# ---------------------------------------------------------------------------
# Overlays
# ---------------------------------------------------------------------------

def _apply_vignette(img: Image.Image) -> Image.Image:
    w, h = img.size
    vignette = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(vignette)
    cx, cy = w / 2, h / 2
    max_r = math.sqrt(cx * cx + cy * cy)
    for i in range(40, 0, -1):
        frac = i / 40
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
    return Image.alpha_composite(img, Image.fromarray(noise_rgba, "RGBA"))


def _draw_accent_lines(
    draw: ImageDraw.Draw, w: int, h: int, theme: Theme,
) -> None:
    """Draw top/bottom accent lines."""
    c = _hex_to_rgb(theme.accent_color)
    thickness = max(3, h // 300)
    draw.rectangle([0, 0, w, thickness], fill=(*c, 200))
    draw.rectangle([0, h - thickness, w, h], fill=(*c, 200))


def _draw_diagonal_slash(
    draw: ImageDraw.Draw, w: int, h: int, theme: Theme,
) -> None:
    c = _hex_to_rgb(theme.accent_color)
    sw = max(w // 8, 80)
    # Draw a wide diagonal band from top-right to bottom area.
    points = [
        (w - sw, 0),
        (w, 0),
        (sw, h),
        (0, h),
    ]
    draw.polygon(points, fill=(*c, 18))


def _draw_court_lines(
    draw: ImageDraw.Draw, w: int, h: int, theme: Theme,
) -> None:
    c = _hex_to_rgb(theme.accent_color)
    alpha = 15
    # Centre circle.
    cx, cy = w // 2, h // 2
    r = min(w, h) // 6
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(*c, alpha), width=2)
    # Half-court line.
    draw.line([(w // 2, 0), (w // 2, h)], fill=(*c, alpha), width=1)


def _draw_background_circle(
    draw: ImageDraw.Draw, w: int, h: int, theme: Theme,
) -> None:
    c = _hex_to_rgb(theme.accent_color)
    cx, cy = w // 2, h // 2
    r = min(w, h) // 4
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(*c, 20), width=3)


def _draw_grid_lines(
    draw: ImageDraw.Draw, w: int, h: int, theme: Theme,
    bar_area_top: int, bar_area_bottom: int, margin_left: int, margin_right: int,
) -> None:
    c = _hex_to_rgb(theme.text_secondary_color)
    alpha = 20
    bar_w = w - margin_left - margin_right
    for frac in (0.25, 0.5, 0.75, 1.0):
        x = margin_left + int(bar_w * frac)
        draw.line([(x, bar_area_top), (x, bar_area_bottom)], fill=(*c, alpha), width=1)


def _draw_border_frame(
    draw: ImageDraw.Draw, w: int, h: int, theme: Theme,
) -> None:
    c = _hex_to_rgb(theme.accent_color)
    t = max(2, h // 400)
    if theme.border_frame == "full":
        draw.rectangle([0, 0, w - 1, h - 1], outline=(*c, 60), width=t)
    elif theme.border_frame == "left-accent":
        draw.rectangle([0, 0, t, h], fill=(*c, 120))


def _draw_rounded_rect(
    draw: ImageDraw.Draw,
    xy: tuple[int, int, int, int],
    radius: int,
    fill: tuple[int, ...] | None = None,
    outline: tuple[int, ...] | None = None,
    width: int = 1,
) -> None:
    x1, y1, x2, y2 = xy
    r = min(radius, (y2 - y1) // 2, (x2 - x1) // 2)
    if r < 1:
        draw.rectangle(xy, fill=fill, outline=outline, width=width)
        return
    draw.rounded_rectangle(xy, radius=r, fill=fill, outline=outline, width=width)


# ---------------------------------------------------------------------------
# Headshot helpers with white-halo removal
# ---------------------------------------------------------------------------

def _remove_white_halo(img: Image.Image) -> Image.Image:
    """Erode alpha by 2-3 px and remove white-fringe pixels."""
    arr = np.array(img)  # (H, W, 4)
    r, g, b, a = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2], arr[:, :, 3]

    # Detect semi-transparent white-ish fringe pixels.
    is_whitish = (r > 200) & (g > 200) & (b > 200)
    is_semi = (a > 10) & (a < 200)
    arr[is_whitish & is_semi, 3] = 0  # make fully transparent

    # Erode alpha by 2 pixels using numpy.
    from PIL import ImageFilter as _IF
    alpha_img = Image.fromarray(a)
    eroded = alpha_img.filter(_IF.MinFilter(size=5))
    arr[:, :, 3] = np.array(eroded)

    return Image.fromarray(arr, "RGBA")


def _load_headshot(
    player: str, directory: str, size: int, theme: Theme,
) -> Optional[Image.Image]:
    """Load, de-halo, shape, and optionally border a headshot."""
    if theme.headshot_shape == "none":
        return None

    base = Path(directory)
    for ext in (".png", ".jpg", ".jpeg", ".webp"):
        candidate = base / f"{player}{ext}"
        if candidate.is_file():
            img = Image.open(candidate).convert("RGBA").resize(
                (size, size), Image.LANCZOS
            )
            img = _remove_white_halo(img)

            # Shape mask.
            mask = Image.new("L", (size, size), 0)
            md = ImageDraw.Draw(mask)
            if theme.headshot_shape == "circle":
                md.ellipse([0, 0, size - 1, size - 1], fill=255)
            elif theme.headshot_shape == "rounded":
                md.rounded_rectangle([0, 0, size - 1, size - 1],
                                     radius=size // 6, fill=255)
            else:  # square
                md.rectangle([0, 0, size - 1, size - 1], fill=255)
            img.putalpha(mask)

            # Border.
            if theme.headshot_border:
                bw = max(2, size // 40)
                border_c = _hex_to_rgb(theme.accent_color)
                if theme.headshot_border_color == "team":
                    # We don't have bar context here; accent is fine.
                    pass
                elif theme.headshot_border_color != "accent":
                    border_c = _hex_to_rgb(theme.headshot_border_color)
                bordered = Image.new("RGBA", (size, size), (0, 0, 0, 0))
                bd = ImageDraw.Draw(bordered)
                if theme.headshot_shape == "circle":
                    bd.ellipse([0, 0, size - 1, size - 1], outline=(*border_c, 200), width=bw)
                elif theme.headshot_shape == "rounded":
                    bd.rounded_rectangle([0, 0, size - 1, size - 1],
                                         radius=size // 6, outline=(*border_c, 200), width=bw)
                else:
                    bd.rectangle([0, 0, size - 1, size - 1], outline=(*border_c, 200), width=bw)
                img = Image.alpha_composite(img, bordered)

            return img
    return None


# ---------------------------------------------------------------------------
# Frame renderer
# ---------------------------------------------------------------------------

class FrameRenderer:
    """Renders individual frames. All visual decisions driven by Theme."""

    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.theme: Theme = get_theme(cfg.theme)
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
        self.font_rank = _load_font(cfg.font_bold, max(10, int(18 * scale)))
        self.font_rank_giant = _load_font(cfg.font_bold, max(20, int(80 * scale)))
        self.font_branding = _load_font(cfg.font_bold, max(8, int(14 * scale)))

        # Precompute background.
        th = self.theme
        self._bg = _build_background(th, self.W, self.H)
        if th.vignette:
            self._bg = _apply_vignette(self._bg)

        # Draw static decorative elements on background.
        bg_draw = ImageDraw.Draw(self._bg)
        if th.show_court_lines:
            _draw_court_lines(bg_draw, self.W, self.H, th)
        if th.show_background_circle:
            _draw_background_circle(bg_draw, self.W, self.H, th)
        if th.show_diagonal_slash:
            _draw_diagonal_slash(bg_draw, self.W, self.H, th)
        if th.border_frame not in ("none", "top-bottom"):
            _draw_border_frame(bg_draw, self.W, self.H, th)

        # Layout constants
        self._margin_left = int(self.W * 0.22)
        self._margin_right = int(self.W * 0.05)
        self._bar_area_top = int(self.H * 0.15)
        self._bar_area_bottom = int(self.H * 0.85)

    # -- public API --------------------------------------------------------

    def render(self, state: FrameState) -> Image.Image:
        """Return an RGBA :class:`PIL.Image.Image` for the given frame."""
        th = self.theme
        img = self._bg.copy()
        if th.noise:
            img = _apply_noise(img)

        draw = ImageDraw.Draw(img)

        # Accent lines (drawn per-frame so they're on top of noise).
        if th.show_accent_line:
            _draw_accent_lines(draw, self.W, self.H, th)
        if th.border_frame == "top-bottom":
            _draw_accent_lines(draw, self.W, self.H, th)

        # Grid lines.
        if th.show_grid_lines:
            _draw_grid_lines(
                draw, self.W, self.H, th,
                self._bar_area_top, self._bar_area_bottom,
                self._margin_left, self._margin_right,
            )

        bar_area_h = self._bar_area_bottom - self._bar_area_top
        n_bars = self.cfg.top_n
        bar_gap = max(4, int(bar_area_h * 0.02))
        bar_h = max(8, (bar_area_h - bar_gap * (n_bars + 1)) // n_bars)
        max_bar_w = self.W - self._margin_left - self._margin_right

        text_c = _hex_to_rgb(th.text_color)
        text2_c = _hex_to_rgb(th.text_secondary_color)
        accent_c = _hex_to_rgb(th.accent_color)

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
            alpha = int(255 * bar.alpha * th.bar_opacity)
            is_leader = bar.rank < 0.5

            radius = th.bar_radius

            # --- leader background highlight ------------------------------
            if th.leader_bg_highlight and is_leader:
                draw.rectangle(
                    [0, y1 - 2, self.W, y2 + 2],
                    fill=(255, 255, 255, 8),
                )

            # --- rank giant watermark behind bar --------------------------
            if th.rank_giant_watermark:
                rank_num = int(bar.rank) + 1
                rank_text = str(rank_num)
                rw, rh = _text_size(draw, rank_text, self.font_rank_giant)
                rx = x1 + bar_w // 2 - rw // 2
                ry = y1 + (bar_h - rh) // 2
                draw.text((rx, ry), rank_text, fill=(*text_c, 15),
                          font=self.font_rank_giant)

            # --- bar shadow -----------------------------------------------
            if th.bar_shadow:
                sh_off = max(2, int(bar_h * 0.08))
                _draw_rounded_rect(
                    draw,
                    (x1 + sh_off, y1 + sh_off, x2 + sh_off, y2 + sh_off),
                    radius=radius, fill=(0, 0, 0, min(alpha, 60)),
                )

            # --- main bar fill --------------------------------------------
            fill = (*base_rgb, alpha)
            _draw_rounded_rect(draw, (x1, y1, x2, y2), radius=radius, fill=fill)

            # --- bar border (outlined style) ------------------------------
            if th.bar_border:
                _draw_rounded_rect(
                    draw, (x1, y1, x2, y2), radius=radius,
                    outline=(*base_rgb, min(alpha, 200)),
                    width=th.bar_border_width,
                )

            # --- team stripe (thin left-edge stripe) ----------------------
            if th.bar_team_stripe:
                stripe_w = max(3, bar_h // 8)
                _draw_rounded_rect(
                    draw,
                    (x1, y1, x1 + stripe_w, y2),
                    radius=min(radius, stripe_w // 2),
                    fill=(*_lighten(base_rgb, 0.3), alpha),
                )

            # --- highlight strip (top 30%) --------------------------------
            if th.show_highlight_strip:
                hl_h = max(1, int(bar_h * 0.30))
                hl_rgb = _lighten(base_rgb, 0.25)
                _draw_rounded_rect(
                    draw, (x1, y1, x2, y1 + hl_h),
                    radius=min(radius, hl_h // 2),
                    fill=(*hl_rgb, alpha),
                )

            # --- shadow strip (bottom 18%) --------------------------------
            if th.show_shadow_strip:
                sh_h = max(1, int(bar_h * 0.18))
                sh_rgb = _darken(base_rgb, 0.25)
                _draw_rounded_rect(
                    draw, (x1, y2 - sh_h, x2, y2),
                    radius=min(radius, sh_h // 2),
                    fill=(*sh_rgb, alpha),
                )

            # --- leader effects -------------------------------------------
            if is_leader:
                if th.leader_glow:
                    glow_c = base_rgb
                    if th.leader_glow_color != "team":
                        glow_c = _hex_to_rgb(th.leader_glow_color)
                    glow = Image.new("RGBA", (bar_w + 20, bar_h + 20), (0, 0, 0, 0))
                    gd = ImageDraw.Draw(glow)
                    gd.rounded_rectangle(
                        [0, 0, bar_w + 19, bar_h + 19],
                        radius=radius + 5,
                        fill=(*glow_c, 40),
                    )
                    glow = glow.filter(ImageFilter.GaussianBlur(radius=10))
                    img.paste(glow, (x1 - 10, y1 - 10), glow)
                    draw = ImageDraw.Draw(img)

                if th.leader_outline:
                    _draw_rounded_rect(
                        draw, (x1 - 1, y1 - 1, x2 + 1, y2 + 1),
                        radius=radius + 1,
                        outline=(*accent_c, 150), width=2,
                    )

                if th.leader_underline:
                    line_c = _hex_to_rgb(th.accent_color)
                    underline_h = max(2, bar_h // 12)
                    draw.rectangle(
                        [x1, y2 + 1, x2, y2 + underline_h],
                        fill=(*line_c, 180),
                    )

            # --- edge fade for entering / exiting bars --------------------
            if bar.entering or bar.exiting:
                fade_alpha = max(0, min(255, int(255 * bar.alpha)))
                if fade_alpha < 200:
                    fade = Image.new("RGBA", (max(1, bar_w), bar_h), (0, 0, 0, 0))
                    fd = ImageDraw.Draw(fade)
                    fd.rectangle([0, 0, bar_w, bar_h], fill=(*base_rgb, fade_alpha))
                    img.paste(fade, (x1, y1), fade)
                    draw = ImageDraw.Draw(img)

            # --- headshot -------------------------------------------------
            if self.cfg.headshot_dir:
                hs_size = max(16, bar_h - 4)
                hs = _load_headshot(bar.player, self.cfg.headshot_dir, hs_size, th)
                if hs is not None:
                    if th.headshot_position == "before-bar":
                        hs_x = x1 - hs_size - 6
                    else:
                        hs_x = x1 + 4
                    hs_y = y1 + (bar_h - hs_size) // 2
                    img.paste(hs, (hs_x, hs_y), hs)
                    draw = ImageDraw.Draw(img)

            # --- rank number (left of name) -------------------------------
            if th.show_rank_numbers and not th.rank_giant_watermark:
                rank_num = int(bar.rank) + 1
                if th.rank_number_style == "padded":
                    rank_text = f"{rank_num:02d}"
                else:
                    rank_text = str(rank_num)
                rw, rh = _text_size(draw, rank_text, self.font_rank)

                if th.rank_number_style == "badge":
                    badge_size = max(rw, rh) + 8
                    badge_x = x1 - badge_size - _text_size(draw, bar.player, self.font_name)[0] - 18
                    badge_y = y1 + (bar_h - badge_size) // 2
                    draw.ellipse(
                        [badge_x, badge_y, badge_x + badge_size, badge_y + badge_size],
                        fill=(*accent_c, 180),
                    )
                    draw.text(
                        (badge_x + (badge_size - rw) // 2, badge_y + (badge_size - rh) // 2),
                        rank_text, fill=(255, 255, 255, 230), font=self.font_rank,
                    )
                else:
                    tw_name = _text_size(draw, bar.player, self.font_name)[0]
                    rank_x = x1 - tw_name - rw - 18
                    rank_y = y1 + (bar_h - rh) // 2
                    draw.text(
                        (rank_x, rank_y), rank_text,
                        fill=(*text2_c, int(alpha * 0.6)), font=self.font_rank,
                    )

            # --- player name (right-aligned, left of bar) -----------------
            name_text = bar.player
            if th.label_case == "upper":
                name_text = name_text.upper()
            elif th.label_case == "title":
                name_text = name_text.title()
            tw, th_h = _text_size(draw, name_text, self.font_name)

            name_x = x1 - tw - 10
            name_y = y1 + (bar_h - th_h) // 2
            draw.text(
                (name_x, name_y), name_text,
                fill=(*text_c, alpha), font=self.font_name,
            )

            # --- value label (inside bar if room, else outside) -----------
            val_text = f"{bar.value:,.0f}{th.value_suffix}"
            vw, vh = _text_size(draw, val_text, self.font_value)

            if bar_w > vw + 16:
                val_x = x2 - vw - 8
                val_color = (*text_c, alpha)
            else:
                val_x = x2 + 8
                val_color = (*text2_c, alpha)
            val_y = y1 + (bar_h - vh) // 2
            draw.text((val_x, val_y), val_text, fill=val_color, font=self.font_value)

        # --- date label ---------------------------------------------------
        date_c = _hex_to_rgb(th.date_color)
        date_alpha = int(255 * th.date_opacity)
        if th.date_position == "top-right":
            date_xy = (self.W - self._margin_right - 10, int(self.H * 0.05))
            date_anchor = "rt"
        elif th.date_position == "bottom-center":
            date_xy = (self.W // 2, self._bar_area_bottom + 20)
            date_anchor = "mt"
        else:
            date_xy = (self.W - self._margin_right - 10, self._bar_area_bottom + 20)
            date_anchor = "rt"
        draw.text(
            date_xy, state.date_label,
            fill=(*date_c, date_alpha),
            font=self.font_date, anchor=date_anchor,
        )

        # --- title + subtitle --------------------------------------------
        title_c = _hex_to_rgb(th.title_color)
        if th.title_position == "top-center":
            title_x = self.W // 2
            title_anchor = "mt"
        else:
            title_x = self._margin_right + 10
            title_anchor = "lt"

        if self.cfg.title:
            draw.text(
                (title_x, int(self.H * 0.04)),
                self.cfg.title,
                fill=(*title_c, 230),
                font=self.font_title, anchor=title_anchor,
            )
        if self.cfg.subtitle:
            draw.text(
                (title_x, int(self.H * 0.04 + 50)),
                self.cfg.subtitle,
                fill=(*text2_c, 200),
                font=self.font_subtitle, anchor=title_anchor,
            )

        # --- branding tag -------------------------------------------------
        if th.show_branding_tag and th.branding_text:
            bc = _hex_to_rgb(th.branding_color)
            bw, bh = _text_size(draw, th.branding_text, self.font_branding)
            bx = self._margin_right + 10
            by = int(self.H * 0.04 + 90)
            # Tag background.
            draw.rectangle(
                [bx - 4, by - 2, bx + bw + 4, by + bh + 2],
                fill=(*bc, 200),
            )
            draw.text((bx, by), th.branding_text, fill=(255, 255, 255, 240),
                      font=self.font_branding)

        # --- watermark (bottom-right) -------------------------------------
        if self.cfg.watermark:
            draw.text(
                (self.W - self._margin_right - 10, self.H - int(self.H * 0.03)),
                self.cfg.watermark,
                fill=(*text_c, 80),
                font=self.font_watermark, anchor="rb",
            )

        return img

    def render_rgb_bytes(self, state: FrameState) -> bytes:
        """Render a frame and return raw RGB bytes (for ffmpeg pipe)."""
        return self.render(state).convert("RGB").tobytes()

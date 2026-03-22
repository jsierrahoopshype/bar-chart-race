"""Pillow/PIL frame renderer — NO matplotlib.

Renders each :class:`~bar_race.animate.FrameState` into a raw RGBA
:class:`PIL.Image.Image`.  All visual decisions are driven by the
:class:`~bar_race.themes.Theme` object.
"""

from __future__ import annotations

import math
import unicodedata
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
# Font loading — with font_family support
# ---------------------------------------------------------------------------

# Font families by platform.
# Linux (Docker): DejaVu fonts installed via fonts-dejavu-core.
# Windows: system fonts in C:/Windows/Fonts.
_LINUX_FONT_FAMILIES: dict[str, dict[str, str]] = {
    "sans": {
        "bold": "DejaVuSans-Bold.ttf",
        "medium": "DejaVuSans.ttf",
        "regular": "DejaVuSans.ttf",
        "light": "DejaVuSans-ExtraLight.ttf",
    },
    "serif": {
        "bold": "DejaVuSerif-Bold.ttf",
        "medium": "DejaVuSerif.ttf",
        "regular": "DejaVuSerif.ttf",
        "light": "DejaVuSerif.ttf",
    },
    "mono": {
        "bold": "DejaVuSansMono-Bold.ttf",
        "medium": "DejaVuSansMono.ttf",
        "regular": "DejaVuSansMono.ttf",
        "light": "DejaVuSansMono.ttf",
    },
    "condensed": {
        "bold": "DejaVuSansCondensed-Bold.ttf",
        "medium": "DejaVuSansCondensed.ttf",
        "regular": "DejaVuSansCondensed.ttf",
        "light": "DejaVuSansCondensed.ttf",
    },
}

_WIN_FONT_FAMILIES: dict[str, dict[str, str]] = {
    "sans": {
        "bold": "arialbd.ttf",
        "medium": "arial.ttf",
        "regular": "arial.ttf",
        "light": "arial.ttf",
    },
    "serif": {
        "bold": "georgiab.ttf",
        "medium": "georgiai.ttf",
        "regular": "georgia.ttf",
        "light": "georgia.ttf",
    },
    "mono": {
        "bold": "courbd.ttf",
        "medium": "cour.ttf",
        "regular": "cour.ttf",
        "light": "cour.ttf",
    },
    "condensed": {
        "bold": "arialnb.ttf",   # Arial Narrow Bold
        "medium": "arialn.ttf",  # Arial Narrow
        "regular": "arialn.ttf",
        "light": "arialn.ttf",
    },
}

_LINUX_FONT_DIR = Path("/usr/share/fonts/truetype/dejavu")
_WIN_FONT_DIR = Path("C:/Windows/Fonts")


def _resolve_font(family: str, weight: str) -> str:
    """Resolve a font family + weight to an absolute path.

    Checks Linux DejaVu paths first, then Windows system fonts.
    """
    # Try Linux (DejaVu) first.
    linux_fam = _LINUX_FONT_FAMILIES.get(family, _LINUX_FONT_FAMILIES["sans"])
    linux_name = linux_fam.get(weight, linux_fam["regular"])
    linux_candidate = _LINUX_FONT_DIR / linux_name
    if linux_candidate.is_file():
        return str(linux_candidate)

    # Try Windows fonts.
    win_fam = _WIN_FONT_FAMILIES.get(family, _WIN_FONT_FAMILIES["sans"])
    win_name = win_fam.get(weight, win_fam["regular"])
    win_candidate = _WIN_FONT_DIR / win_name
    if win_candidate.is_file():
        return str(win_candidate)

    # Fallback to Arial (Windows) or DejaVu Sans (Linux).
    for fallback in (_LINUX_FONT_DIR / "DejaVuSans.ttf",
                     _WIN_FONT_DIR / "arial.ttf"):
        if fallback.is_file():
            return str(fallback)
    return linux_name


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
    thickness = max(4, h // 200)
    draw.rectangle([0, 0, w, thickness], fill=(*c, 220))
    draw.rectangle([0, h - thickness, w, h], fill=(*c, 220))


def _draw_diagonal_slash(
    draw: ImageDraw.Draw, w: int, h: int, theme: Theme,
) -> None:
    c = _hex_to_rgb(theme.accent_color)
    sw = max(w // 6, 100)
    points = [
        (w - sw, 0),
        (w, 0),
        (sw, h),
        (0, h),
    ]
    draw.polygon(points, fill=(*c, 25))
    # Second thinner slash for more visual impact.
    sw2 = sw // 3
    off = sw // 2
    points2 = [
        (w - sw - off, 0),
        (w - off - sw + sw2, 0),
        (sw2 + off - sw, h),
        (off - sw, h),
    ]
    draw.polygon(points2, fill=(*c, 12))


def _draw_court_lines(
    draw: ImageDraw.Draw, w: int, h: int, theme: Theme,
) -> None:
    c = _hex_to_rgb(theme.accent_color)
    alpha = 25
    lw = max(2, h // 400)
    # Centre circle.
    cx, cy = w // 2, h // 2
    r = min(w, h) // 5
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(*c, alpha), width=lw)
    # Smaller inner circle.
    r2 = r // 3
    draw.ellipse([cx - r2, cy - r2, cx + r2, cy + r2], outline=(*c, alpha // 2), width=lw)
    # Half-court line.
    draw.line([(w // 2, 0), (w // 2, h)], fill=(*c, alpha), width=lw)
    # Free throw circles (left and right).
    ftr = min(w, h) // 8
    draw.arc([w // 6 - ftr, cy - ftr, w // 6 + ftr, cy + ftr],
             start=270, end=90, fill=(*c, alpha // 2), width=lw)
    draw.arc([w * 5 // 6 - ftr, cy - ftr, w * 5 // 6 + ftr, cy + ftr],
             start=90, end=270, fill=(*c, alpha // 2), width=lw)


def _draw_background_circle(
    draw: ImageDraw.Draw, w: int, h: int, theme: Theme,
) -> None:
    c = _hex_to_rgb(theme.accent_color)
    cx, cy = w // 2, h // 2
    r = min(w, h) // 3
    lw = max(3, h // 300)
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(*c, 25), width=lw)
    r2 = r // 2
    draw.ellipse([cx - r2, cy - r2, cx + r2, cy + r2], outline=(*c, 12), width=lw)


def _draw_grid_lines(
    draw: ImageDraw.Draw, w: int, h: int, theme: Theme,
    bar_area_top: int, bar_area_bottom: int, margin_left: int, margin_right: int,
) -> None:
    c = _hex_to_rgb(theme.text_secondary_color)
    alpha = 30
    bar_w = w - margin_left - margin_right
    lw = max(1, h // 600)
    for frac in (0.25, 0.5, 0.75, 1.0):
        x = margin_left + int(bar_w * frac)
        draw.line([(x, bar_area_top - 5), (x, bar_area_bottom + 5)],
                  fill=(*c, alpha), width=lw)


def _draw_border_frame(
    draw: ImageDraw.Draw, w: int, h: int, theme: Theme,
) -> None:
    c = _hex_to_rgb(theme.accent_color)
    t = max(3, h // 300)
    if theme.border_frame == "full":
        draw.rectangle([0, 0, w - 1, h - 1], outline=(*c, 80), width=t)
    elif theme.border_frame == "left-accent":
        draw.rectangle([0, 0, t + 1, h], fill=(*c, 160))


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
        return
    draw.rounded_rectangle(xy, radius=r, fill=fill, outline=outline, width=width)


# ---------------------------------------------------------------------------
# Bar gradient rendering (left-to-right team color gradient)
# ---------------------------------------------------------------------------

def _draw_bar_gradient(
    img: Image.Image,
    xy: tuple[int, int, int, int],
    base_rgb: tuple[int, int, int],
    alpha: int,
    radius: int,
) -> None:
    """Draw a horizontal gradient bar: team color on left → lighter on right."""
    x1, y1, x2, y2 = xy
    bw = x2 - x1
    bh = y2 - y1
    if bw < 2 or bh < 2:
        return

    lighter = _lighten(base_rgb, 0.4)
    # Build gradient strip using numpy.
    ts = np.linspace(0, 1, bw, dtype=np.float32)[None, :]  # (1, bw)
    c1a = np.array(base_rgb, dtype=np.float32)
    c2a = np.array(lighter, dtype=np.float32)
    rgb = (c1a + (c2a - c1a) * ts[:, :, None]).clip(0, 255).astype(np.uint8)
    rgb = np.broadcast_to(rgb, (bh, bw, 3)).copy()
    a_arr = np.full((bh, bw, 1), alpha, dtype=np.uint8)
    bar_img = Image.fromarray(np.concatenate([rgb, a_arr], axis=2), "RGBA")

    # Apply rounded mask.
    mask = Image.new("L", (bw, bh), 0)
    md = ImageDraw.Draw(mask)
    r = min(radius, bh // 2, bw // 2)
    if r > 0:
        md.rounded_rectangle([0, 0, bw - 1, bh - 1], radius=r, fill=255)
    else:
        md.rectangle([0, 0, bw - 1, bh - 1], fill=255)
    bar_img.putalpha(mask)

    img.paste(bar_img, (x1, y1), bar_img)


# ---------------------------------------------------------------------------
# Headshot helpers with white-halo removal and caching
# ---------------------------------------------------------------------------

_headshot_cache: dict[str, Optional[Image.Image]] = {}


def _ascii_fold(name: str) -> str:
    """Fold Unicode characters to ASCII equivalents (e.g. ć→c, ö→o)."""
    nfkd = unicodedata.normalize("NFKD", name)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _remove_white_halo(img: Image.Image) -> Image.Image:
    """Erode alpha by 2-3 px and remove white-fringe pixels."""
    arr = np.array(img)  # (H, W, 4)
    r, g, b, a = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2], arr[:, :, 3]

    # Detect semi-transparent white-ish fringe pixels.
    is_whitish = (r > 180) & (g > 180) & (b > 180)
    is_semi = (a > 10) & (a < 220)
    arr[is_whitish & is_semi, 3] = 0  # make fully transparent

    # Erode alpha by 2 pixels.
    from PIL import ImageFilter as _IF
    alpha_img = Image.fromarray(a)
    eroded = alpha_img.filter(_IF.MinFilter(size=5))
    arr[:, :, 3] = np.array(eroded)

    return Image.fromarray(arr, "RGBA")


def _load_headshot(
    player: str, directory: str, size: int, theme: Theme,
    team_color: tuple[int, int, int] | None = None,
) -> Optional[Image.Image]:
    """Load, de-halo, shape, and optionally border a headshot. Cached."""
    cache_key = f"{player}:{size}:{theme.slug}"
    if cache_key in _headshot_cache:
        return _headshot_cache[cache_key]

    if theme.headshot_shape == "none":
        _headshot_cache[cache_key] = None
        return None

    base = Path(directory)
    # Try exact name first, then ASCII-folded fallback (e.g. Dončić → Doncic).
    names_to_try = [player]
    folded = _ascii_fold(player)
    if folded != player:
        names_to_try.append(folded)

    result = None
    for name_variant in names_to_try:
        if result is not None:
            break
        for ext in (".png", ".jpg", ".jpeg", ".webp"):
            candidate = base / f"{name_variant}{ext}"
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
                    bw = max(2, size // 30)
                    border_c = _hex_to_rgb(theme.accent_color)
                    if theme.headshot_border_color == "team" and team_color:
                        border_c = team_color
                    elif theme.headshot_border_color not in ("team", "accent"):
                        border_c = _hex_to_rgb(theme.headshot_border_color)
                    bordered = Image.new("RGBA", (size, size), (0, 0, 0, 0))
                    bd = ImageDraw.Draw(bordered)
                    if theme.headshot_shape == "circle":
                        bd.ellipse([0, 0, size - 1, size - 1],
                                   outline=(*border_c, 220), width=bw)
                    elif theme.headshot_shape == "rounded":
                        bd.rounded_rectangle([0, 0, size - 1, size - 1],
                                             radius=size // 6,
                                             outline=(*border_c, 220), width=bw)
                    else:
                        bd.rectangle([0, 0, size - 1, size - 1],
                                     outline=(*border_c, 220), width=bw)
                    img = Image.alpha_composite(img, bordered)

                result = img
                break

    _headshot_cache[cache_key] = result
    return result


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

        th = self.theme

        # Resolve fonts based on theme font_family.
        family = th.font_family
        scale = self.H / 1080

        # Use theme's font_family to resolve system fonts.
        # If user explicitly set fonts in config, use those instead.
        bold_path = cfg.font_bold
        medium_path = cfg.font_medium
        regular_path = cfg.font_regular
        light_path = cfg.font_light

        # Override with font_family if config used defaults (auto-resolved).
        if family != "sans":
            bold_path = _resolve_font(family, "bold")
            medium_path = _resolve_font(family, "medium")
            regular_path = _resolve_font(family, "regular")
            light_path = _resolve_font(family, "light")

        self.font_title = _load_font(bold_path, max(12, int(44 * scale)))
        self.font_subtitle = _load_font(medium_path, max(10, int(26 * scale)))
        self.font_name = _load_font(medium_path, max(10, int(24 * scale)))
        self.font_value = _load_font(regular_path, max(10, int(20 * scale)))
        self.font_date = _load_font(bold_path, max(14, int(72 * scale)))
        self.font_watermark = _load_font(light_path, max(10, int(18 * scale)))
        self.font_rank = _load_font(bold_path, max(10, int(20 * scale)))
        self.font_rank_giant = _load_font(bold_path, max(20, int(90 * scale)))
        self.font_branding = _load_font(bold_path, max(8, int(14 * scale)))

        # Precompute background.
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
        self._bar_area_top = int(self.H * 0.16)
        self._bar_area_bottom = int(self.H * 0.86)

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
        bar_gap = max(4, int(bar_area_h * 0.025))
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
                    [0, y1 - 4, self.W, y2 + 4],
                    fill=(255, 255, 255, 12),
                )

            # --- rank giant watermark behind bar --------------------------
            if th.rank_giant_watermark:
                rank_num = int(bar.rank) + 1
                rank_text = str(rank_num)
                rw, rh = _text_size(draw, rank_text, self.font_rank_giant)
                rx = x1 + bar_w // 2 - rw // 2
                ry = y1 + (bar_h - rh) // 2
                draw.text((rx, ry), rank_text, fill=(*text_c, 20),
                          font=self.font_rank_giant)

            # --- bar shadow -----------------------------------------------
            if th.bar_shadow:
                sh_off = max(3, int(bar_h * 0.08))
                _draw_rounded_rect(
                    draw,
                    (x1 + sh_off, y1 + sh_off, x2 + sh_off, y2 + sh_off),
                    radius=radius, fill=(0, 0, 0, min(alpha, 70)),
                )

            # --- main bar fill --------------------------------------------
            if th.bar_gradient:
                # Draw gradient bar using pixel-level rendering.
                _draw_bar_gradient(img, (x1, y1, x2, y2), base_rgb, alpha, radius)
                draw = ImageDraw.Draw(img)  # refresh after paste
            else:
                fill = (*base_rgb, alpha)
                _draw_rounded_rect(draw, (x1, y1, x2, y2), radius=radius, fill=fill)

            # --- bar border (outlined style) ------------------------------
            if th.bar_border:
                border_c = _lighten(base_rgb, 0.2)
                _draw_rounded_rect(
                    draw, (x1, y1, x2, y2), radius=radius,
                    outline=(*border_c, min(alpha, 180)),
                    width=th.bar_border_width,
                )

            # --- team stripe (thin left-edge stripe) ----------------------
            if th.bar_team_stripe:
                stripe_w = max(4, bar_h // 6)
                stripe_rgb = _lighten(base_rgb, 0.35)
                _draw_rounded_rect(
                    draw,
                    (x1, y1, x1 + stripe_w, y2),
                    radius=min(radius, stripe_w // 2),
                    fill=(*stripe_rgb, alpha),
                )

            # --- highlight strip (top 30%) --------------------------------
            if th.show_highlight_strip:
                hl_h = max(1, int(bar_h * 0.30))
                hl_rgb = _lighten(base_rgb, 0.25)
                _draw_rounded_rect(
                    draw, (x1, y1, x2, y1 + hl_h),
                    radius=min(radius, hl_h // 2),
                    fill=(*hl_rgb, min(alpha, 120)),
                )

            # --- shadow strip (bottom 18%) --------------------------------
            if th.show_shadow_strip:
                sh_h = max(1, int(bar_h * 0.18))
                sh_rgb = _darken(base_rgb, 0.25)
                _draw_rounded_rect(
                    draw, (x1, y2 - sh_h, x2, y2),
                    radius=min(radius, sh_h // 2),
                    fill=(*sh_rgb, min(alpha, 120)),
                )

            # --- leader effects -------------------------------------------
            if is_leader:
                if th.leader_glow:
                    glow_c = base_rgb
                    if th.leader_glow_color != "team":
                        glow_c = _hex_to_rgb(th.leader_glow_color)
                    glow = Image.new("RGBA", (bar_w + 24, bar_h + 24), (0, 0, 0, 0))
                    gd = ImageDraw.Draw(glow)
                    gd.rounded_rectangle(
                        [0, 0, bar_w + 23, bar_h + 23],
                        radius=radius + 6,
                        fill=(*glow_c, 50),
                    )
                    glow = glow.filter(ImageFilter.GaussianBlur(radius=12))
                    img.paste(glow, (x1 - 12, y1 - 12), glow)
                    draw = ImageDraw.Draw(img)

                if th.leader_outline:
                    outline_c = accent_c
                    _draw_rounded_rect(
                        draw, (x1 - 2, y1 - 2, x2 + 2, y2 + 2),
                        radius=radius + 2,
                        outline=(*outline_c, 180), width=3,
                    )

                if th.leader_underline:
                    line_c = _hex_to_rgb(th.accent_color)
                    underline_h = max(3, bar_h // 10)
                    draw.rectangle(
                        [x1, y2 + 2, x2, y2 + underline_h + 2],
                        fill=(*line_c, 200),
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
                hs_size = max(16, bar_h - 6)
                hs = _load_headshot(
                    bar.player, self.cfg.headshot_dir, hs_size, th,
                    team_color=base_rgb,
                )
                if hs is not None:
                    if th.headshot_position == "before-bar":
                        hs_x = x1 - hs_size - 8
                    else:
                        hs_x = x1 + 6
                    hs_y = y1 + (bar_h - hs_size) // 2

                    # Draw a colored ring behind the headshot to hide
                    # any white fringe artifacts at the edges.
                    ring_pad = 3  # ring extends 3 px beyond headshot
                    ring_size = hs_size + ring_pad * 2
                    ring = Image.new("RGBA", (ring_size, ring_size), (0, 0, 0, 0))
                    rd = ImageDraw.Draw(ring)
                    if th.headshot_shape == "circle":
                        rd.ellipse(
                            [0, 0, ring_size - 1, ring_size - 1],
                            fill=(*base_rgb, 255),
                        )
                    elif th.headshot_shape == "rounded":
                        rd.rounded_rectangle(
                            [0, 0, ring_size - 1, ring_size - 1],
                            radius=ring_size // 6,
                            fill=(*base_rgb, 255),
                        )
                    else:
                        rd.rectangle(
                            [0, 0, ring_size - 1, ring_size - 1],
                            fill=(*base_rgb, 255),
                        )
                    img.paste(ring, (hs_x - ring_pad, hs_y - ring_pad), ring)

                    img.paste(hs, (hs_x, hs_y), hs)
                    draw = ImageDraw.Draw(img)

            # --- rank number (left of name) -------------------------------
            if th.show_rank_numbers and not th.rank_giant_watermark:
                rank_num = int(bar.rank) + 1
                if th.rank_number_style == "padded":
                    rank_text = f"{rank_num:02d}"
                elif th.rank_number_style == "badge":
                    rank_text = str(rank_num)
                else:
                    rank_text = str(rank_num)
                rw, rh = _text_size(draw, rank_text, self.font_rank)

                # Apply label case to name for width measurement.
                name_for_measure = bar.player
                if th.label_case == "upper":
                    name_for_measure = name_for_measure.upper()
                tw_name = _text_size(draw, name_for_measure, self.font_name)[0]

                if th.rank_number_style == "badge":
                    badge_size = max(rw, rh) + 12
                    badge_x = x1 - tw_name - badge_size - 16
                    badge_y = y1 + (bar_h - badge_size) // 2
                    draw.ellipse(
                        [badge_x, badge_y, badge_x + badge_size, badge_y + badge_size],
                        fill=(*accent_c, 200),
                    )
                    draw.text(
                        (badge_x + (badge_size - rw) // 2,
                         badge_y + (badge_size - rh) // 2),
                        rank_text, fill=(255, 255, 255, 240), font=self.font_rank,
                    )
                else:
                    rank_x = x1 - tw_name - rw - 18
                    rank_y = y1 + (bar_h - rh) // 2
                    draw.text(
                        (rank_x, rank_y), rank_text,
                        fill=(*text2_c, int(alpha * 0.7)), font=self.font_rank,
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

            if bar_w > vw + 20:
                val_x = x2 - vw - 10
                val_color = (*text_c, alpha)
            else:
                val_x = x2 + 10
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
                fill=(*title_c, 240),
                font=self.font_title, anchor=title_anchor,
            )
        if self.cfg.subtitle:
            draw.text(
                (title_x, int(self.H * 0.04 + 52 * (self.H / 1080))),
                self.cfg.subtitle,
                fill=(*text2_c, 200),
                font=self.font_subtitle, anchor=title_anchor,
            )

        # --- branding tag -------------------------------------------------
        if th.show_branding_tag and th.branding_text:
            bc = _hex_to_rgb(th.branding_color)
            btw, bth = _text_size(draw, th.branding_text, self.font_branding)
            bx = self._margin_right + 10
            by = int(self.H * 0.04 + 95 * (self.H / 1080))
            # Tag background pill.
            pad_x, pad_y = 8, 4
            draw.rounded_rectangle(
                [bx - pad_x, by - pad_y, bx + btw + pad_x, by + bth + pad_y],
                radius=4,
                fill=(*bc, 220),
            )
            draw.text((bx, by), th.branding_text, fill=(255, 255, 255, 245),
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

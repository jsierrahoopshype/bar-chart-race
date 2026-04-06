"""Pillow/PIL frame renderer — NO matplotlib.

Renders each :class:`~bar_race.animate.FrameState` into a raw RGBA
:class:`PIL.Image.Image`.  All visual decisions are driven by the
:class:`~bar_race.themes.Theme` object.
"""

from __future__ import annotations

import math
import os
import unicodedata
from pathlib import Path
from typing import Optional

# Project root — two directories above this file (src/bar_race/render.py).
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from bar_race.animate import BarState, FrameState
from bar_race.config import (
    Config,
    FALLBACK_PALETTE,
    NBA_TEAM_COLORS,
    VideoPreset,
)
from bar_race.player_teams import PLAYER_TEAM_MAP
from bar_race.themes import Theme, get_theme

# ---------------------------------------------------------------------------
# Month abbreviation helper
# ---------------------------------------------------------------------------

_MONTH_ABBREVS: list[tuple[str, str]] = [
    ("January", "Jan"), ("February", "Feb"), ("March", "Mar"),
    ("April", "Apr"), ("May", "May"), ("June", "Jun"),
    ("July", "Jul"), ("August", "Aug"), ("September", "Sep"),
    ("October", "Oct"), ("November", "Nov"), ("December", "Dec"),
]


def _abbreviate_months(text: str) -> str:
    """Replace full month names with 3-letter abbreviations in *text*."""
    for full, abbr in _MONTH_ABBREVS:
        text = text.replace(full, abbr)
    return text


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

    color = None
    # 1. Use team from data if available.
    if use_team and bar.team and bar.team in NBA_TEAM_COLORS:
        color = NBA_TEAM_COLORS[bar.team]
    # 2. Fall back to iconic team map.
    if color is None and bar.player in PLAYER_TEAM_MAP:
        team = PLAYER_TEAM_MAP[bar.player]
        if team in NBA_TEAM_COLORS:
            color = NBA_TEAM_COLORS[team]
    # 3. Fall back to palette cycling.
    if color is None:
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


def _load_bg_image(path: str, width: int, height: int) -> Image.Image:
    """Load a background image, resize to cover, center-crop to exact size.

    Uses LANCZOS for quality.  Returns an unmodified RGBA image — callers
    must NOT layer vignette, gradient, or noise on top when the source
    image already contains those effects (e.g. mesh3.jpg).
    """
    img = Image.open(path).convert("RGB")
    # Cover: scale up so the *smaller* dimension matches, then center-crop.
    src_w, src_h = img.size
    scale = max(width / src_w, height / src_h)
    new_w = int(src_w * scale)
    new_h = int(src_h * scale)
    img = img.resize((new_w, new_h), Image.LANCZOS)
    # Center-crop to exact target size.
    left = (new_w - width) // 2
    top = (new_h - height) // 2
    img = img.crop((left, top, left + width, top + height))
    # Convert to RGBA (fully opaque) so it composites correctly.
    return img.convert("RGBA")


def _build_background(theme: Theme, width: int, height: int) -> Image.Image:
    # If a background image is set, use it instead of gradient.
    if theme.bg_image:
        img_path = theme.bg_image
        if not os.path.isabs(img_path):
            img_path = os.path.join(PROJECT_ROOT, img_path)
        print(f"[render] bg_image resolved: {img_path}  exists={os.path.exists(img_path)}")
        if os.path.exists(img_path):
            return _load_bg_image(img_path, width, height)

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

# ---------------------------------------------------------------------------
# Fuzzy headshot name matching
# ---------------------------------------------------------------------------

# Directory index: built once per directory, maps normalised keys → Path.
_hs_dir_index: dict[str, dict[str, Path]] = {}
_hs_last_name_index: dict[str, dict[str, list[Path]]] = {}


def _to_ascii(s: str) -> str:
    """Fold Unicode to ASCII (e.g. Dončić → Doncic, Şengün → Sengun)."""
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")


def _normalize_key(name: str) -> str:
    """Normalise a player name for fuzzy matching.

    Pipeline: ASCII-fold → strip punctuation → lowercase → collapse spaces.
    """
    s = _to_ascii(name)
    s = s.replace("'", "").replace("-", " ").replace(".", "")
    return " ".join(s.lower().split())


def _first_last_key(name: str) -> str:
    """Extract 'first last' from a name, skipping middle parts and suffixes."""
    parts = _normalize_key(name).split()
    # Strip trailing suffixes.
    while parts and parts[-1] in ("jr", "sr", "ii", "iii", "iv"):
        parts.pop()
    if len(parts) >= 2:
        return f"{parts[0]} {parts[-1]}"
    return " ".join(parts)


def _nospaces_key(name: str) -> str:
    """Normalise then remove all spaces (catches 'Jo Jo' vs 'Jojo')."""
    return _normalize_key(name).replace(" ", "")


def _build_hs_index(directory: str) -> None:
    """Scan *directory* once and populate the lookup indices."""
    if directory in _hs_dir_index:
        return
    idx: dict[str, Path] = {}
    last_idx: dict[str, list[Path]] = {}
    base = Path(directory)
    for f in base.iterdir():
        if not f.is_file() or f.suffix.lower() not in (".png", ".jpg", ".jpeg", ".webp"):
            continue
        if f.stem.startswith("_"):
            continue
        stem = f.stem
        # Key 1: exact stem (case-sensitive).
        idx[stem] = f
        # Key 2: normalised key (lowercase, ASCII, no punctuation).
        nk = _normalize_key(stem)
        idx.setdefault(nk, f)
        # Key 3: lowercase stem (case-insensitive exact).
        idx.setdefault(stem.lower(), f)
        # Key 4: no-spaces key (catches "Jo Jo" ↔ "Jojo").
        idx.setdefault(_nospaces_key(stem), f)
        # Key 5: first+last only (skips middle initials / suffixes).
        idx.setdefault(_first_last_key(stem), f)
        # Key 6: name-order reversal (last first → first last).
        nk_parts = nk.split()
        if len(nk_parts) == 2:
            idx.setdefault(f"{nk_parts[1]} {nk_parts[0]}", f)
        # Last-name index.
        parts = stem.split()
        if parts:
            ln = parts[-1].lower()
            last_idx.setdefault(ln, []).append(f)
    _hs_dir_index[directory] = idx
    _hs_last_name_index[directory] = last_idx


def _find_headshot_file(player: str, directory: str) -> Optional[Path]:
    """Find a headshot file for *player* using fuzzy matching.

    Lookup order:
      1. Exact filename match
      2. ASCII-folded + punctuation-stripped normalised key
      3. Case-insensitive match
      4. Last-name-only match (if exactly one file matches)
    The directory is indexed once; all lookups are O(1).
    """
    _build_hs_index(directory)
    idx = _hs_dir_index[directory]

    # 1. Exact stem.
    hit = idx.get(player)
    if hit is not None:
        return hit

    # 2. Normalised key (ASCII-folded, no punctuation, lowercase).
    nk = _normalize_key(player)
    hit = idx.get(nk)
    if hit is not None:
        return hit

    # 3. Case-insensitive.
    hit = idx.get(player.lower())
    if hit is not None:
        return hit

    # 4. No-spaces key (catches "Jo Jo White" ↔ "Jojo White").
    hit = idx.get(_nospaces_key(player))
    if hit is not None:
        return hit

    # 5. First+last only (skips middle initials, "World B. Free" → "world free").
    hit = idx.get(_first_last_key(player))
    if hit is not None:
        return hit

    # 6. Try without suffixes (Jr., III, II — CSV lacks them but file has them).
    stripped = _normalize_key(player)
    for suffix in (" jr", " sr", " iii", " ii", " iv"):
        if stripped.endswith(suffix):
            hit = idx.get(stripped[: -len(suffix)].rstrip())
            if hit is not None:
                return hit

    # 7. Try ADDING suffixes (CSV has "Larry Nance", file is "Larry Nance Jr.").
    for suffix in (" jr", " iii", " ii"):
        hit = idx.get(nk + suffix)
        if hit is not None:
            return hit

    # 8. Name-order reversal ("Ha Seung-Jin" ↔ "Seung-Jin Ha").
    nk_parts = nk.split()
    if len(nk_parts) >= 2:
        # Move last to front: "ha seung jin" → "jin ha seung".
        rev1 = f"{nk_parts[-1]} {' '.join(nk_parts[:-1])}"
        # Move first to back: "ha seung jin" → "seung jin ha".
        rev2 = f"{' '.join(nk_parts[1:])} {nk_parts[0]}"
        for rev in (rev1, rev2):
            hit = idx.get(rev)
            if hit is not None:
                return hit
            hit = idx.get(rev.replace(" ", ""))
            if hit is not None:
                return hit

    # 9. Nickname / abbreviated first name fallback.
    #    "Steve Smith" → "Steven Smith", "Clar. Weatherspoon" → "Clarence …"
    #    Match if first 4+ chars of first name match and last name is exact.
    if len(nk_parts) >= 2:
        first_prefix = nk_parts[0][:4] if len(nk_parts[0]) >= 4 else nk_parts[0]
        last = nk_parts[-1]
        last_matches = _hs_last_name_index.get(directory, {}).get(
            _to_ascii(last), []
        )
        for candidate in last_matches:
            cstem = _normalize_key(candidate.stem)
            cparts = cstem.split()
            if cparts and cparts[0].startswith(first_prefix):
                return candidate

    return None


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


def _apply_shape_mask(img: Image.Image, shape: str, size: int) -> Image.Image:
    """Apply a shape mask (circle, rounded, square) to an image."""
    mask = Image.new("L", (size, size), 0)
    md = ImageDraw.Draw(mask)
    if shape == "circle":
        md.ellipse([0, 0, size - 1, size - 1], fill=255)
    elif shape == "rounded":
        md.rounded_rectangle([0, 0, size - 1, size - 1],
                             radius=size // 6, fill=255)
    else:  # square
        md.rectangle([0, 0, size - 1, size - 1], fill=255)
    img.putalpha(mask)
    return img


def _apply_border(img: Image.Image, shape: str, size: int,
                  border_c: tuple[int, int, int]) -> Image.Image:
    """Draw a border outline on the headshot image."""
    bw = max(2, size // 30)
    bordered = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    bd = ImageDraw.Draw(bordered)
    if shape == "circle":
        bd.ellipse([0, 0, size - 1, size - 1],
                   outline=(*border_c, 220), width=bw)
    elif shape == "rounded":
        bd.rounded_rectangle([0, 0, size - 1, size - 1],
                             radius=size // 6,
                             outline=(*border_c, 220), width=bw)
    else:
        bd.rectangle([0, 0, size - 1, size - 1],
                     outline=(*border_c, 220), width=bw)
    return Image.alpha_composite(img, bordered)


def _resolve_border_color(theme: Theme,
                          team_color: tuple[int, int, int] | None,
                          ) -> tuple[int, int, int]:
    border_c = _hex_to_rgb(theme.accent_color)
    if theme.headshot_border_color == "team" and team_color:
        border_c = team_color
    elif theme.headshot_border_color not in ("team", "accent"):
        border_c = _hex_to_rgb(theme.headshot_border_color)
    return border_c


def _load_headshot(
    player: str, directory: str, size: int, theme: Theme,
    team_color: tuple[int, int, int] | None = None,
    bar_h: int = 0,
) -> Optional[Image.Image]:
    """Load, process, and cache a headshot based on headshot_style.

    Styles:
      circle     — circular clip with colored ring behind it
      shrink-pad — 80 % headshot centred on filled circle of bar color
      vignette   — radial gradient alpha fade in outer 12 %
      hard-alpha — force all pixels to fully opaque or transparent
      rectangle  — square crop, no circle, full bar height
    """
    _MIN_HEADSHOT_BYTES = 15_000  # below this = silhouette placeholder

    style = theme.headshot_style
    # For rectangle: landscape orientation — width > height.
    if style == "rectangle" and bar_h > 0:
        rect_h = bar_h
        rect_w = max(1, int(bar_h * 1.4))
        effective_size = rect_h
    else:
        rect_h = rect_w = size
        effective_size = size

    cache_key = f"{player}:{effective_size}:{theme.slug}"
    if cache_key in _headshot_cache:
        return _headshot_cache[cache_key]

    if theme.headshot_shape == "none":
        _headshot_cache[cache_key] = None
        return None

    filepath = _find_headshot_file(player, directory)
    result = None
    if filepath is not None:
        # Skip silhouettes: files under 15 KB are NBA CDN placeholders.
        if filepath.stat().st_size < _MIN_HEADSHOT_BYTES:
            _headshot_cache[cache_key] = None
            return None

        raw = Image.open(filepath).convert("RGBA")

        if style == "rectangle":
            # Full width, crop top 80 % of height (face/upper body).
            src_w, src_h = raw.size
            crop_h = int(src_h * 0.80)
            raw = raw.crop((0, 0, src_w, max(1, crop_h)))
            result = raw.resize((rect_w, rect_h), Image.LANCZOS)

        elif style == "shrink-pad":
            # 80 % headshot centred on filled circle of team color.
            img = raw.resize((effective_size, effective_size), Image.LANCZOS)
            img = _remove_white_halo(img)
            inner_size = int(effective_size * 0.80)
            inner = img.resize((inner_size, inner_size), Image.LANCZOS)
            # Create circle filled with bar color.
            pad = Image.new("RGBA", (effective_size, effective_size), (0, 0, 0, 0))
            pd_draw = ImageDraw.Draw(pad)
            fill_c = team_color if team_color else (128, 128, 128)
            shape = theme.headshot_shape
            if shape == "circle":
                pd_draw.ellipse([0, 0, effective_size - 1, effective_size - 1],
                                fill=(*fill_c, 255))
            elif shape == "rounded":
                pd_draw.rounded_rectangle([0, 0, effective_size - 1, effective_size - 1],
                                          radius=effective_size // 6, fill=(*fill_c, 255))
            else:
                pd_draw.rectangle([0, 0, effective_size - 1, effective_size - 1],
                                  fill=(*fill_c, 255))
            # Apply shape mask to inner headshot.
            inner = _apply_shape_mask(inner, shape, inner_size)
            offset = (effective_size - inner_size) // 2
            pad.paste(inner, (offset, offset), inner)
            # Apply outer shape mask.
            pad = _apply_shape_mask(pad, shape, effective_size)
            if theme.headshot_border:
                pad = _apply_border(pad, shape, effective_size,
                                    _resolve_border_color(theme, team_color))
            result = pad

        elif style == "vignette":
            img = raw.resize((effective_size, effective_size), Image.LANCZOS)
            img = _remove_white_halo(img)
            img = _apply_shape_mask(img, theme.headshot_shape, effective_size)
            # Radial gradient alpha: centre=255, fade starts at 88 % radius.
            arr = np.array(img)
            cx = cy = effective_size / 2.0
            max_r = effective_size / 2.0
            fade_start = 0.88
            ys, xs = np.mgrid[0:effective_size, 0:effective_size]
            dist = np.sqrt((xs - cx) ** 2 + (ys - cy) ** 2) / max_r
            # Pixels inside fade_start: alpha unchanged; outside: fade to 0.
            fade = np.clip((1.0 - dist) / (1.0 - fade_start), 0.0, 1.0)
            arr[:, :, 3] = (arr[:, :, 3].astype(np.float32) * fade).astype(np.uint8)
            result = Image.fromarray(arr, "RGBA")

        elif style == "hard-alpha":
            img = raw.resize((effective_size, effective_size), Image.LANCZOS)
            img = _remove_white_halo(img)
            img = _apply_shape_mask(img, theme.headshot_shape, effective_size)
            # Force alpha to binary: >= 128 → 255, else 0.
            arr = np.array(img)
            arr[:, :, 3] = np.where(arr[:, :, 3] >= 128, 255, 0).astype(np.uint8)
            img = Image.fromarray(arr, "RGBA")
            if theme.headshot_border:
                img = _apply_border(img, theme.headshot_shape, effective_size,
                                    _resolve_border_color(theme, team_color))
            result = img

        else:
            # Default "circle" style.
            img = raw.resize((effective_size, effective_size), Image.LANCZOS)
            img = _remove_white_halo(img)
            img = _apply_shape_mask(img, theme.headshot_shape, effective_size)
            if theme.headshot_border:
                img = _apply_border(img, theme.headshot_shape, effective_size,
                                    _resolve_border_color(theme, team_color))
            result = img

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

        # Custom font directory: map weights to specific font files.
        if th.font_custom_dir:
            custom_dir_str = th.font_custom_dir
            if not os.path.isabs(custom_dir_str):
                custom_dir_str = os.path.join(PROJECT_ROOT, custom_dir_str)
            custom_dir = Path(custom_dir_str)
            _custom_map = {
                "bold": "Futura_Today_Bold.otf",
                "medium": "Futura_Today_DemiBold.otf",
                "regular": "Futura_Today_Normal.otf",
                "light": "Futura_Today_Light.otf",
            }
            all_found = True
            for weight, filename in _custom_map.items():
                candidate = custom_dir / filename
                if candidate.is_file():
                    if weight == "bold":
                        bold_path = str(candidate)
                    elif weight == "medium":
                        medium_path = str(candidate)
                    elif weight == "regular":
                        regular_path = str(candidate)
                    elif weight == "light":
                        light_path = str(candidate)
                else:
                    all_found = False
            # If not all custom fonts found, fall back to standard resolution.
            if not all_found:
                bold_path = cfg.font_bold
                medium_path = cfg.font_medium
                regular_path = cfg.font_regular
                light_path = cfg.font_light
        # Override with font_family if config used defaults (auto-resolved).
        elif family != "sans":
            bold_path = _resolve_font(family, "bold")
            medium_path = _resolve_font(family, "medium")
            regular_path = _resolve_font(family, "regular")
            light_path = _resolve_font(family, "light")

        self.font_title = _load_font(bold_path, max(12, int(44 * scale * th.title_scale)))
        self.font_subtitle = _load_font(medium_path, max(10, int(26 * scale)))
        self.font_name = _load_font(medium_path, max(10, int(24 * scale)))
        self.font_tenure = _load_font(regular_path, max(8, int(17 * scale)))
        self.font_value = _load_font(regular_path, max(10, int(20 * scale)))
        self.font_date = _load_font(bold_path, max(14, int(72 * scale)))
        self.font_watermark = _load_font(light_path, max(10, int(18 * scale)))
        self.font_panel = _load_font(light_path, max(8, int(14 * 1.15 * 1.12 * scale)))
        self.font_rank = _load_font(bold_path, max(10, int(20 * scale)))
        self.font_rank_giant = _load_font(bold_path, max(20, int(90 * scale)))
        self.font_branding = _load_font(bold_path, max(8, int(14 * scale)))

        # Precompute background.
        self._bg = _build_background(th, self.W, self.H)
        if th.vignette and not th.bg_image:
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
        if th.label_position == "inside":
            self._margin_left = int(self.W * 0.08)
        else:
            self._margin_left = int(self.W * 0.22)
        self._margin_right = int(self.W * 0.05)
        self._bar_area_top = int(self.H * 0.16)
        self._bar_area_bottom = int(self.H * 0.86)

        # Preload logo image if specified.
        self._logo: Optional[Image.Image] = None
        if th.logo_path:
            logo_file = th.logo_path
            if not os.path.isabs(logo_file):
                logo_file = os.path.join(PROJECT_ROOT, logo_file)
            if os.path.exists(logo_file):
                try:
                    logo = Image.open(logo_file).convert("RGBA")
                    logo_h = max(20, int(80 * scale * th.title_scale))
                    logo_w = int(logo.width * logo_h / logo.height)
                    self._logo = logo.resize((logo_w, logo_h), Image.LANCZOS)
                except Exception:
                    pass

    def _draw_rank_number(
        self, draw: ImageDraw.Draw, bar: BarState,
        x1: int, y1: int, bar_h: int, name_tw: int,
        text2_c: tuple[int, int, int],
        accent_c: tuple[int, int, int],
        alpha: int,
    ) -> None:
        """Draw rank number to the left of the player name."""
        th = self.theme
        rank_num = int(bar.rank) + 1
        if th.rank_number_style == "padded":
            rank_text = f"{rank_num:02d}"
        else:
            rank_text = str(rank_num)
        rw, rh = _text_size(draw, rank_text, self.font_rank)
        if th.rank_number_style == "badge":
            badge_size = max(rw, rh) + 12
            badge_x = x1 - name_tw - badge_size - 16
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
            rank_x = x1 - name_tw - rw - 18
            rank_y = y1 + (bar_h - rh) // 2
            draw.text(
                (rank_x, rank_y), rank_text,
                fill=(*text2_c, int(alpha * 0.7)), font=self.font_rank,
            )

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
            hs_right_edge = 0  # track right edge for "inside" label layout
            if self.cfg.headshot_dir:
                hs_size = max(16, bar_h - 6)
                hs = _load_headshot(
                    bar.player, self.cfg.headshot_dir, hs_size, th,
                    team_color=base_rgb, bar_h=bar_h,
                )
                if hs is not None:
                    hs_w, hs_h = hs.size

                    if th.headshot_style == "rectangle":
                        # Flush with bar left edge, full bar height.
                        hs_x = x1
                        hs_y = y1
                    elif th.headshot_position == "before-bar":
                        hs_x = x1 - hs_w - 8
                        hs_y = y1 + (bar_h - hs_h) // 2
                    else:
                        hs_x = x1 + 6
                        hs_y = y1 + (bar_h - hs_h) // 2

                    # Draw colored ring behind non-rectangle, non-vignette,
                    # non-shrink-pad styles.
                    if th.headshot_style in ("circle", "hard-alpha"):
                        ring_pad = 4
                        ring_size = hs_w + ring_pad * 2
                        ring = Image.new("RGBA", (ring_size, ring_size), (0, 0, 0, 0))
                        rd = ImageDraw.Draw(ring)
                        shape = th.headshot_shape
                        if shape == "circle":
                            rd.ellipse([0, 0, ring_size - 1, ring_size - 1],
                                       fill=(*base_rgb, 255), outline=(0, 0, 0, 77))
                        elif shape == "rounded":
                            rd.rounded_rectangle([0, 0, ring_size - 1, ring_size - 1],
                                                 radius=ring_size // 6,
                                                 fill=(*base_rgb, 255), outline=(0, 0, 0, 77))
                        else:
                            rd.rectangle([0, 0, ring_size - 1, ring_size - 1],
                                         fill=(*base_rgb, 255), outline=(0, 0, 0, 77))
                        img.paste(ring, (hs_x - ring_pad, hs_y - ring_pad), ring)

                    img.paste(hs, (hs_x, hs_y), hs)
                    hs_right_edge = hs_x + hs_w
                    draw = ImageDraw.Draw(img)

            # --- prepare text ---------------------------------------------
            name_text = bar.player
            if th.label_case == "upper":
                name_text = name_text.upper()
            elif th.label_case == "title":
                name_text = name_text.title()
            tw, th_h = _text_size(draw, name_text, self.font_name)

            val_text = f"{bar.value:,.0f}{th.value_suffix}"
            vw, vh = _text_size(draw, val_text, self.font_value)

            label_pos = th.label_position

            if label_pos == "inside":
                # --- INSIDE: name + value inside the bar ------------------
                # Text left edge: after headshot or bar left + padding.
                text_left = max(hs_right_edge + 8, x1 + 10)
                text_right = x2 - 10
                avail = text_right - text_left
                min_gap = 10  # minimum pixels between name and value

                # Dark gradient overlay on left of bar for readability.
                grad_w = min(bar_w, max(int(bar_w * 0.5), tw + vw + 40))
                if grad_w > 10 and bar_h > 2:
                    grad = Image.new("RGBA", (grad_w, bar_h), (0, 0, 0, 0))
                    g_arr = np.zeros((bar_h, grad_w, 4), dtype=np.uint8)
                    xs_g = np.linspace(1.0, 0.0, grad_w)
                    g_arr[:, :, 3] = (xs_g * 80).astype(np.uint8)
                    grad = Image.fromarray(g_arr, "RGBA")
                    img.paste(grad, (x1, y1), grad)
                    draw = ImageDraw.Draw(img)

                name_y = y1 + (bar_h - th_h) // 2
                val_y = y1 + (bar_h - vh) // 2

                # Can both name and value fit inside with a gap?
                if avail >= vw + min_gap + 30:
                    max_name_w = avail - vw - min_gap - 10
                    display_name = name_text
                    if tw > max_name_w:
                        # Abbreviate: "First Last" → "F. Last"
                        parts = name_text.split()
                        if len(parts) >= 2:
                            abbrev = f"{parts[0][0]}. {parts[-1]}"
                            aw = _text_size(draw, abbrev, self.font_name)[0]
                            if aw <= max_name_w:
                                display_name = abbrev
                            else:
                                display_name = parts[-1]  # last name only
                        else:
                            display_name = name_text[:6] + "…"

                    # Text shadow + name.
                    draw.text((text_left + 1, name_y + 1), display_name,
                              fill=(0, 0, 0, min(alpha, 120)), font=self.font_name)
                    draw.text((text_left, name_y), display_name,
                              fill=(255, 255, 255, alpha), font=self.font_name)
                    # Value right-aligned inside bar.
                    draw.text((text_right - vw + 1, val_y + 1), val_text,
                              fill=(0, 0, 0, min(alpha, 120)), font=self.font_value)
                    draw.text((text_right - vw, val_y), val_text,
                              fill=(255, 255, 255, alpha), font=self.font_value)
                else:
                    # Bar too short: name inside (abbreviated), value outside.
                    display_name = name_text
                    if tw > avail - 5:
                        parts = name_text.split()
                        if len(parts) >= 2:
                            display_name = f"{parts[0][0]}. {parts[-1]}"
                        else:
                            display_name = name_text[:6] + "…"
                    draw.text((text_left + 1, name_y + 1), display_name,
                              fill=(0, 0, 0, min(alpha, 120)), font=self.font_name)
                    draw.text((text_left, name_y), display_name,
                              fill=(255, 255, 255, alpha), font=self.font_name)
                    draw.text((x2 + 10, val_y), val_text,
                              fill=(*text2_c, alpha), font=self.font_value)

            elif label_pos == "outside-right":
                # --- OUTSIDE-RIGHT: name left of bar, value always outside --
                # Rank numbers.
                if th.show_rank_numbers and not th.rank_giant_watermark:
                    self._draw_rank_number(draw, bar, x1, y1, bar_h, tw,
                                           text2_c, accent_c, alpha)
                name_x = x1 - tw - 10
                name_y = y1 + (bar_h - th_h) // 2
                draw.text((name_x, name_y), name_text,
                          fill=(*text_c, alpha), font=self.font_name)
                val_y = y1 + (bar_h - vh) // 2
                draw.text((x2 + 10, val_y), val_text,
                          fill=(*text2_c, alpha), font=self.font_value)

            else:
                # --- OUTSIDE (default): name left, value inside/outside ----
                # Rank numbers.
                if th.show_rank_numbers and not th.rank_giant_watermark:
                    self._draw_rank_number(draw, bar, x1, y1, bar_h, tw,
                                           text2_c, accent_c, alpha)
                name_x = x1 - tw - 10
                name_y = y1 + (bar_h - th_h) // 2
                draw.text((name_x, name_y), name_text,
                          fill=(*text_c, alpha), font=self.font_name)

                if bar_w > vw + 20:
                    val_x = x2 - vw - 10
                    val_color = (*text_c, alpha)
                else:
                    val_x = x2 + 10
                    val_color = (*text2_c, alpha)
                val_y = y1 + (bar_h - vh) // 2
                draw.text((val_x, val_y), val_text,
                          fill=val_color, font=self.font_value)

        # --- date label (bottom-right, at 90% height) -----------------------
        date_c = _hex_to_rgb(th.date_color)
        date_alpha = int(255 * th.date_opacity)
        date_xy = (self.W - self._margin_right - 10,
                   int(self.H * 0.93))
        date_text = _abbreviate_months(state.date_label)
        if th.date_uppercase:
            date_text = date_text.upper()
        draw.text(
            date_xy, date_text,
            fill=(*date_c, date_alpha),
            font=self.font_date, anchor="rt",
        )

        # --- title + subtitle --------------------------------------------
        title_c = _hex_to_rgb(th.title_color)
        if th.title_position == "top-center":
            title_x = self.W // 2
            title_anchor = "mt"
        else:
            title_x = self._margin_right + 10
            title_anchor = "lt"

        # Draw logo to the left of title if available.
        logo_offset = 0
        if self._logo is not None and title_anchor == "lt":
            logo_y = int(self.H * 0.04)
            img.paste(self._logo, (title_x, logo_y), self._logo)
            logo_offset = self._logo.width + 15
            draw = ImageDraw.Draw(img)

        if self.cfg.title:
            draw.text(
                (title_x + logo_offset, int(self.H * 0.04)),
                self.cfg.title,
                fill=(*title_c, 240),
                font=self.font_title, anchor=title_anchor,
            )
        if self.cfg.subtitle:
            draw.text(
                (title_x + logo_offset, int(self.H * 0.04 + 52 * th.title_scale * (self.H / 1080))),
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

        # --- overlays ---------------------------------------------------------

        # Gap alert — small accent text above the leader bar.
        if (self.cfg.show_gap_alerts and th.show_gap_alerts
                and state.show_gap and state.bars):
            leader_bar = min(state.bars, key=lambda b: b.rank)
            if leader_bar.rank < n_bars:
                gap_text = f"+{state.gap_pct * 100:.1f}% lead"
                ly = int(self._bar_area_top + bar_gap
                         + leader_bar.rank * (bar_h + bar_gap))
                leader_bar_w = int((leader_bar.value / max(state.max_value, 1e-9))
                                   * max_bar_w)
                gx = self._margin_left + leader_bar_w
                gy = ly - 4
                draw.text((gx, gy), gap_text,
                          fill=(*accent_c, 200), font=self.font_watermark,
                          anchor="rb")

        # --- bottom panel: three columns between bars and date ---------------
        panel_y = self._bar_area_bottom + 4
        panel_max_y = int(self.H * 0.93) - 10  # stop above the date
        line_h = max(11, int(self.H * 0.014))
        header_c = (*text_c, 178)
        row_c = (*text2_c, 110)
        panel_w = int(self.W * 0.68)
        # Allocate columns: 43% / 29% / 28% so RECENT #1s has room.
        col1_w = int(panel_w * 0.43)
        col2_w = int(panel_w * 0.29)
        col_x0 = self._margin_right + 10
        col_x1 = col_x0 + col1_w
        col_x2 = col_x1 + col2_w

        # Resolve tenure column header from time_unit.
        _unit = self.cfg.time_unit.lower()
        _UNIT_LABELS = {
            "years": "YEARS", "seasons": "SEASONS", "games": "GAMES",
            "days": "DAYS", "weeks": "WEEKS", "months": "MONTHS",
        }
        _unit_label = _UNIT_LABELS.get(_unit, "YEARS")

        # LEFT: Recent #1s.
        if self.cfg.show_reign_history and state.reign_history:
            cx = col_x0
            cy = panel_y
            draw.text((cx, cy), "RECENT #1s", fill=header_c,
                      font=self.font_panel)
            cy += line_h
            for entry in state.reign_history[:5]:
                if cy + line_h > panel_max_y:
                    break
                draw.text((cx, cy), _abbreviate_months(entry), fill=row_c,
                          font=self.font_panel)
                cy += line_h

        # CENTER: Most [unit] in top N.
        if self.cfg.show_tenure_leaderboard and state.tenure_leaders:
            cx = col_x1
            cy = panel_y
            tenure_header = f"MOST {_unit_label} IN TOP 10"
            draw.text((cx, cy), tenure_header, fill=header_c,
                      font=self.font_panel)
            cy += line_h
            for entry in state.tenure_leaders[:5]:
                if cy + line_h > panel_max_y:
                    break
                draw.text((cx, cy), _abbreviate_months(entry), fill=row_c,
                          font=self.font_panel)
                cy += line_h

        # RIGHT: First to milestones.
        if self.cfg.show_milestone_records and state.milestone_records:
            cx = col_x2
            cy = panel_y
            draw.text((cx, cy), "FIRST TO", fill=header_c,
                      font=self.font_panel)
            cy += line_h
            for entry in state.milestone_records[:5]:
                if cy + line_h > panel_max_y:
                    break
                draw.text((cx, cy), _abbreviate_months(entry), fill=row_c,
                          font=self.font_panel)
                cy += line_h

        # Player counter — below subtitle in top-left.
        if state.players_seen > 0 and th.show_player_counter:
            counter_text = f"Players tracked: {state.players_seen}"
            cx = self._margin_right + 10
            cy = int(self.H * 0.04 + 80 * (self.H / 1080))
            draw.text((cx, cy), counter_text,
                      fill=(*text2_c, 100), font=self.font_watermark)

        return img

    def render_rgb_bytes(self, state: FrameState) -> bytes:
        """Render a frame and return raw RGB bytes (for ffmpeg pipe)."""
        return self.render(state).convert("RGB").tobytes()

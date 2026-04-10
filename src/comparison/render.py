"""Horizontal conveyor-belt renderer — fast-scrolling stat cards."""

from __future__ import annotations

import os
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

from comparison.config import ComparisonConfig, PROJECT_ROOT
from comparison.ingest import ComparisonData
from bar_race.render import _find_headshot_file, _load_font


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _hex(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _tsz(draw: ImageDraw.Draw, text: str, font) -> tuple[int, int]:
    try:
        bb = font.getbbox(text)
        return bb[2] - bb[0], bb[3] - bb[1]
    except AttributeError:
        return draw.textsize(text, font=font)


def _load_bg(path: str, w: int, h: int) -> Image.Image:
    img = Image.open(path).convert("RGB")
    sw, sh = img.size
    sc = max(w / sw, h / sh)
    nw, nh = int(sw * sc), int(sh * sc)
    img = img.resize((nw, nh), Image.LANCZOS)
    l, t = (nw - w) // 2, (nh - h) // 2
    return img.crop((l, t, l + w, t + h)).convert("RGBA")


def _fonts(font_dir: str) -> dict[str, str]:
    base = font_dir if os.path.isabs(font_dir) else os.path.join(PROJECT_ROOT, font_dir)
    out: dict[str, str] = {}
    for wt, fn in [("bold", "Futura_Today_Bold.otf"), ("medium", "Futura_Today_DemiBold.otf"),
                    ("regular", "Futura_Today_Normal.otf"), ("light", "Futura_Today_Light.otf")]:
        p = os.path.join(base, fn)
        out[wt] = p if os.path.isfile(p) and os.path.getsize(p) > 0 else ""
    return out


def _interleave(data: ComparisonData, lowest: list[str]) -> list[str]:
    """Alternate wins between first two players, end with closest stat."""
    if len(data.players) < 2:
        return list(data.categories)
    p0, p1 = data.players[0], data.players[1]
    w0, w1, ties = [], [], []
    for cat in data.categories:
        v = data.values.get(cat, {})
        a, b = v.get(p0, 0.0), v.get(p1, 0.0)
        low = cat in lowest
        if (not low and a > b) or (low and a < b):
            w0.append(cat)
        elif (not low and b > a) or (low and b < a):
            w1.append(cat)
        else:
            ties.append(cat)
    # Sort each group so closest margin is last (most dramatic at the end).
    def _margin(cat):
        v = data.values.get(cat, {})
        a, b = v.get(p0, 0.0), v.get(p1, 0.0)
        return abs(a - b) / max(a, b, 1)
    w0.sort(key=_margin, reverse=True)
    w1.sort(key=_margin, reverse=True)
    out: list[str] = []
    i, j, turn = 0, 0, 0
    while i < len(w0) or j < len(w1):
        if turn == 0 and i < len(w0):
            out.append(w0[i]); i += 1
        elif turn == 1 and j < len(w1):
            out.append(w1[j]); j += 1
        elif i < len(w0):
            out.append(w0[i]); i += 1
        else:
            out.append(w1[j]); j += 1
        turn = 1 - turn
    out.extend(ties)
    return out


# ---------------------------------------------------------------------------
# Card builder
# ---------------------------------------------------------------------------

_CARD_BG = (26, 26, 46)       # #1a1a2e
_CARD_BORDER = (51, 51, 51)   # #333
_WIN_BG = (204, 0, 0)         # #CC0000
_LOSE_BG = (42, 42, 42)       # #2a2a2a
_TIE_BG = (218, 165, 32)      # #DAA520


class CardBuilder:
    """Builds a single stat-comparison card image."""

    def __init__(
        self,
        card_w: int,
        card_h: int,
        font_title,
        font_name,
        font_value,
        hs_dir: str,
        winner_rgb: tuple[int, int, int] = _WIN_BG,
        loser_rgb: tuple[int, int, int] = _LOSE_BG,
        tie_rgb: tuple[int, int, int] = _TIE_BG,
    ):
        self.cw = card_w
        self.ch = card_h
        self.font_title = font_title
        self.font_name = font_name
        self.font_value = font_value
        self.hs_dir = hs_dir
        self.winner_rgb = winner_rgb
        self.loser_rgb = loser_rgb
        self.tie_rgb = tie_rgb
        self._hs_cache: dict[str, Optional[Image.Image]] = {}

    def _headshot(self, player: str, width: int, height: int) -> Optional[Image.Image]:
        key = f"{player}_{width}_{height}"
        if key in self._hs_cache:
            return self._hs_cache[key]
        hs = None
        if os.path.isdir(self.hs_dir):
            path = _find_headshot_file(player, self.hs_dir)
            if path:
                try:
                    raw = Image.open(str(path)).convert("RGBA")
                    rw, rh = raw.size
                    # Crop top 65% (face focus).
                    crop_h = int(rh * 0.65)
                    raw = raw.crop((0, 0, rw, crop_h))
                    # Scale to fill card width, center-crop to target height.
                    sc = width / raw.width
                    nw = width
                    nh = int(raw.height * sc)
                    raw = raw.resize((nw, nh), Image.LANCZOS)
                    if nh > height:
                        top = (nh - height) // 2
                        raw = raw.crop((0, top, nw, top + height))
                    elif nh < height:
                        padded = Image.new("RGBA", (nw, height), (0, 0, 0, 0))
                        padded.paste(raw, (0, 0), raw)
                        raw = padded
                    hs = raw
                except Exception:
                    pass
        self._hs_cache[key] = hs
        return hs

    def build(
        self,
        category: str,
        player_vals: list[tuple[str, float]],
        winner: str,
        runner_up: str,
        is_tie: bool,
    ) -> Image.Image:
        cw, ch = self.cw, self.ch
        card = Image.new("RGBA", (cw, ch), (*_CARD_BG, 255))
        draw = ImageDraw.Draw(card)

        # Border.
        draw.rounded_rectangle(
            [0, 0, cw - 1, ch - 1], radius=8,
            outline=(*_CARD_BORDER, 255), width=2,
        )

        # Stat title at top.
        title = category.upper()
        tw, th = _tsz(draw, title, self.font_title)
        title_y = 10
        # Truncate if needed.
        if tw > cw - 16:
            while tw > cw - 16 and len(title) > 5:
                title = title[:-1]
                tw, th = _tsz(draw, title, self.font_title)
            title = title.rstrip() + "…"
            tw, th = _tsz(draw, title, self.font_title)
        draw.text(((cw - tw) // 2, title_y), title,
                  fill=(255, 255, 255, 210), font=self.font_title)

        # Player sections.
        n = len(player_vals)
        body_top = title_y + th + 8
        body_h = ch - body_top - 6
        section_h = body_h // max(n, 1)

        for pi, (player, val) in enumerate(player_vals):
            sy = body_top + pi * section_h
            sh = section_h - 2  # 2px gap between sections

            # Section background (winner/loser).
            if is_tie:
                bg = self.tie_rgb
            elif player == winner:
                bg = self.winner_rgb
            else:
                bg = self.loser_rgb
            # Draw section background within card border.
            pad = 3
            draw.rounded_rectangle(
                [pad, sy, cw - pad, sy + sh], radius=6,
                fill=(*bg, 255),
            )

            # Headshot: fills card width, generous height.
            hs_w = cw - pad * 2
            hs_h = int(sh * 0.55)
            hs = self._headshot(player, hs_w, hs_h)
            if hs is not None:
                card.paste(hs, (pad, sy), hs)
                draw = ImageDraw.Draw(card)

            # Player name.
            name_y = sy + hs_h + 2
            nw, nh = _tsz(draw, player, self.font_name)
            draw.text(((cw - nw) // 2, name_y), player,
                      fill=(255, 255, 255, 240), font=self.font_name)

            # Value.
            vt = f"{val:,.0f}" if val == int(val) else f"{val:,.1f}"
            vw, vh = _tsz(draw, vt, self.font_value)
            val_y = name_y + nh + 2
            draw.text(((cw - vw) // 2, val_y), vt,
                      fill=(255, 255, 255, 255), font=self.font_value)

            # Divider line between players (except after last).
            if pi < n - 1:
                div_y = sy + sh + 1
                draw.line(
                    [(cw // 6, div_y), (cw - cw // 6, div_y)],
                    fill=(255, 255, 255, 50), width=1,
                )

        return card


# ---------------------------------------------------------------------------
# ConveyorRenderer
# ---------------------------------------------------------------------------

class ConveyorRenderer:
    """Frame-by-frame horizontal conveyor belt of stat cards."""

    def __init__(self, cfg: ComparisonConfig, data: ComparisonData) -> None:
        self.cfg = cfg
        self.data = data
        self.preset = cfg.get_preset()
        self.W = self.preset.width
        self.H = self.preset.height

        f = _fonts(cfg.font_dir)
        s = min(self.W, self.H) / 1080

        self.font_title = _load_font(f["bold"], max(14, int(36 * s)))
        self.font_subtitle = _load_font(f["medium"], max(10, int(20 * s)))
        self.font_card_title = _load_font(f["bold"], max(10, int(20 * s)))
        self.font_card_name = _load_font(f["bold"], max(10, int(16 * s)))
        self.font_card_value = _load_font(f["bold"], max(16, int(50 * s)))

        # Background.
        bg_path = cfg.resolve_path(cfg.bg_image)
        if os.path.isfile(bg_path):
            self._bg = _load_bg(bg_path, self.W, self.H)
        else:
            self._bg = Image.new("RGBA", (self.W, self.H), (10, 10, 20, 255))

        # Title overlay (baked once).
        self._bg_titled = self._bg.copy()
        draw = ImageDraw.Draw(self._bg_titled)
        ty = int(self.H * 0.015)
        if cfg.title:
            tw, _ = _tsz(draw, cfg.title, self.font_title)
            draw.text(((self.W - tw) // 2, ty), cfg.title,
                      fill=(255, 255, 255, 245), font=self.font_title)
        if cfg.subtitle:
            sw, _ = _tsz(draw, cfg.subtitle, self.font_subtitle)
            sty = ty + int(self.H * 0.04)
            draw.text(((self.W - sw) // 2, sty), cfg.subtitle,
                      fill=(255, 255, 255, 178), font=self.font_subtitle)

        # Card dimensions — derive from cards_visible.
        n_vis = max(2, min(6, cfg.cards_visible))
        self.card_w = int(self.W / (n_vis + 0.3))
        self.card_gap = max(8, int(self.W * 0.012))
        self.card_stride = self.card_w + self.card_gap
        self.card_h = int(self.H * 0.80)
        self.card_top = int(self.H * 0.08)
        self._scroll_speed = cfg.scroll_speed

        # Headshot dir.
        hs_dir = cfg.resolve_path(cfg.headshot_dir)

        # Card builder with configurable colors.
        self._builder = CardBuilder(
            self.card_w, self.card_h,
            self.font_card_title, self.font_card_name, self.font_card_value,
            hs_dir,
            winner_rgb=_hex(cfg.winner_color),
            loser_rgb=_hex(cfg.loser_color),
            tie_rgb=_hex(cfg.runner_up_color),
        )

        # Order categories.
        ordered = _interleave(data, cfg.lowest_is_better)

        # Precompute card metadata + images.
        self.card_metas: list[dict] = []
        self.card_images: list[Image.Image] = []
        for cat in ordered:
            vals = data.values.get(cat, {})
            pv = [(p, vals.get(p, 0.0)) for p in data.players]
            low = cat in cfg.lowest_is_better
            ranked = sorted(pv, key=lambda x: x[1], reverse=not low)
            tie = len(ranked) >= 2 and ranked[0][1] == ranked[1][1]
            w = "" if tie else (ranked[0][0] if ranked else "")
            ru = "" if tie else (ranked[1][0] if len(ranked) > 1 else "")
            meta = {"cat": cat, "pv": pv, "winner": w, "runner_up": ru, "tie": tie}
            self.card_metas.append(meta)
            self.card_images.append(
                self._builder.build(cat, pv, w, ru, tie)
            )

    def timing(self) -> dict:
        fps = self.cfg.fps
        n = len(self.card_images)
        # Speed: one card crosses frame center in scroll_speed seconds.
        ppf = self.card_stride / (self._scroll_speed * fps)
        # Total scroll: from first card entering right edge to last card
        # fully visible (centered).
        total_scroll = self.W + n * self.card_stride
        scroll_frames = int(total_scroll / ppf)
        intro = int(2.0 * fps)
        outro = int(3.0 * fps)
        return {
            "ppf": ppf,
            "intro": intro,
            "scroll": scroll_frames,
            "outro": outro,
            "total": intro + scroll_frames + outro,
        }

    def render_frame(self, fi: int, t: dict) -> Image.Image:
        img = self._bg_titled.copy()
        if fi < t["intro"]:
            return img

        scroll_fi = fi - t["intro"]
        if scroll_fi > t["scroll"]:
            scroll_fi = t["scroll"]  # hold last position during outro
        offset = scroll_fi * t["ppf"]

        for ci, cimg in enumerate(self.card_images):
            cx = int(self.W - offset + ci * self.card_stride)
            if cx + self.card_w < 0:
                continue
            if cx > self.W:
                continue
            img.paste(cimg, (cx, self.card_top), cimg)

        return img

    def render_frame_bytes(self, fi: int, t: dict) -> bytes:
        return self.render_frame(fi, t).convert("RGB").tobytes()

    def render_card_png(self, idx: int) -> Image.Image:
        """Export a single card as standalone PNG with background."""
        pad = 20
        w = self.card_w + pad * 2
        h = self.card_h + pad * 2
        bg_path = self.cfg.resolve_path(self.cfg.bg_image)
        bg = _load_bg(bg_path, w, h) if os.path.isfile(bg_path) else Image.new("RGBA", (w, h), (10, 10, 20, 255))
        bg.paste(self.card_images[idx], (pad, pad), self.card_images[idx])
        return bg

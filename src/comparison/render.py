"""Horizontal conveyor-belt renderer — winner-photo stat cards."""

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
    """Alternate wins between first two players, closest margin last."""
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
# CardBuilder — winner-photo design
# ---------------------------------------------------------------------------

_CARD_BG = (26, 26, 46)
_CARD_BORDER = (60, 60, 60)
_CAT_BAR_BG = (240, 240, 240)
_CAT_BAR_TEXT = (20, 20, 20)
_WIN_BG = (204, 0, 0)
_LOSE_BG = (85, 85, 85)
_TIE_BG = (218, 165, 32)
_HEADSHOT_BG = (0, 151, 167)  # teal #0097a7


class CardBuilder:
    """Builds a card: winner photo on top, category bar, then player rows."""

    def __init__(
        self, card_w: int, card_h: int,
        font_cat, font_row, font_row_small,
        hs_dir: str, bold_path: str,
        winner_rgb=(204, 0, 0), loser_rgb=(85, 85, 85), tie_rgb=(218, 165, 32),
    ):
        self.cw = card_w
        self.ch = card_h
        self.font_cat = font_cat
        self.font_row = font_row
        self.font_row_small = font_row_small
        self.hs_dir = hs_dir
        self._bold_path = bold_path
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
                    # Crop top 70% for face focus.
                    crop_h = int(rh * 0.70)
                    raw = raw.crop((0, 0, rw, crop_h))
                    # Scale to fill width, center-crop height.
                    sc = width / raw.width
                    nw = width
                    nh = int(raw.height * sc)
                    raw = raw.resize((nw, nh), Image.LANCZOS)
                    if nh > height:
                        top = (nh - height) // 2
                        raw = raw.crop((0, top, nw, top + height))
                    elif nh < height:
                        padded = Image.new("RGBA", (nw, height), (0, 0, 0, 0))
                        padded.paste(raw, (0, (height - nh) // 2), raw)
                        raw = padded
                    hs = raw
                except Exception:
                    pass
        self._hs_cache[key] = hs
        return hs

    def _fit_text(self, draw, text, font, max_w):
        """Shrink font until text fits max_w. Returns (font, text_w, text_h)."""
        tw, th = _tsz(draw, text, font)
        if tw <= max_w:
            return font, tw, th
        size = getattr(font, 'size', 0)
        while tw > max_w and size > 8:
            size = int(size * 0.9)
            font = _load_font(self._bold_path, size)
            tw, th = _tsz(draw, text, font)
        return font, tw, th

    def build(
        self, category: str,
        player_vals: list[tuple[str, float]],
        winner: str, runner_up: str, is_tie: bool,
    ) -> Image.Image:
        cw, ch = self.cw, self.ch
        n = len(player_vals)
        card = Image.new("RGBA", (cw, ch), (*_CARD_BG, 255))
        draw = ImageDraw.Draw(card)

        # Proportions: photo 50%, category bar 15%, player rows share 35%.
        photo_h = int(ch * 0.50)
        cat_bar_h = int(ch * 0.15)
        rows_total_h = ch - photo_h - cat_bar_h
        row_h = rows_total_h // max(n, 1)

        # --- Winner's headshot (top, fills card width) ---
        # Fill headshot area with teal background first.
        draw.rectangle([0, 0, cw, photo_h], fill=(*_HEADSHOT_BG, 255))

        photo_player = winner if winner else (player_vals[0][0] if player_vals else "")
        if is_tie and player_vals:
            photo_player = player_vals[0][0]
        hs = self._headshot(photo_player, cw, photo_h)
        if hs is not None:
            card.paste(hs, (0, 0), hs)
            draw = ImageDraw.Draw(card)

        # --- Category name bar (white bg, black text) ---
        cat_y = photo_h
        draw.rectangle([0, cat_y, cw, cat_y + cat_bar_h], fill=(*_CAT_BAR_BG, 255))
        cat_text = category.upper()
        cat_font, ctw, cth = self._fit_text(draw, cat_text, self.font_cat, cw - 12)
        draw.text(((cw - ctw) // 2, cat_y + (cat_bar_h - cth) // 2),
                  cat_text, fill=(*_CAT_BAR_TEXT, 255), font=cat_font)

        # --- Player rows ---
        rows_y = cat_y + cat_bar_h
        for pi, (player, val) in enumerate(player_vals):
            ry = rows_y + pi * row_h

            # Row background color.
            if is_tie:
                bg = self.tie_rgb
            elif player == winner:
                bg = self.winner_rgb
            elif player == runner_up:
                bg = self.loser_rgb
            else:
                bg = self.loser_rgb
            draw.rectangle([0, ry, cw, ry + row_h - 1], fill=(*bg, 255))

            # Text: "Player Name: Value"
            vt = f"{val:,.0f}" if val == int(val) else f"{val:,.1f}"
            row_text = f"{player}: {vt}"
            if player == winner and not is_tie:
                text_color = (255, 255, 255, 255)
            elif is_tie:
                text_color = (30, 30, 30, 255)
            else:
                text_color = (220, 220, 220, 255)

            font = self.font_row
            rtw, rth = _tsz(draw, row_text, font)
            if rtw > cw - 10:
                font = self.font_row_small
                rtw, rth = _tsz(draw, row_text, font)
            draw.text(((cw - rtw) // 2, ry + (row_h - rth) // 2),
                      row_text, fill=text_color, font=font)

        # Border.
        draw.rounded_rectangle([0, 0, cw - 1, ch - 1], radius=6,
                               outline=(*_CARD_BORDER, 255), width=2)

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

        self.font_card_cat = _load_font(f["bold"], max(12, int(24 * s)))
        self.font_card_row = _load_font(f["bold"], max(12, int(26 * s)))
        self.font_card_row_sm = _load_font(f["bold"], max(10, int(18 * s)))

        # Background (no title overlay — cards take full height).
        bg_path = cfg.resolve_path(cfg.bg_image)
        if os.path.isfile(bg_path):
            self._bg = _load_bg(bg_path, self.W, self.H)
        else:
            self._bg = Image.new("RGBA", (self.W, self.H), (10, 10, 20, 255))

        # Card dimensions.
        n_vis = max(2, min(6, cfg.cards_visible))
        self.card_gap = max(4, int(self.W * 0.005))
        self.card_w = (self.W - self.card_gap * (n_vis + 1)) // n_vis
        self.card_stride = self.card_w + self.card_gap
        self.card_h = int(self.H * 0.98)
        self.card_top = int(self.H * 0.01)
        self._scroll_speed = cfg.scroll_speed

        hs_dir = cfg.resolve_path(cfg.headshot_dir)

        self._builder = CardBuilder(
            self.card_w, self.card_h,
            self.font_card_cat, self.font_card_row, self.font_card_row_sm,
            hs_dir, f["bold"],
            winner_rgb=_hex(cfg.winner_color),
            loser_rgb=_hex(cfg.loser_color),
            tie_rgb=_hex(cfg.runner_up_color),
        )

        # Order categories.
        ordered = _interleave(data, cfg.lowest_is_better)

        # Precompute cards.
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
            self.card_metas.append({"cat": cat, "winner": w, "runner_up": ru, "tie": tie})
            self.card_images.append(self._builder.build(cat, pv, w, ru, tie))

    def timing(self) -> dict:
        fps = self.cfg.fps
        n = len(self.card_images)
        ppf = self.card_stride / (self._scroll_speed * fps)
        total_scroll = self.W + n * self.card_stride
        scroll_frames = int(total_scroll / ppf)
        intro = int(2.0 * fps)
        outro = int(3.0 * fps)
        return {
            "ppf": ppf, "intro": intro, "scroll": scroll_frames,
            "outro": outro, "total": intro + scroll_frames + outro,
        }

    def render_frame(self, fi: int, t: dict) -> Image.Image:
        img = self._bg.copy()
        if fi < t["intro"]:
            return img
        scroll_fi = fi - t["intro"]
        if scroll_fi > t["scroll"]:
            scroll_fi = t["scroll"]
        offset = scroll_fi * t["ppf"]
        for ci, cimg in enumerate(self.card_images):
            cx = int(self.W - offset + ci * self.card_stride)
            if cx + self.card_w < 0 or cx > self.W:
                continue
            img.paste(cimg, (cx, self.card_top), cimg)
        return img

    def render_frame_bytes(self, fi: int, t: dict) -> bytes:
        return self.render_frame(fi, t).convert("RGB").tobytes()

    def render_card_png(self, idx: int) -> Image.Image:
        pad = 10
        w = self.card_w + pad * 2
        h = self.card_h + pad * 2
        bg_path = self.cfg.resolve_path(self.cfg.bg_image)
        bg = _load_bg(bg_path, w, h) if os.path.isfile(bg_path) else Image.new("RGBA", (w, h), (10, 10, 20, 255))
        bg.paste(self.card_images[idx], (pad, pad), self.card_images[idx])
        return bg

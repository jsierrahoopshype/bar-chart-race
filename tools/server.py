"""Local dev server for the bar-chart-race customizer UI.

Run:  python tools/server.py
Open: http://localhost:8765
"""

from __future__ import annotations

import copy
import json
import os
import queue
import sys
import tempfile
import threading
import uuid
from pathlib import Path

# Add project root so we can import bar_race.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import parse_qs, urlparse
import io

from PIL import Image as PILImage

from bar_race.animate import BarState, FrameState
from bar_race.config import Config
from bar_race.render import FrameRenderer, _headshot_cache
from bar_race.themes import THEMES, get_theme, list_themes

from comparison.config import ComparisonConfig
from comparison.ingest import load as load_comparison
from comparison.render import ConveyorRenderer
from comparison.pipeline import _filter_data, run_single_preset

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TOOLS_DIR = Path(__file__).resolve().parent
ASSETS_DIR = PROJECT_ROOT / "assets"
OUTPUT_DIR = PROJECT_ROOT / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

# Progress tracking for SSE.
_progress: dict[str, queue.Queue] = {}


def _run_pipeline_multi(job_id: str, base_cfg: Config, input_path: str,
                        preset_outputs: list[tuple[str, str]],
                        temp_theme_slug: str | None = None) -> None:
    """Run the video pipeline for multiple presets, posting progress."""
    q = _progress[job_id]
    try:
        from bar_race.ingest import load
        from bar_race.normalize import normalize
        from bar_race.animate import build_keyframes, interpolate_frames
        from bar_race.render import FrameRenderer, _headshot_cache
        from bar_race.pipeline import _compute_progressive_max
        from bar_race.encode import encode
        from bar_race.animate import populate_leader_overlays
        from bar_race.pipeline import _hold_frames

        q.put({"event": "status", "data": "Loading data..."})
        df = load(path=input_path)

        q.put({"event": "status", "data": "Normalizing..."})
        ndf = normalize(df)

        q.put({"event": "status", "data": "Building keyframes..."})
        kfs = build_keyframes(ndf, base_cfg.top_n)

        body_frames = int(base_cfg.fps * base_cfg.duration_sec)
        n_steps = max(1, len(kfs) - 1)
        min_fpt = max(15, int(base_cfg.fps * 0.5))
        if n_steps <= 50 and body_frames // n_steps < min_fpt:
            body_frames = n_steps * min_fpt
        frames = interpolate_frames(kfs, total_frames=body_frames, top_n=base_cfg.top_n)
        _compute_progressive_max(frames, headroom=0.12)

        _reigns, _sound_events = populate_leader_overlays(
            frames, fps=base_cfg.fps,
            gap_threshold=base_cfg.gap_alert_threshold,
        )

        intro_count = int(base_cfg.fps * base_cfg.intro_hold_sec)
        outro_count = int(base_cfg.fps * base_cfg.outro_hold_sec)
        if intro_count and frames:
            frames = _hold_frames(frames[0], intro_count) + frames
        if outro_count and frames:
            frames = frames + _hold_frames(frames[-1], outro_count)

        total_frames = len(frames)
        n_presets = len(preset_outputs)
        output_names: list[str] = []

        for idx, (preset_name, output_path) in enumerate(preset_outputs):
            label = preset_name.capitalize()
            q.put({"event": "status",
                    "data": f"Generating {label} ({idx+1}/{n_presets})..."})

            cfg = copy.copy(base_cfg)
            cfg.preset = preset_name
            cfg.output = output_path

            _headshot_cache.clear()
            renderer = FrameRenderer(cfg)
            preset = cfg.get_preset()

            frame_count = 0

            def frame_gen(renderer=renderer):
                nonlocal frame_count
                for fs in frames:
                    yield renderer.render_rgb_bytes(fs)
                    frame_count += 1
                    if frame_count % 10 == 0:
                        # Scale progress: each preset gets an equal share.
                        base_pct = int(100 * idx / n_presets)
                        this_pct = int(100 * frame_count / max(total_frames, 1) / n_presets)
                        q.put({"event": "progress", "data": str(base_pct + this_pct)})

            encode(
                frames=frame_gen(),
                total_frames=total_frames,
                preset=preset,
                output=cfg.output,
                fps=cfg.fps,
                bitrate=cfg.bitrate,
            )
            output_names.append(os.path.basename(output_path))

        q.put({"event": "progress", "data": "100"})
        q.put({"event": "done", "data": json.dumps(output_names)})
    except Exception as e:
        import traceback
        traceback.print_exc()
        q.put({"event": "error", "data": str(e)})
    finally:
        if temp_theme_slug:
            THEMES.pop(temp_theme_slug, None)


def _parse_multipart(content_type: str, body: bytes) -> dict:
    """Parse multipart/form-data without the deprecated cgi module."""
    import re
    # Extract boundary from Content-Type header.
    m = re.search(r'boundary=([^\s;]+)', content_type)
    if not m:
        return {}
    boundary = m.group(1).encode()
    parts_raw = body.split(b'--' + boundary)
    result: dict = {}
    for part in parts_raw:
        part = part.strip()
        if not part or part == b'--':
            continue
        if b'\r\n\r\n' in part:
            header_block, data = part.split(b'\r\n\r\n', 1)
        elif b'\n\n' in part:
            header_block, data = part.split(b'\n\n', 1)
        else:
            continue
        # Strip trailing boundary marker.
        if data.endswith(b'\r\n'):
            data = data[:-2]
        headers_str = header_block.decode('utf-8', errors='replace')
        name_match = re.search(r'name="([^"]+)"', headers_str)
        if not name_match:
            continue
        name = name_match.group(1)
        filename_match = re.search(r'filename="([^"]*)"', headers_str)
        result[name] = {
            "data": data,
            "filename": filename_match.group(1) if filename_match else None,
        }
    return result


_SAMPLE_PLAYERS = [
    ("Shai Gilgeous-Alexander", "OKC", 1500),
    ("Luka Doncic", "DAL", 1400),
    ("Giannis Antetokounmpo", "MIL", 1300),
    ("Jayson Tatum", "BOS", 1200),
    ("Kevin Durant", "PHX", 1100),
    ("LeBron James", "LAL", 1050),
    ("Anthony Edwards", "MIN", 1000),
    ("Nikola Jokic", "DEN", 950),
    ("Devin Booker", "PHX", 900),
    ("Trae Young", "ATL", 850),
]


def _sample_frame(top_n: int = 10) -> FrameState:
    """Build a synthetic FrameState for preview rendering."""
    bars = []
    for i, (player, team, val) in enumerate(_SAMPLE_PLAYERS[:top_n]):
        bars.append(BarState(player=player, team=team, value=float(val), rank=float(i)))
    mx = max(b.value for b in bars) * 1.12
    return FrameState(bars=bars, date_label="Jan 15, 2024", progress=0.5, max_value=mx)


def _make_theme_with_overrides(slug: str, overrides: dict) -> str:
    """Copy the base theme, apply overrides, register as temp, return slug."""
    try:
        base = get_theme(slug)
    except ValueError:
        # Unknown theme (e.g. "custom-main" from browser localStorage).
        base = get_theme("midnight-premium")
    theme = copy.copy(base)
    for key, val in overrides.items():
        if hasattr(theme, key):
            setattr(theme, key, val)
    temp_slug = f"_tmp_{uuid.uuid4().hex[:8]}"
    theme.slug = temp_slug
    THEMES[temp_slug] = theme
    return temp_slug


def _apply_renames(data, player_renames: dict, category_renames: dict):
    """Apply player and category renames to ComparisonData in place."""
    if player_renames:
        data.players = [player_renames.get(p, p) for p in data.players]
        for cat in list(data.values):
            old_vals = data.values[cat]
            new_vals = {}
            for p, v in old_vals.items():
                new_vals[player_renames.get(p, p)] = v
            data.values[cat] = new_vals
    if category_renames:
        data.categories = [category_renames.get(c, c) for c in data.categories]
        new_values = {}
        for c, vals in data.values.items():
            new_values[category_renames.get(c, c)] = vals
        data.values = new_values
    return data


def _run_comparison_multi(job_id: str, cfg: ComparisonConfig, data, input_path: str) -> None:
    """Run comparison pipeline for all 3 presets in a background thread."""
    q = _progress[job_id]
    try:
        from comparison.render import ConveyorRenderer
        from comparison.encode import encode as comp_encode
        presets = [
            ("square", str(PROJECT_ROOT / f"output_comparison_square_{uuid.uuid4().hex[:6]}.mp4")),
            ("youtube", str(PROJECT_ROOT / f"output_comparison_youtube_{uuid.uuid4().hex[:6]}.mp4")),
            ("reels", str(PROJECT_ROOT / f"output_comparison_reels_{uuid.uuid4().hex[:6]}.mp4")),
        ]
        output_names = []
        n_presets = len(presets)
        for idx, (preset_name, output_path) in enumerate(presets):
            label = preset_name.capitalize()
            q.put({"event": "status", "data": f"Generating {label} ({idx+1}/{n_presets})..."})
            pcfg = copy.copy(cfg)
            pcfg.preset = preset_name
            pcfg.output = output_path
            renderer = ConveyorRenderer(pcfg, data)
            t = renderer.timing()
            total = t["total"]
            preset = pcfg.get_preset()
            frame_count = 0
            def gen(r=renderer, t=t, tot=total):
                nonlocal frame_count
                for fi in range(tot):
                    yield r.render_frame_bytes(fi, t)
                    frame_count += 1
                    if frame_count % 15 == 0:
                        base_pct = int(100 * idx / n_presets)
                        this_pct = int(100 * frame_count / max(tot, 1) / n_presets)
                        q.put({"event": "progress", "data": str(base_pct + this_pct)})
            comp_encode(frames=gen(), total_frames=total, preset=preset,
                        output=pcfg.output, fps=pcfg.fps)
            output_names.append(os.path.basename(output_path))
        q.put({"event": "progress", "data": "100"})
        q.put({"event": "done", "data": json.dumps(output_names)})
    except Exception as e:
        import traceback
        traceback.print_exc()
        q.put({"event": "error", "data": str(e)})


class Handler(SimpleHTTPRequestHandler):
    # No request timeout — allow renders to run as long as needed.
    timeout = None

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        # Serve customizer.html at root.
        if path == "/" or path == "/index.html":
            html_path = TOOLS_DIR / "customizer.html"
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(html_path.read_bytes())
            return

        # API: list themes.
        if path == "/api/themes":
            themes_list = []
            for slug in sorted(THEMES):
                t = THEMES[slug]
                themes_list.append({
                    "slug": t.slug,
                    "name": t.name,
                    "description": t.description,
                    "bg_type": t.bg_type,
                    "bg_colors": t.bg_colors,
                    "accent_color": t.accent_color,
                    "accent_secondary": t.accent_secondary,
                    "text_color": t.text_color,
                    "text_secondary_color": t.text_secondary_color,
                    "bar_radius": t.bar_radius,
                    "bar_gradient": t.bar_gradient,
                    "bar_border": t.bar_border,
                    "bar_team_stripe": t.bar_team_stripe,
                    "show_accent_line": t.show_accent_line,
                    "show_diagonal_slash": t.show_diagonal_slash,
                    "show_court_lines": t.show_court_lines,
                    "show_grid_lines": t.show_grid_lines,
                    "show_background_circle": t.show_background_circle,
                    "leader_glow": t.leader_glow,
                    "leader_outline": t.leader_outline,
                    "leader_underline": t.leader_underline,
                    "show_rank_numbers": t.show_rank_numbers,
                    "rank_giant_watermark": t.rank_giant_watermark,
                    "rank_number_style": t.rank_number_style,
                    "font_family": t.font_family,
                    "label_case": t.label_case,
                    "headshot_shape": t.headshot_shape,
                    "headshot_border": t.headshot_border,
                    "border_frame": t.border_frame,
                    "show_branding_tag": t.show_branding_tag,
                    "branding_text": t.branding_text,
                    "branding_color": t.branding_color,
                    "vignette": t.vignette,
                    "noise": t.noise,
                    "bar_shadow": t.bar_shadow,
                    "bar_opacity": t.bar_opacity,
                    "value_suffix": t.value_suffix,
                    "date_color": t.date_color,
                    "date_opacity": t.date_opacity,
                    "title_color": t.title_color,
                })
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(themes_list).encode())
            return

        # API: SSE progress stream.
        if path.startswith("/api/progress/"):
            job_id = path.split("/")[-1]
            if job_id not in _progress:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            q = _progress[job_id]
            while True:
                try:
                    msg = q.get(timeout=600)
                    line = f"event: {msg['event']}\ndata: {msg['data']}\n\n"
                    self.wfile.write(line.encode())
                    self.wfile.flush()
                    if msg["event"] in ("done", "error"):
                        break
                except queue.Empty:
                    # Send keepalive.
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
            return

        # API: download generated file.
        if path.startswith("/api/download/"):
            filename = path.split("/")[-1]
            filepath = PROJECT_ROOT / filename
            if filepath.is_file():
                self.send_response(200)
                self.send_header("Content-Type", "video/mp4")
                self.send_header("Content-Disposition",
                                 f'attachment; filename="{filename}"')
                self.send_header("Content-Length", str(filepath.stat().st_size))
                self.end_headers()
                with open(filepath, "rb") as f:
                    self.wfile.write(f.read())
                return
            self.send_error(404)
            return

        self.send_error(404)

    def do_POST(self):
        parsed = urlparse(self.path)

        if parsed.path == "/api/preview":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            config = json.loads(body)

            theme_slug = config.get("theme", "midnight-premium")
            overrides = config.get("overrides", {})
            temp_slug = None

            try:
                if overrides:
                    temp_slug = _make_theme_with_overrides(theme_slug, overrides)
                else:
                    temp_slug = None

                _headshot_cache.clear()

                cfg = Config(
                    output="",
                    preset=config.get("preset", "youtube"),
                    theme=temp_slug or theme_slug,
                    top_n=int(config.get("top_n", 10)),
                    title=config.get("title", ""),
                    subtitle=config.get("subtitle", ""),
                    watermark=config.get("watermark", ""),
                    headshot_dir=str(ASSETS_DIR / "headshots"),
                    logo_dir=str(ASSETS_DIR / "logos"),
                    time_unit=config.get("time_unit", "auto"),
                )

                renderer = FrameRenderer(cfg)
                frame = _sample_frame(cfg.top_n)
                img = renderer.render(frame)

                # Resize for preview.
                preset = cfg.get_preset()
                pw = min(preset.width, 960)
                ph = int(pw * preset.height / preset.width)
                img = img.convert("RGB").resize((pw, ph), PILImage.LANCZOS)

                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=85)
                data = buf.getvalue()

                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(data)
            except Exception as e:
                import traceback
                traceback.print_exc()
                self.send_error(500, str(e))
            finally:
                if temp_slug:
                    THEMES.pop(temp_slug, None)
            return

        if parsed.path == "/api/generate":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)

            # Parse multipart or JSON.
            content_type = self.headers.get("Content-Type", "")

            if "multipart/form-data" in content_type:
                # Parse multipart form data without deprecated cgi module.
                parts = _parse_multipart(content_type, body)
                config_json = parts.get("config", {}).get("data", b"{}").decode()
                config = json.loads(config_json)

                # Save uploaded file.
                file_part = parts.get("file", {})
                if file_part.get("data") and file_part.get("filename"):
                    ext = Path(file_part["filename"]).suffix
                    tmp = tempfile.NamedTemporaryFile(
                        delete=False, suffix=ext,
                        dir=str(PROJECT_ROOT),
                    )
                    tmp.write(file_part["data"])
                    tmp.close()
                    input_path = tmp.name
                else:
                    input_path = str(PROJECT_ROOT / "sample_data" /
                                     "nba_points_2024_long.xlsx")
            else:
                config = json.loads(body)
                input_path = config.get(
                    "input_path",
                    str(PROJECT_ROOT / "sample_data" /
                        "nba_points_2024_long.xlsx"),
                )

            # Build Config.
            output_name = config.get("output", f"output_{uuid.uuid4().hex[:8]}.mp4")
            output_path = str(PROJECT_ROOT / output_name)

            # Apply theme overrides if present.
            theme_slug = config.get("theme", "midnight-premium")
            theme_overrides = config.get("theme_overrides", {})
            temp_slug = None
            if theme_overrides:
                temp_slug = _make_theme_with_overrides(theme_slug, theme_overrides)
                theme_slug = temp_slug

            run_id = uuid.uuid4().hex[:8]
            preset_outputs: list[tuple[str, str]] = [
                ("square", str(PROJECT_ROOT / f"output_square_{run_id}.mp4")),
                ("youtube", str(PROJECT_ROOT / f"output_youtube_{run_id}.mp4")),
                ("reels", str(PROJECT_ROOT / f"output_reels_{run_id}.mp4")),
            ]

            base_cfg = Config(
                input_path=input_path,
                output="",
                preset="square",
                theme=theme_slug,
                fps=int(config.get("fps", 60)),
                duration_sec=float(config.get("duration", 30)),
                top_n=int(config.get("top_n", 10)),
                title=config.get("title", ""),
                subtitle=config.get("subtitle", ""),
                watermark=config.get("watermark", ""),
                headshot_dir=str(ASSETS_DIR / "headshots"),
                logo_dir=str(ASSETS_DIR / "logos"),
                time_unit=config.get("time_unit", "auto"),
            )

            job_id = uuid.uuid4().hex[:12]
            _progress[job_id] = queue.Queue()

            thread = threading.Thread(
                target=_run_pipeline_multi,
                args=(job_id, base_cfg, input_path, preset_outputs, temp_slug),
                daemon=True,
            )
            thread.start()

            output_names = [os.path.basename(p) for _, p in preset_outputs]
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({
                "job_id": job_id,
                "outputs": output_names,
            }).encode())
            return

        # ------------------------------------------------------------------
        # Comparison endpoints
        # ------------------------------------------------------------------

        if parsed.path == "/api/comparison/detect":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            content_type = self.headers.get("Content-Type", "")
            if "multipart/form-data" in content_type:
                parts = _parse_multipart(content_type, body)
                file_part = parts.get("file", {})
                if file_part.get("data") and file_part.get("filename"):
                    ext = Path(file_part["filename"]).suffix
                    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
                    tmp.write(file_part["data"])
                    tmp.close()
                    try:
                        data = load_comparison(tmp.name)
                        # Heuristic: comparison data has few rows (< 50) and 2+ player columns.
                        is_comp = len(data.categories) < 50 and len(data.players) >= 2
                        result = {
                            "type": "comparison" if is_comp else "bar_race",
                            "players": data.players,
                            "categories": data.categories,
                        }
                    except Exception:
                        result = {"type": "bar_race", "players": [], "categories": []}
                    finally:
                        os.unlink(tmp.name)
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    self.wfile.write(json.dumps(result).encode())
                    return

        if parsed.path == "/api/comparison/transpose":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            content_type = self.headers.get("Content-Type", "")
            result = {"players": [], "categories": []}
            if "multipart/form-data" in content_type:
                parts = _parse_multipart(content_type, body)
                file_part = parts.get("file", {})
                if file_part.get("data") and file_part.get("filename"):
                    ext = Path(file_part["filename"]).suffix
                    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
                    tmp.write(file_part["data"])
                    tmp.close()
                    try:
                        import pandas as pd
                        if ext.lower() in (".xlsx", ".xls"):
                            df = pd.read_excel(tmp.name)
                        else:
                            df = pd.read_csv(tmp.name)
                        # Transpose: swap rows and columns.
                        df.columns = [str(c).strip() for c in df.columns]
                        first_col = df.columns[0]
                        tdf = df.set_index(first_col).T.reset_index()
                        tdf.columns = [str(c).strip() for c in tdf.columns]
                        data = load_comparison(tmp.name)
                        # After transpose, old players become categories and vice versa.
                        result = {
                            "players": data.categories,
                            "categories": data.players,
                        }
                    except Exception as e:
                        import traceback
                        traceback.print_exc()
                    finally:
                        os.unlink(tmp.name)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(result).encode())
            return

        if parsed.path == "/api/comparison/preview":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            content_type = self.headers.get("Content-Type", "")
            try:
                if "multipart/form-data" in content_type:
                    parts = _parse_multipart(content_type, body)
                    config = json.loads(parts.get("config", {}).get("data", b"{}").decode())
                    file_part = parts.get("file", {})
                    if file_part.get("data") and file_part.get("filename"):
                        ext = Path(file_part["filename"]).suffix
                        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
                        tmp.write(file_part["data"])
                        tmp.close()
                        input_path = tmp.name
                    else:
                        input_path = str(PROJECT_ROOT / "sample_data" / "jordan_vs_lebron.csv")
                else:
                    config = json.loads(body)
                    input_path = str(PROJECT_ROOT / "sample_data" / "jordan_vs_lebron.csv")

                data = load_comparison(input_path)
                ccfg = ComparisonConfig(
                    input_path=input_path,
                    preset=config.get("preset", "square"),
                    title=config.get("title", ""),
                    subtitle=config.get("subtitle", ""),
                    fps=30,
                    winner_color=config.get("winner_color", "#CC0000"),
                    runner_up_color=config.get("runner_up_color", "#DAA520"),
                    loser_color=config.get("loser_color", "#2a2a2a"),
                    cards_visible=int(config.get("cards_visible", 4)),
                    scroll_speed=float(config.get("scroll_speed", 1.5)),
                    selected_players=config.get("selected_players", []),
                    selected_categories=config.get("selected_categories", []),
                    categories_order=config.get("categories_order", []),
                    lowest_is_better=config.get("lowest_is_better", []),
                    headshot_dir=str(ASSETS_DIR / "headshots"),
                    bg_image="assets/backgrounds/mesh3.jpg",
                    font_dir="assets/fonts",
                )
                _apply_renames(data,
                              config.get("player_renames", {}),
                              config.get("category_renames", {}))
                data = _filter_data(data, ccfg)
                renderer = ConveyorRenderer(ccfg, data)
                t = renderer.timing()

                # Render first 90 frames as preview image (frame at 1/3 scroll).
                preview_frame = min(t["intro"] + t["scroll"] // 3, t["total"] - 1)
                img = renderer.render_frame(preview_frame, t)
                preset = ccfg.get_preset()
                pw = min(preset.width, 960)
                ph = int(pw * preset.height / preset.width)
                img = img.convert("RGB").resize((pw, ph), PILImage.LANCZOS)
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=85)
                pic = buf.getvalue()

                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Content-Length", str(len(pic)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(pic)
            except Exception as e:
                import traceback
                traceback.print_exc()
                self.send_error(500, str(e))
            return

        if parsed.path == "/api/comparison/generate":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            content_type = self.headers.get("Content-Type", "")
            if "multipart/form-data" in content_type:
                parts = _parse_multipart(content_type, body)
                config = json.loads(parts.get("config", {}).get("data", b"{}").decode())
                file_part = parts.get("file", {})
                if file_part.get("data") and file_part.get("filename"):
                    ext = Path(file_part["filename"]).suffix
                    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
                    tmp.write(file_part["data"])
                    tmp.close()
                    input_path = tmp.name
                else:
                    input_path = str(PROJECT_ROOT / "sample_data" / "jordan_vs_lebron.csv")
            else:
                config = json.loads(body)
                input_path = str(PROJECT_ROOT / "sample_data" / "jordan_vs_lebron.csv")

            ccfg = ComparisonConfig(
                input_path=input_path,
                preset="square",
                title=config.get("title", ""),
                subtitle=config.get("subtitle", ""),
                fps=30,
                winner_color=config.get("winner_color", "#CC0000"),
                runner_up_color=config.get("runner_up_color", "#DAA520"),
                loser_color=config.get("loser_color", "#2a2a2a"),
                cards_visible=int(config.get("cards_visible", 4)),
                scroll_speed=float(config.get("scroll_speed", 1.5)),
                selected_players=config.get("selected_players", []),
                selected_categories=config.get("selected_categories", []),
                categories_order=config.get("categories_order", []),
                lowest_is_better=config.get("lowest_is_better", []),
                headshot_dir=str(ASSETS_DIR / "headshots"),
                bg_image="assets/backgrounds/mesh3.jpg",
                font_dir="assets/fonts",
            )
            data = load_comparison(input_path)
            _apply_renames(data,
                           config.get("player_renames", {}),
                           config.get("category_renames", {}))
            data = _filter_data(data, ccfg)

            job_id = uuid.uuid4().hex[:12]
            _progress[job_id] = queue.Queue()
            thread = threading.Thread(
                target=_run_comparison_multi,
                args=(job_id, ccfg, data, input_path),
                daemon=True,
            )
            thread.start()

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"job_id": job_id}).encode())
            return

        self.send_error(404)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def log_message(self, format, *args):
        # Quieter logs.
        if "/api/progress" not in str(args[0] if args else ""):
            super().log_message(format, *args)


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    server = HTTPServer(("0.0.0.0", port), Handler)
    server.timeout = None
    print(f"\n  Bar Chart Race Customizer")
    print(f"  http://localhost:{port}\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.shutdown()


if __name__ == "__main__":
    main()

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

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TOOLS_DIR = Path(__file__).resolve().parent
ASSETS_DIR = PROJECT_ROOT / "assets"
OUTPUT_DIR = PROJECT_ROOT / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

# Progress tracking for SSE.
_progress: dict[str, queue.Queue] = {}


def _run_pipeline(job_id: str, cfg: Config, input_path: str, temp_theme_slug: str | None = None) -> None:
    """Run the video pipeline in a background thread, posting progress."""
    q = _progress[job_id]
    try:
        from bar_race.ingest import load
        from bar_race.normalize import normalize
        from bar_race.animate import build_keyframes, interpolate_frames
        from bar_race.render import FrameRenderer
        from bar_race.pipeline import _compute_progressive_max
        from bar_race.encode import encode

        q.put({"event": "status", "data": "Loading data..."})
        df = load(path=input_path)

        q.put({"event": "status", "data": "Normalizing..."})
        ndf = normalize(df)

        q.put({"event": "status", "data": "Building keyframes..."})
        kfs = build_keyframes(ndf, cfg.top_n)

        body_frames = int(cfg.fps * cfg.duration_sec)
        n_steps = max(1, len(kfs) - 1)
        min_fpt = max(15, int(cfg.fps * 0.5))
        if n_steps <= 50 and body_frames // n_steps < min_fpt:
            body_frames = n_steps * min_fpt
        frames = interpolate_frames(kfs, total_frames=body_frames, top_n=cfg.top_n)
        _compute_progressive_max(frames, headroom=0.12)

        # Leader overlay tracking.
        from bar_race.animate import populate_leader_overlays
        _reigns, _sound_events = populate_leader_overlays(
            frames, fps=cfg.fps,
            gap_threshold=cfg.gap_alert_threshold,
        )

        # Intro / outro hold frames.
        from bar_race.pipeline import _hold_frames
        intro_count = int(cfg.fps * cfg.intro_hold_sec)
        outro_count = int(cfg.fps * cfg.outro_hold_sec)
        if intro_count and frames:
            frames = _hold_frames(frames[0], intro_count) + frames
        if outro_count and frames:
            frames = frames + _hold_frames(frames[-1], outro_count)

        total = len(frames)
        # Verify overlay data survives into outro hold frames.
        if outro_count and len(frames) > outro_count:
            last_outro = frames[-1]
            sys.stderr.write(
                f"  Outro hold: {outro_count} frames, "
                f"reign_history={len(last_outro.reign_history)} entries, "
                f"players_seen={last_outro.players_seen}\n"
            )
        q.put({"event": "status", "data": f"Rendering {total} frames..."})
        renderer = FrameRenderer(cfg)
        preset = cfg.get_preset()

        frame_count = 0

        def frame_gen():
            nonlocal frame_count
            for fs in frames:
                yield renderer.render_rgb_bytes(fs)
                frame_count += 1
                if frame_count % 10 == 0:
                    pct = int(100 * frame_count / max(total, 1))
                    q.put({"event": "progress", "data": str(pct)})

        q.put({"event": "status", "data": "Encoding video..."})
        encode(
            frames=frame_gen(),
            total_frames=total,
            preset=preset,
            output=cfg.output,
            fps=cfg.fps,
            bitrate=cfg.bitrate,
        )

        q.put({"event": "progress", "data": "100"})
        q.put({"event": "done", "data": cfg.output})
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

            cfg = Config(
                input_path=input_path,
                output=output_path,
                preset=config.get("preset", "youtube"),
                theme=theme_slug,
                fps=int(config.get("fps", 60)),
                duration_sec=float(config.get("duration", 30)),
                top_n=int(config.get("top_n", 10)),
                title=config.get("title", ""),
                subtitle=config.get("subtitle", ""),
                watermark=config.get("watermark", ""),
                headshot_dir=str(ASSETS_DIR / "headshots"),
                logo_dir=str(ASSETS_DIR / "logos"),
            )

            job_id = uuid.uuid4().hex[:12]
            _progress[job_id] = queue.Queue()

            thread = threading.Thread(
                target=_run_pipeline,
                args=(job_id, cfg, input_path, temp_slug),
                daemon=True,
            )
            thread.start()

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({
                "job_id": job_id,
                "output": output_name,
            }).encode())
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

"""Flask API for bar-chart-race video generation.

Endpoints:
  GET  /api/health   → {"status": "ok"}
  GET  /api/themes   → JSON list of all 50 themes
  POST /api/generate → accepts multipart form, returns MP4 bytes
"""

from __future__ import annotations

import json
import os
import tempfile
import uuid
from pathlib import Path

from flask import Flask, Response, jsonify, request
from flask_cors import CORS

# Ensure bar_race package is importable from this directory.
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))

from bar_race.config import Config
from bar_race.pipeline import run
from bar_race.themes import THEMES

app = Flask(__name__)
CORS(app)

SPACE_DIR = Path(__file__).resolve().parent
HEADSHOT_DIR = SPACE_DIR / "assets" / "headshots"


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


@app.route("/api/themes", methods=["GET"])
def themes():
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
    return jsonify(themes_list)


@app.route("/api/generate", methods=["POST"])
def generate():
    tmp_input = None
    tmp_output = None
    try:
        # Parse config from form field or JSON body.
        if request.content_type and "multipart/form-data" in request.content_type:
            config_str = request.form.get("config", "{}")
            config = json.loads(config_str)

            # Handle uploaded file.
            uploaded = request.files.get("file")
            gsheet_url = config.get("gsheet_url")

            if uploaded and uploaded.filename:
                ext = Path(uploaded.filename).suffix
                tmp = tempfile.NamedTemporaryFile(
                    delete=False, suffix=ext, prefix="bcr_input_"
                )
                uploaded.save(tmp)
                tmp.close()
                tmp_input = tmp.name
            elif not gsheet_url:
                return jsonify({"error": "No file or Google Sheets URL provided"}), 400
        else:
            config = request.get_json(force=True) or {}
            gsheet_url = config.get("gsheet_url")
            tmp_input = None
            if not gsheet_url:
                return jsonify({"error": "No file or Google Sheets URL provided"}), 400

        # Build output path.
        output_name = f"output_{uuid.uuid4().hex[:8]}.mp4"
        tmp_output = tempfile.NamedTemporaryFile(
            delete=False, suffix=".mp4", prefix="bcr_out_"
        ).name

        # Build Config.
        cfg = Config(
            input_path=tmp_input,
            gsheet_url=gsheet_url if not tmp_input else None,
            output=tmp_output,
            preset=config.get("preset", "reels"),
            theme=config.get("theme", "midnight-premium"),
            fps=int(config.get("fps", 30)),
            duration_sec=float(config.get("duration", 30)),
            top_n=int(config.get("top_n", 10)),
            title=config.get("title", ""),
            subtitle=config.get("subtitle", ""),
            watermark=config.get("watermark", ""),
            headshot_dir=str(HEADSHOT_DIR),
        )

        # Run pipeline (synchronous — HF Spaces have generous timeouts).
        run(cfg)

        # Read video into memory before cleanup.
        video_bytes = Path(tmp_output).read_bytes()

        return Response(
            video_bytes,
            mimetype="video/mp4",
            headers={
                "Content-Disposition": f'attachment; filename="{output_name}"',
                "Content-Length": str(len(video_bytes)),
            },
        )

    except Exception as e:
        return jsonify({"error": str(e)}), 500

    finally:
        # Clean up temp files.
        for path in (tmp_input, tmp_output):
            if path:
                try:
                    os.unlink(path)
                except OSError:
                    pass


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    app.run(host="0.0.0.0", port=port, debug=False)

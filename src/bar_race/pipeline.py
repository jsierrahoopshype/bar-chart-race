"""Orchestrate: ingest → normalize → animate → render → encode."""

from __future__ import annotations

import sys
from typing import Iterator

from bar_race.animate import FrameState, build_keyframes, interpolate_frames
from bar_race.config import Config
from bar_race.encode import encode
from bar_race.ingest import load
from bar_race.normalize import normalize
from bar_race.render import FrameRenderer


def _compute_progressive_max(frames: list[FrameState], headroom: float = 0.12) -> None:
    """Mutate *frames* in-place so that ``max_value`` is monotonically
    non-decreasing with *headroom* (e.g. 12 %) above the raw maximum.

    This prevents the axis from shrinking when leaders change.
    """
    running_max = 0.0
    for f in frames:
        raw = f.max_value
        target = raw * (1.0 + headroom)
        if target > running_max:
            running_max = target
        f.max_value = running_max


def _hold_frames(frame: FrameState, count: int) -> list[FrameState]:
    """Duplicate a single frame *count* times for intro/outro holds."""
    return [
        FrameState(
            bars=list(frame.bars),
            date_label=frame.date_label,
            progress=frame.progress,
            max_value=frame.max_value,
        )
        for _ in range(count)
    ]


def run(cfg: Config) -> None:
    """Execute the full pipeline and write the output video."""

    # 1. Ingest
    sys.stderr.write("Loading data...\n")
    df = load(
        path=cfg.input_path,
        gsheet_url=cfg.gsheet_url,
        sheet_name=cfg.sheet_name,
    )

    # 2. Normalize
    sys.stderr.write("Normalizing data...\n")
    df = normalize(
        df,
        stat_column=cfg.stat_column,
        date_start=cfg.date_start,
        date_end=cfg.date_end,
    )

    # 3. Animate (build keyframes + interpolate)
    sys.stderr.write("Building animation frames...\n")
    keyframes = build_keyframes(df, top_n=cfg.top_n)

    body_frames = int(cfg.fps * cfg.duration_sec)
    frames = interpolate_frames(keyframes, total_frames=body_frames, top_n=cfg.top_n)

    # Progressive max scaling.
    _compute_progressive_max(frames, headroom=0.12)

    # Intro / outro hold frames.
    intro_count = int(cfg.fps * cfg.intro_hold_sec)
    outro_count = int(cfg.fps * cfg.outro_hold_sec)

    all_frames: list[FrameState] = []
    if intro_count and frames:
        all_frames.extend(_hold_frames(frames[0], intro_count))
    all_frames.extend(frames)
    if outro_count and frames:
        all_frames.extend(_hold_frames(frames[-1], outro_count))

    total = len(all_frames)
    sys.stderr.write(f"Total frames to render: {total}\n")

    # 4. Render + 5. Encode (stream frames to ffmpeg)
    renderer = FrameRenderer(cfg)
    preset = cfg.get_preset()

    def frame_gen() -> Iterator[bytes]:
        for fs in all_frames:
            yield renderer.render_rgb_bytes(fs)

    sys.stderr.write(f"Encoding to {cfg.output} ...\n")
    encode(
        frames=frame_gen(),
        total_frames=total,
        preset=preset,
        output=cfg.output,
        fps=cfg.fps,
        bitrate=cfg.bitrate,
    )

    sys.stderr.write(f"Done — saved to {cfg.output}\n")

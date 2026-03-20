"""Pipe raw RGB frames to ffmpeg as H.264 MP4."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Iterator

from bar_race.config import VideoPreset


def encode(
    frames: Iterator[bytes],
    total_frames: int,
    preset: VideoPreset,
    output: str | Path,
    fps: int = 60,
    bitrate: str = "12M",
    crf: int = 18,
) -> None:
    """Stream raw RGB frames into ffmpeg and produce an MP4.

    Parameters
    ----------
    frames:
        Iterator yielding raw RGB bytes, each of size
        ``preset.width * preset.height * 3``.
    total_frames:
        Expected number of frames (used only for progress display).
    preset:
        Video resolution preset.
    output:
        Destination file path.
    fps:
        Frames per second.
    bitrate:
        Target bitrate string (e.g. ``"12M"``).
    crf:
        Constant Rate Factor (lower → higher quality).
    """
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "ffmpeg",
        "-y",
        "-f", "rawvideo",
        "-vcodec", "rawvideo",
        "-pix_fmt", "rgb24",
        "-s", f"{preset.width}x{preset.height}",
        "-r", str(fps),
        "-i", "-",
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-crf", str(crf),
        "-b:v", bitrate,
        "-movflags", "+faststart",
        "-an",
        str(output),
    ]

    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    try:
        for idx, frame_bytes in enumerate(frames, 1):
            assert proc.stdin is not None
            proc.stdin.write(frame_bytes)

            if total_frames > 0:
                pct = idx / total_frames * 100
                sys.stderr.write(f"\rEncoding: {pct:5.1f}%  ({idx}/{total_frames})")
                sys.stderr.flush()
    finally:
        if proc.stdin:
            proc.stdin.close()

    proc.wait()
    sys.stderr.write("\n")

    if proc.returncode != 0:
        raise RuntimeError(
            f"ffmpeg exited with code {proc.returncode}. "
            "Make sure ffmpeg is installed and on your PATH."
        )

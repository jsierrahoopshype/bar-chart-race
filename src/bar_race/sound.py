"""Generate sound effects for bar chart race videos.

Produces a WAV file with programmatically generated sounds synced to
animation events (whoosh, ding, boom) plus subtle ambient background.
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from bar_race.animate import SoundEvent


def _envelope(length: int, attack: int, decay: int) -> np.ndarray:
    """Create an ADSR-like envelope (attack-sustain-decay)."""
    env = np.ones(length, dtype=np.float32)
    if attack > 0:
        env[:attack] = np.linspace(0, 1, attack)
    if decay > 0:
        env[-decay:] = np.linspace(1, 0, decay)
    return env


def _whoosh(sr: int, duration: float = 0.25, intensity: float = 1.0) -> np.ndarray:
    """Short burst of filtered noise with fast attack."""
    n = int(sr * duration)
    noise = np.random.randn(n).astype(np.float32)
    # Low-pass via simple moving average.
    kernel = np.ones(8) / 8
    noise = np.convolve(noise, kernel, mode="same")
    env = _envelope(n, int(sr * 0.02), int(sr * 0.15))
    return noise * env * 0.3 * intensity


def _ding(sr: int, duration: float = 0.3, freq: float = 800.0) -> np.ndarray:
    """Short sine tone with fast decay."""
    n = int(sr * duration)
    t = np.arange(n, dtype=np.float32) / sr
    tone = np.sin(2 * np.pi * freq * t)
    env = _envelope(n, int(sr * 0.005), int(sr * 0.2))
    return tone * env * 0.2


def _boom(sr: int, duration: float = 0.5, freq: float = 150.0) -> np.ndarray:
    """Low sine tone with medium decay."""
    n = int(sr * duration)
    t = np.arange(n, dtype=np.float32) / sr
    tone = np.sin(2 * np.pi * freq * t)
    env = _envelope(n, int(sr * 0.01), int(sr * 0.35))
    return tone * env * 0.25


def generate_audio(
    sound_events: list[SoundEvent],
    total_frames: int,
    fps: int,
    output_wav: str,
    sr: int = 44100,
) -> None:
    """Write a WAV file with sound effects at the right timestamps."""
    duration = total_frames / max(fps, 1)
    total_samples = int(sr * duration)
    audio = np.zeros(total_samples, dtype=np.float32)

    # Subtle ambient pink noise at -30 dB.
    ambient = np.random.randn(total_samples).astype(np.float32)
    # Simple pink noise approximation via cumulative sum + normalization.
    ambient = np.cumsum(ambient)
    ambient -= np.linspace(ambient[0], ambient[-1], total_samples)
    ambient /= max(np.abs(ambient).max(), 1e-6)
    audio += ambient * 0.015  # very quiet

    # Place sound events.
    for ev in sound_events:
        sample_pos = int(ev.frame / max(fps, 1) * sr)
        if sample_pos >= total_samples:
            continue

        if ev.kind == "whoosh":
            sfx = _whoosh(sr, intensity=ev.intensity)
        elif ev.kind == "ding":
            sfx = _ding(sr)
        elif ev.kind == "boom":
            sfx = _boom(sr)
        else:
            continue

        end = min(sample_pos + len(sfx), total_samples)
        n = end - sample_pos
        audio[sample_pos:end] += sfx[:n]

    # Clip and convert to 16-bit PCM.
    audio = np.clip(audio, -1.0, 1.0)
    pcm = (audio * 32767).astype(np.int16)

    # Write WAV manually (avoid scipy dependency).
    import struct
    with open(output_wav, "wb") as f:
        n_samples = len(pcm)
        data_size = n_samples * 2  # 16-bit mono
        f.write(b"RIFF")
        f.write(struct.pack("<I", 36 + data_size))
        f.write(b"WAVE")
        f.write(b"fmt ")
        f.write(struct.pack("<IHHIIHH", 16, 1, 1, sr, sr * 2, 2, 16))
        f.write(b"data")
        f.write(struct.pack("<I", data_size))
        f.write(pcm.tobytes())


def merge_audio_video(video_path: str, wav_path: str, output_path: str) -> bool:
    """Merge WAV audio with MP4 video using ffmpeg. Returns True on success."""
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-i", wav_path,
        "-c:v", "copy",
        "-c:a", "aac",
        "-shortest",
        output_path,
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, timeout=120,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False

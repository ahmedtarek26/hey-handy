"""Subtle synthesized audio chimes for wake/confirm/sleep feedback."""

from __future__ import annotations

import threading
from typing import Sequence, Tuple

import numpy as np


def _tone_wave(
    notes: Sequence[Tuple[float, float]],
    sample_rate: int = 22050,
    gain: float = 0.10,
) -> np.ndarray:
    """Synthesize a soft sequence of (freq_hz, duration_s) tones with smooth fade."""
    segments = []
    for freq, dur in notes:
        n = max(1, int(sample_rate * dur))
        t = np.linspace(0.0, dur, n, endpoint=False, dtype=np.float32)
        wave = np.sin(2.0 * np.pi * freq * t)
        fade = max(1, min(n // 4, int(sample_rate * 0.015)))
        env = np.ones(n, dtype=np.float32)
        env[:fade] = np.linspace(0.0, 1.0, fade, dtype=np.float32)
        env[-fade:] = np.linspace(1.0, 0.0, fade, dtype=np.float32)
        segments.append(wave * env * gain)
    return np.concatenate(segments) if segments else np.zeros(0, dtype=np.float32)


def play_chime(kind: str, enabled: bool = True) -> None:
    """Play a brief non-blocking feedback chime ('wake', 'confirm', or 'sleep')."""
    if not enabled:
        return
    presets = {
        "wake": [(587.33, 0.065), (880.00, 0.095)],
        "confirm": [(783.99, 0.055), (1046.50, 0.075)],
        "sleep": [(523.25, 0.070), (392.00, 0.085)],
    }
    notes = presets.get(kind)
    if not notes:
        return

    def _run() -> None:
        try:
            import sounddevice as sd

            wave = _tone_wave(notes)
            sd.play(wave, samplerate=22050, blocking=False)
        except Exception:
            pass

    threading.Thread(target=_run, daemon=True).start()

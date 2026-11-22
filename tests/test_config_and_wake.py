"""Tests for configuration persistence, audio resampling, and wake-word tokenization."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from hey_handy.config import DEFAULT_GESTURE_MAP, HeyHandyConfig
from hey_handy.wake_word import normalize_speech_chunk, resample_mono, sensitivity_to_kws_params


def test_config_roundtrip_and_sanitization(tmp_path: Path) -> None:
    cfg_path = tmp_path / "config.json"
    cfg = HeyHandyConfig(
        wake_phrase="  hey handy  ",
        wake_sensitivity=2.5,
        wake_window_s=0.1,
        volume_step=99,
        volume_mode="invalid",
        gesture_map={"Open_Palm": "pause", "Unknown": "bogus"},
    )
    cfg.save(cfg_path)
    loaded = HeyHandyConfig.load(cfg_path)

    assert loaded.wake_phrase == "HEY HANDY"
    assert loaded.wake_sensitivity == 1.0
    assert loaded.wake_window_s == 2.0
    assert loaded.volume_step == 25
    assert loaded.volume_mode == "system"
    assert loaded.gesture_map["Open_Palm"] == "pause"
    assert loaded.gesture_map["Victory"] == DEFAULT_GESTURE_MAP["Victory"]
    assert "Unknown" not in loaded.gesture_map


def test_corrupt_config_falls_back_to_defaults(tmp_path: Path) -> None:
    cfg_path = tmp_path / "broken.json"
    cfg_path.write_text("{not valid json", encoding="utf-8")
    loaded = HeyHandyConfig.load(cfg_path)
    assert loaded.wake_phrase == "HEY HANDY"
    assert loaded.ws_port == 17421


def test_resample_mono_preserves_duration_and_handles_edge_cases() -> None:
    assert resample_mono(np.array([], dtype=np.float32), 48000, 16000).size == 0

    t = np.linspace(0.0, 0.1, 4800, endpoint=False, dtype=np.float32)
    sine_48k = np.sin(2.0 * np.pi * 440.0 * t).astype(np.float32)
    out = resample_mono(sine_48k, 48000, 16000)
    assert out.shape == (1600,)
    assert out.dtype == np.float32
    # Zero-crossings / amplitude preserved closely
    assert np.max(np.abs(out)) > 0.95


def test_sensitivity_mapping_monotonic() -> None:
    b_low, th_low = sensitivity_to_kws_params(0.1)
    b_high, th_high = sensitivity_to_kws_params(0.9)
    assert b_high > b_low
    assert th_high < th_low


def test_agc_boosts_quiet_speech_and_leaves_silence_alone() -> None:
    silence = np.full(1280, 0.0005, dtype=np.float32)
    out_sil, ema = normalize_speech_chunk(silence, 0.0)
    assert float(np.max(np.abs(out_sil))) < 0.001

    quiet_speech = np.sin(np.linspace(0.0, 20.0, 1280, dtype=np.float32)) * 0.03
    out_sp, ema2 = normalize_speech_chunk(quiet_speech, ema)
    assert float(np.max(np.abs(out_sp))) > 0.20
    assert ema2 >= 0.029


def test_v1_config_migrates_strict_thresholds(tmp_path: Path) -> None:
    cfg_path = tmp_path / "old.json"
    cfg_path.write_text(
        '{"min_confidence": 0.58, "stability_frames": 4, "min_hand_span": 0.08}',
        encoding="utf-8",
    )
    loaded = HeyHandyConfig.load(cfg_path)
    assert loaded.min_confidence == 0.42
    assert loaded.stability_frames == 3
    assert loaded.min_hand_span == 0.06

"""Optional local integration tests run when offline models are downloaded."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from hey_handy.models import resolve_model_paths
from hey_handy.wake_word import build_keywords_file

MODELS = resolve_model_paths()


@pytest.mark.skipif(not MODELS.all_ready, reason="Offline models not downloaded yet")
def test_real_kws_and_mediapipe_models_load_and_run(tmp_path: Path) -> None:
    import mediapipe as mp
    import sherpa_onnx
    from mediapipe.tasks import python as mp_python
    from mediapipe.tasks.python import vision

    kw_path = build_keywords_file(
        bpe_model_path=MODELS.bpe_model,
        tokens_path=MODELS.tokens,
        phrases=["HEY HANDY", "HEY HAND E"],
        sensitivity=0.55,
        out_path=tmp_path / "keywords.txt",
    )
    text = kw_path.read_text(encoding="utf-8")
    assert "@HEY_HANDY" in text

    kws = sherpa_onnx.KeywordSpotter(
        tokens=str(MODELS.tokens),
        encoder=str(MODELS.encoder),
        decoder=str(MODELS.decoder),
        joiner=str(MODELS.joiner),
        num_threads=1,
        keywords_file=str(kw_path),
        provider="cpu",
    )
    stream = kws.create_stream()
    stream.accept_waveform(16000, np.zeros(8000, dtype=np.float32))
    while kws.is_ready(stream):
        kws.decode_stream(stream)
    assert kws.get_result(stream) == ""

    opts = vision.GestureRecognizerOptions(
        base_options=mp_python.BaseOptions(model_asset_path=str(MODELS.gesture_task)),
        running_mode=vision.RunningMode.IMAGE,
        num_hands=1,
    )
    rec = vision.GestureRecognizer.create_from_options(opts)
    try:
        res = rec.recognize(
            mp.Image(image_format=mp.ImageFormat.SRGB, data=np.zeros((240, 320, 3), dtype=np.uint8))
        )
        assert res.gestures == []
    finally:
        rec.close()

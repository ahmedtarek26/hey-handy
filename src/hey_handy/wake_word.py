"""Offline streaming wake-word listener ('Hey Handy') using sherpa-onnx."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Callable, Iterable, List, Optional, Tuple

import numpy as np

from .models import ModelPaths

TARGET_SAMPLE_RATE = 16000


def resample_mono(samples: np.ndarray, src_rate: int, dst_rate: int = TARGET_SAMPLE_RATE) -> np.ndarray:
    """Resample a 1-D float32 audio chunk from src_rate to dst_rate."""
    arr = np.asarray(samples, dtype=np.float32).reshape(-1)
    if arr.size == 0 or src_rate == dst_rate or src_rate <= 0:
        return arr
    dst_len = max(1, int(round(arr.size * (dst_rate / float(src_rate)))))
    src_x = np.linspace(0.0, 1.0, arr.size, endpoint=False)
    dst_x = np.linspace(0.0, 1.0, dst_len, endpoint=False)
    return np.interp(dst_x, src_x, arr).astype(np.float32)


def _load_token_vocab(tokens_path: Path) -> set[str]:
    vocab: set[str] = set()
    for line in tokens_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        token = line.split()[0]
        vocab.add(token)
    return vocab


def sensitivity_to_kws_params(sensitivity: float) -> Tuple[float, float]:
    """Map user sensitivity (0.1..1.0) to (boosting_score, trigger_threshold)."""
    s = max(0.1, min(1.0, float(sensitivity)))
    boost = round(1.0 + s * 1.4, 2)
    threshold = round(0.55 - s * 0.35, 2)
    return boost, max(0.12, threshold)


def build_keywords_file(
    bpe_model_path: Path,
    tokens_path: Path,
    phrases: Iterable[str],
    sensitivity: float,
    out_path: Path,
    tag: str = "HEY_HANDY",
) -> Path:
    """Encode wake-word phrases into sherpa-onnx keywords.txt format using SentencePiece BPE."""
    import sentencepiece as spm

    sp = spm.SentencePieceProcessor()
    sp.load(str(bpe_model_path))
    vocab = _load_token_vocab(tokens_path)
    boost, threshold = sensitivity_to_kws_params(sensitivity)

    lines: List[str] = []
    seen: set[str] = set()
    for raw_phrase in phrases:
        clean = " ".join(raw_phrase.strip().upper().split())
        if not clean or clean in seen:
            continue
        seen.add(clean)
        pieces = sp.encode(clean, out_type=str)
        # Filter/verify against tokens.txt (GigaSpeech BPE uses U+2581 '▁' word markers)
        valid_pieces = [p for p in pieces if p in vocab]
        if not valid_pieces:
            # Fallback without leading marker if model uses plain characters
            valid_pieces = [p.lstrip("▁") for p in pieces if p.lstrip("▁") in vocab]
        if not valid_pieces:
            raise ValueError(f"Could not tokenize wake phrase '{clean}' against {tokens_path}")
        lines.append(f"{' '.join(valid_pieces)} :{boost} #{threshold} @{tag}")

    if not lines:
        raise ValueError("No valid wake-word phrases provided")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out_path


class WakeWordListener:
    """Continuously listens on the microphone in a background thread for 'Hey Handy'."""

    def __init__(
        self,
        model_paths: ModelPaths,
        phrase: str = "HEY HANDY",
        sensitivity: float = 0.55,
        mic_device: Optional[int] = None,
        debounce_s: float = 1.6,
        on_wake: Optional[Callable[[str], None]] = None,
        on_error: Optional[Callable[[str], None]] = None,
    ) -> None:
        self.model_paths = model_paths
        self.phrase = phrase
        self.sensitivity = sensitivity
        self.mic_device = mic_device
        self.debounce_s = debounce_s
        self.on_wake = on_wake
        self.on_error = on_error

        self._stop_event = threading.Event()
        self._paused = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._last_trigger = 0.0

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def is_paused(self) -> bool:
        return self._paused

    def set_paused(self, paused: bool) -> None:
        self._paused = bool(paused)

    def update_config(
        self,
        phrase: str,
        sensitivity: float,
        mic_device: Optional[int],
    ) -> None:
        changed = (
            phrase.strip().upper() != self.phrase.strip().upper()
            or abs(sensitivity - self.sensitivity) > 1e-4
            or mic_device != self.mic_device
        )
        self.phrase = phrase
        self.sensitivity = sensitivity
        self.mic_device = mic_device
        if changed and self.is_running:
            self.stop()
            self.start()

    def start(self) -> None:
        with self._lock:
            if self.is_running:
                return
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._run_loop, name="hey-handy-kws", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        with self._lock:
            t = self._thread
            self._thread = None
        if t and t.is_alive():
            t.join(timeout=2.0)

    def _build_phrases(self) -> List[str]:
        base = " ".join(self.phrase.strip().upper().split()) or "HEY HANDY"
        phrases = [base]
        # Include helpful close phonetic/ASR spelling if using default phrase
        if base == "HEY HANDY":
            phrases.append("HEY HAND E")
        return phrases

    def _run_loop(self) -> None:
        try:
            import sherpa_onnx
            import sounddevice as sd
        except Exception as exc:
            if self.on_error:
                self.on_error(f"Audio wake-word dependencies unavailable: {exc}")
            return

        if not self.model_paths.kws_ready:
            if self.on_error:
                self.on_error("Wake-word model files are missing.")
            return

        keywords_file = self.model_paths.base_dir / "hey_handy_keywords.txt"
        try:
            build_keywords_file(
                bpe_model_path=self.model_paths.bpe_model,
                tokens_path=self.model_paths.tokens,
                phrases=self._build_phrases(),
                sensitivity=self.sensitivity,
                out_path=keywords_file,
            )
            kws = sherpa_onnx.KeywordSpotter(
                tokens=str(self.model_paths.tokens),
                encoder=str(self.model_paths.encoder),
                decoder=str(self.model_paths.decoder),
                joiner=str(self.model_paths.joiner),
                num_threads=2,
                keywords_file=str(keywords_file),
                provider="cpu",
            )
        except Exception as exc:
            if self.on_error:
                self.on_error(f"Failed to initialize wake-word engine: {exc}")
            return

        stream = kws.create_stream()

        # Open microphone at 16 kHz if supported, otherwise fall back to device default rate.
        capture_rate = TARGET_SAMPLE_RATE
        try:
            sd.check_input_settings(device=self.mic_device, samplerate=TARGET_SAMPLE_RATE, channels=1)
        except Exception:
            try:
                info = sd.query_devices(self.mic_device, "input")
                capture_rate = int(info.get("default_samplerate") or 48000)
            except Exception:
                capture_rate = 48000

        blocksize = max(512, int(capture_rate * 0.08))

        def callback(indata: np.ndarray, frames: int, time_info: object, status: object) -> None:
            if self._stop_event.is_set() or self._paused:
                return
            mono = indata[:, 0] if indata.ndim > 1 else indata
            chunk = resample_mono(mono, capture_rate, TARGET_SAMPLE_RATE)
            stream.accept_waveform(TARGET_SAMPLE_RATE, chunk)
            while kws.is_ready(stream):
                kws.decode_stream(stream)
                result = kws.get_result(stream)
                if result:
                    now = time.monotonic()
                    if now - self._last_trigger >= self.debounce_s:
                        self._last_trigger = now
                        kws.reset_stream(stream)
                        if self.on_wake:
                            self.on_wake(str(result))

        try:
            with sd.InputStream(
                device=self.mic_device,
                samplerate=capture_rate,
                channels=1,
                dtype="float32",
                blocksize=blocksize,
                callback=callback,
            ):
                while not self._stop_event.wait(0.15):
                    pass
        except Exception as exc:
            if self.on_error and not self._stop_event.is_set():
                self.on_error(f"Microphone stream error: {exc}")

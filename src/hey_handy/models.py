"""Pre-trained model discovery and download helpers for MediaPipe & sherpa-onnx."""

from __future__ import annotations

import shutil
import tarfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from .config import get_data_dir

GESTURE_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/"
    "gesture_recognizer/gesture_recognizer/float16/1/gesture_recognizer.task"
)
KWS_MODEL_DIRNAME = "sherpa-onnx-kws-zipformer-gigaspeech-3.3M-2024-01-01"
KWS_MODEL_URL = (
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/kws-models/"
    f"{KWS_MODEL_DIRNAME}.tar.bz2"
)


@dataclass(frozen=True)
class ModelPaths:
    """Resolved local paths to required MediaPipe and KWS model assets."""

    base_dir: Path
    gesture_task: Path
    kws_dir: Path
    encoder: Path
    decoder: Path
    joiner: Path
    tokens: Path
    bpe_model: Path

    @property
    def gesture_ready(self) -> bool:
        return self.gesture_task.is_file() and self.gesture_task.stat().st_size > 0

    @property
    def kws_ready(self) -> bool:
        return all(
            p.is_file() and p.stat().st_size > 0
            for p in (self.encoder, self.decoder, self.joiner, self.tokens, self.bpe_model)
        )

    @property
    def all_ready(self) -> bool:
        return self.gesture_ready and self.kws_ready


def resolve_model_paths(models_dir: Optional[Path] = None) -> ModelPaths:
    """Locate model paths inside the provided directory, local repo, or user data dir."""
    if models_dir is None:
        repo_models = Path(__file__).resolve().parents[2] / "models"
        if (repo_models / "gesture_recognizer.task").exists() or (repo_models / KWS_MODEL_DIRNAME).exists():
            models_dir = repo_models
        else:
            models_dir = get_data_dir() / "models"

    kws_dir = models_dir / KWS_MODEL_DIRNAME

    def _find_onnx(prefix: str, fallback: str) -> Path:
        if kws_dir.is_dir():
            matches = sorted(kws_dir.glob(f"{prefix}*.int8.onnx")) or sorted(kws_dir.glob(f"{prefix}*.onnx"))
            if matches:
                return matches[0]
        return kws_dir / fallback

    return ModelPaths(
        base_dir=models_dir,
        gesture_task=models_dir / "gesture_recognizer.task",
        kws_dir=kws_dir,
        encoder=_find_onnx("encoder", "encoder-epoch-12-avg-2-chunk-16-left-64.int8.onnx"),
        decoder=_find_onnx("decoder", "decoder-epoch-12-avg-2-chunk-16-left-64.int8.onnx"),
        joiner=_find_onnx("joiner", "joiner-epoch-12-avg-2-chunk-16-left-64.int8.onnx"),
        tokens=kws_dir / "tokens.txt",
        bpe_model=kws_dir / "bpe.model",
    )


def _download_file(
    url: str,
    dest: Path,
    progress_cb: Optional[Callable[[str, float], None]] = None,
    label: str = "Downloading",
) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": "hey-handy/0.1.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        total = int(resp.headers.get("Content-Length") or 0)
        downloaded = 0
        with open(tmp, "wb") as fh:
            while True:
                chunk = resp.read(65536)
                if not chunk:
                    break
                fh.write(chunk)
                downloaded += len(chunk)
                if progress_cb:
                    frac = (downloaded / total) if total > 0 else 0.0
                    progress_cb(label, min(1.0, frac))
    tmp.replace(dest)


def ensure_models(
    models_dir: Optional[Path] = None,
    progress_cb: Optional[Callable[[str, float], None]] = None,
) -> ModelPaths:
    """Download and extract MediaPipe & sherpa-onnx KWS models if missing."""
    paths = resolve_model_paths(models_dir)
    paths.base_dir.mkdir(parents=True, exist_ok=True)

    if not paths.gesture_ready:
        _download_file(
            GESTURE_MODEL_URL,
            paths.gesture_task,
            progress_cb=progress_cb,
            label="Downloading hand gesture model (~8 MB)...",
        )

    if not paths.kws_ready:
        archive = paths.base_dir / f"{KWS_MODEL_DIRNAME}.tar.bz2"
        _download_file(
            KWS_MODEL_URL,
            archive,
            progress_cb=progress_cb,
            label="Downloading Hey Handy voice wake model (~15 MB)...",
        )
        if progress_cb:
            progress_cb("Extracting wake-word model...", 1.0)
        if paths.kws_dir.exists():
            shutil.rmtree(paths.kws_dir, ignore_errors=True)
        with tarfile.open(archive, "r:bz2") as tar:
            tar.extractall(path=paths.base_dir, filter="data")
        archive.unlink(missing_ok=True)

    return resolve_model_paths(paths.base_dir)

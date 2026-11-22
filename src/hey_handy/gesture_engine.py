"""MediaPipe hand gesture recognizer, eating-safety guards, and wake-window state machine."""

from __future__ import annotations

import math
import threading
import time
from collections import Counter, deque
from dataclasses import dataclass
from typing import Callable, Deque, Dict, List, Optional, Sequence, Tuple

import numpy as np

from .config import HeyHandyConfig
from .models import ModelPaths

CONTINUOUS_ACTIONS = frozenset({"volume_up", "volume_down"})

# MediaPipe 21-landmark indices
WRIST = 0
THUMB_CMC, THUMB_MCP, THUMB_IP, THUMB_TIP = 1, 2, 3, 4
INDEX_MCP, INDEX_PIP, INDEX_DIP, INDEX_TIP = 5, 6, 7, 8
MIDDLE_MCP, MIDDLE_PIP, MIDDLE_DIP, MIDDLE_TIP = 9, 10, 11, 12
RING_MCP, RING_PIP, RING_DIP, RING_TIP = 13, 14, 15, 16
PINKY_MCP, PINKY_PIP, PINKY_DIP, PINKY_TIP = 17, 18, 19, 20


@dataclass(frozen=True)
class LandmarkPoint:
    """Lightweight normalized 3D hand landmark."""

    x: float
    y: float
    z: float = 0.0


@dataclass(frozen=True)
class GestureEvent:
    """Emitted when a gesture clears consensus, geometry guards, and cooldowns."""

    gesture: str
    action: str
    confidence: float
    continuous: bool


def _dist2d(a: LandmarkPoint, b: LandmarkPoint) -> float:
    return math.hypot(a.x - b.x, a.y - b.y)


def hand_span(landmarks: Sequence[LandmarkPoint]) -> float:
    """Return normalized bounding-box max dimension of the detected hand."""
    if len(landmarks) < 21:
        return 0.0
    xs = [lm.x for lm in landmarks]
    ys = [lm.y for lm in landmarks]
    return max(max(xs) - min(xs), max(ys) - min(ys))


def _is_finger_extended(
    landmarks: Sequence[LandmarkPoint],
    mcp_idx: int,
    pip_idx: int,
    tip_idx: int,
) -> bool:
    wrist = landmarks[WRIST]
    return _dist2d(wrist, landmarks[tip_idx]) > _dist2d(wrist, landmarks[pip_idx]) * 1.06 and (
        _dist2d(wrist, landmarks[tip_idx]) > _dist2d(wrist, landmarks[mcp_idx]) * 1.20
    )


def _is_finger_curled(
    landmarks: Sequence[LandmarkPoint],
    mcp_idx: int,
    pip_idx: int,
    tip_idx: int,
) -> bool:
    wrist = landmarks[WRIST]
    return _dist2d(wrist, landmarks[tip_idx]) < _dist2d(wrist, landmarks[pip_idx]) * 1.05


def validate_gesture_geometry(gesture: str, landmarks: Optional[Sequence[LandmarkPoint]]) -> bool:
    """Apply geometric sanity checks on top of MediaPipe's classifier to prevent eating misfires."""
    if landmarks is None:
        return True
    if len(landmarks) < 21:
        return False

    index_ext = _is_finger_extended(landmarks, INDEX_MCP, INDEX_PIP, INDEX_TIP)
    middle_ext = _is_finger_extended(landmarks, MIDDLE_MCP, MIDDLE_PIP, MIDDLE_TIP)
    ring_ext = _is_finger_extended(landmarks, RING_MCP, RING_PIP, RING_TIP)
    pinky_ext = _is_finger_extended(landmarks, PINKY_MCP, PINKY_PIP, PINKY_TIP)

    index_curl = _is_finger_curled(landmarks, INDEX_MCP, INDEX_PIP, INDEX_TIP)
    middle_curl = _is_finger_curled(landmarks, MIDDLE_MCP, MIDDLE_PIP, MIDDLE_TIP)
    ring_curl = _is_finger_curled(landmarks, RING_MCP, RING_PIP, RING_TIP)
    pinky_curl = _is_finger_curled(landmarks, PINKY_MCP, PINKY_PIP, PINKY_TIP)

    if gesture == "Thumb_Up":
        thumb_dy = landmarks[THUMB_MCP].y - landmarks[THUMB_TIP].y
        return thumb_dy > 0.04 and middle_curl and ring_curl and pinky_curl

    if gesture == "Thumb_Down":
        thumb_dy = landmarks[THUMB_TIP].y - landmarks[THUMB_MCP].y
        return thumb_dy > 0.04 and middle_curl and ring_curl and pinky_curl

    if gesture == "Open_Palm":
        return sum((index_ext, middle_ext, ring_ext, pinky_ext)) >= 3

    if gesture == "Closed_Fist":
        return sum((index_curl, middle_curl, ring_curl, pinky_curl)) >= 3

    if gesture == "Victory":
        return index_ext and middle_ext and ring_curl and pinky_curl

    if gesture == "Pointing_Up":
        return index_ext and middle_curl and ring_curl and pinky_curl

    return True


class GestureStateMachine:
    """Wake-window, temporal consensus, and cooldown state machine for eating-safe control."""

    def __init__(self, config: HeyHandyConfig) -> None:
        self.config = config
        self._armed = bool(config.always_on_gestures)
        self._armed_until = 0.0
        self._history: Deque[Optional[str]] = deque(maxlen=max(4, config.stability_frames + 2))
        self._last_discrete_at = -1e9
        self._active_continuous: Optional[str] = None
        self._last_continuous_at = -1e9
        self._miss_streak = 0

    @property
    def is_armed(self) -> bool:
        return self._armed or self.config.always_on_gestures

    def remaining_seconds(self, now: float) -> float:
        if self.config.always_on_gestures:
            return float("inf")
        if not self._armed:
            return 0.0
        return max(0.0, self._armed_until - now)

    def update_config(self, config: HeyHandyConfig, now: float) -> None:
        self.config = config
        self._history = deque(self._history, maxlen=max(4, config.stability_frames + 2))
        if config.always_on_gestures:
            self._armed = True

    def wake(self, now: float) -> None:
        """Arm gesture recognition for wake_window_s seconds."""
        self._armed = True
        self._armed_until = now + self.config.wake_window_s
        self._history.clear()
        self._active_continuous = None
        self._miss_streak = 0

    def sleep(self) -> None:
        """Disarm gesture recognition (ignored if always_on_gestures is enabled)."""
        self._history.clear()
        self._active_continuous = None
        self._miss_streak = 0
        if not self.config.always_on_gestures:
            self._armed = False
            self._armed_until = 0.0

    def tick(self, now: float) -> bool:
        """Advance clock; returns True if wake window just expired and transitioned to sleep."""
        if self.config.always_on_gestures:
            self._armed = True
            return False
        if self._armed and now >= self._armed_until:
            self.sleep()
            return True
        return False

    def process_detection(
        self,
        gesture_name: Optional[str],
        confidence: float,
        landmarks: Optional[Sequence[LandmarkPoint]],
        now: float,
    ) -> Optional[GestureEvent]:
        """Evaluate one frame's MediaPipe detection and emit a GestureEvent when confirmed."""
        if self.tick(now) or not self.is_armed:
            return None

        action = self.config.gesture_map.get(gesture_name or "", "none")
        valid = (
            bool(gesture_name)
            and action != "none"
            and confidence >= self.config.min_confidence
            and (landmarks is None or hand_span(landmarks) >= self.config.min_hand_span)
            and validate_gesture_geometry(gesture_name or "", landmarks)
        )

        if not valid:
            self._history.append(None)
            self._miss_streak += 1
            if self._miss_streak >= 2:
                self._active_continuous = None
            return None

        is_continuous = action in CONTINUOUS_ACTIONS
        if not is_continuous and (now - self._last_discrete_at) < self.config.action_cooldown_s:
            # Do not let frames held during cooldown accumulate toward an instant re-trigger.
            self._history.clear()
            return None

        self._miss_streak = 0
        self._history.append(gesture_name)
        counts = Counter(g for g in self._history if g is not None)
        if not counts or counts.get(gesture_name, 0) < self.config.stability_frames:
            return None

        if is_continuous:
            # Keep wake window alive while the user holds Thumb Up / Down for volume.
            if not self.config.always_on_gestures:
                self._armed_until = max(
                    self._armed_until,
                    now + max(4.0, self.config.post_action_grace_s + 1.5),
                )
            if (
                self._active_continuous != action
                or (now - self._last_continuous_at) >= self.config.volume_repeat_s
            ):
                self._active_continuous = action
                self._last_continuous_at = now
                return GestureEvent(
                    gesture=gesture_name or "",
                    action=action,
                    confidence=confidence,
                    continuous=True,
                )
            return None

        self._active_continuous = None
        self._last_discrete_at = now
        self._history.clear()

        if action == "sleep":
            self.sleep()
        elif not self.config.always_on_gestures:
            self._armed_until = now + self.config.post_action_grace_s

        return GestureEvent(
            gesture=gesture_name or "",
            action=action,
            confidence=confidence,
            continuous=False,
        )


@dataclass(frozen=True)
class PreviewFrame:
    """Lightweight diagnostic payload emitted only when camera preview is enabled."""

    rgb_image: np.ndarray
    gesture: str
    confidence: float
    landmarks: Tuple[LandmarkPoint, ...]
    armed: bool


class CameraGestureWorker:
    """Runs MediaPipe GestureRecognizer only while armed (or previewing/warm)."""

    def __init__(
        self,
        model_paths: ModelPaths,
        config: HeyHandyConfig,
        on_event: Optional[Callable[[GestureEvent], None]] = None,
        on_preview: Optional[Callable[[PreviewFrame], None]] = None,
        on_sleep: Optional[Callable[[], None]] = None,
        on_countdown: Optional[Callable[[float], None]] = None,
        on_error: Optional[Callable[[str], None]] = None,
    ) -> None:
        self.model_paths = model_paths
        self.config = config
        self.state_machine = GestureStateMachine(config)

        self.on_event = on_event
        self.on_preview = on_preview
        self.on_sleep = on_sleep
        self.on_countdown = on_countdown
        self.on_error = on_error

        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._wake_event = threading.Event()
        self._preview_enabled = False
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._run_loop, name="hey-handy-cam", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._wake_event.set()
        with self._lock:
            t = self._thread
            self._thread = None
        if t and t.is_alive():
            t.join(timeout=2.5)

    def wake(self) -> None:
        with self._lock:
            self.state_machine.wake(time.monotonic())
        self._wake_event.set()

    def sleep_now(self) -> None:
        with self._lock:
            self.state_machine.sleep()
        if self.on_sleep:
            self.on_sleep()

    def set_preview_enabled(self, enabled: bool) -> None:
        self._preview_enabled = bool(enabled)
        if enabled:
            self._wake_event.set()

    def update_config(self, config: HeyHandyConfig) -> None:
        with self._lock:
            self.config = config
            self.state_machine.update_config(config, time.monotonic())
        if config.always_on_gestures or config.keep_camera_warm:
            self._wake_event.set()

    def _should_keep_camera_open(self) -> bool:
        with self._lock:
            return (
                self.state_machine.is_armed
                or self._preview_enabled
                or self.config.keep_camera_warm
            )

    def _run_loop(self) -> None:
        try:
            import cv2
            import mediapipe as mp
            from mediapipe.tasks import python as mp_python
            from mediapipe.tasks.python import vision
        except Exception as exc:
            if self.on_error:
                self.on_error(f"Vision dependencies unavailable: {exc}")
            return

        if not self.model_paths.gesture_ready:
            if self.on_error:
                self.on_error("Gesture recognition model file is missing.")
            return

        try:
            options = vision.GestureRecognizerOptions(
                base_options=mp_python.BaseOptions(model_asset_path=str(self.model_paths.gesture_task)),
                running_mode=vision.RunningMode.IMAGE,
                num_hands=1,
                min_hand_detection_confidence=0.45,
                min_hand_presence_confidence=0.45,
                min_tracking_confidence=0.45,
            )
            recognizer = vision.GestureRecognizer.create_from_options(options)
        except Exception as exc:
            if self.on_error:
                self.on_error(f"Failed to load MediaPipe GestureRecognizer: {exc}")
            return

        cap = None
        last_countdown_emit = 0.0

        def _close_cap() -> None:
            nonlocal cap
            if cap is not None:
                try:
                    cap.release()
                except Exception:
                    pass
                cap = None

        try:
            while not self._stop_event.is_set():
                need_cam = self._should_keep_camera_open()
                if not need_cam:
                    _close_cap()
                    self._wake_event.clear()
                    self._wake_event.wait(0.25)
                    continue

                if cap is None:
                    cap = cv2.VideoCapture(self.config.camera_index)
                    if not cap.isOpened():
                        _close_cap()
                        if self.on_error:
                            self.on_error(f"Unable to open webcam #{self.config.camera_index}.")
                        with self._lock:
                            self.state_machine.sleep()
                        if self.on_sleep:
                            self.on_sleep()
                        self._wake_event.clear()
                        self._wake_event.wait(1.0)
                        continue
                    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 360)

                ok, frame = cap.read()
                if not ok or frame is None:
                    time.sleep(0.03)
                    continue

                now = time.monotonic()
                with self._lock:
                    expired = self.state_machine.tick(now)
                    is_armed = self.state_machine.is_armed
                    remaining = self.state_machine.remaining_seconds(now)

                if expired and self.on_sleep:
                    self.on_sleep()

                if is_armed and not math.isinf(remaining) and (now - last_countdown_emit) >= 0.35:
                    last_countdown_emit = now
                    if self.on_countdown:
                        self.on_countdown(remaining)

                # If camera is only open because keep_camera_warm=True (and not previewing), sleep lightly.
                if not is_armed and not self._preview_enabled:
                    time.sleep(0.08)
                    continue

                frame = cv2.flip(frame, 1)
                h, w = frame.shape[:2]
                if w > 640:
                    scale = 640.0 / w
                    frame = cv2.resize(frame, (640, max(1, int(h * scale))))

                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                result = recognizer.recognize(mp_image)

                gesture_name = ""
                score = 0.0
                landmarks: Tuple[LandmarkPoint, ...] = ()

                if result.hand_landmarks:
                    landmarks = tuple(
                        LandmarkPoint(lm.x, lm.y, lm.z) for lm in result.hand_landmarks[0]
                    )
                if result.gestures and result.gestures[0]:
                    top = result.gestures[0][0]
                    gesture_name = top.category_name or ""
                    score = float(top.score or 0.0)

                if self._preview_enabled and self.on_preview:
                    self.on_preview(
                        PreviewFrame(
                            rgb_image=rgb,
                            gesture=gesture_name,
                            confidence=score,
                            landmarks=landmarks,
                            armed=is_armed,
                        )
                    )

                if is_armed:
                    with self._lock:
                        event = self.state_machine.process_detection(
                            gesture_name=gesture_name or None,
                            confidence=score,
                            landmarks=landmarks or None,
                            now=now,
                        )
                        just_slept = event is not None and event.action == "sleep"
                    if event and self.on_event:
                        self.on_event(event)
                    if just_slept and self.on_sleep:
                        self.on_sleep()

                time.sleep(0.03)  # ~30 fps cap
        finally:
            _close_cap()
            try:
                recognizer.close()
            except Exception:
                pass

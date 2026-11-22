"""Tests for the wake-window, geometry guards, and eating-safe gesture state machine."""

from __future__ import annotations

from typing import List

from hey_handy.config import HeyHandyConfig
from hey_handy.gesture_engine import GestureStateMachine, LandmarkPoint, validate_gesture_geometry


def _make_hand(
    thumb_tip_y: float = 0.5,
    thumb_mcp_y: float = 0.5,
    index_ext: bool = False,
    middle_ext: bool = False,
    ring_ext: bool = False,
    pinky_ext: bool = False,
    scale: float = 1.0,
) -> List[LandmarkPoint]:
    """Build a synthetic 21-landmark hand scaled around wrist (0.5, 0.8)."""
    pts = [LandmarkPoint(0.5, 0.8)] * 21

    def s(dx: float, dy: float) -> LandmarkPoint:
        return LandmarkPoint(0.5 + dx * scale, 0.8 + dy * scale)

    pts[0] = s(0.0, 0.0)
    pts[1] = s(-0.04, -0.05)
    pts[2] = LandmarkPoint(0.5 - 0.06 * scale, 0.8 + (thumb_mcp_y - 0.8) * scale)
    pts[3] = LandmarkPoint(
        0.5 - 0.07 * scale,
        0.8 + (((thumb_mcp_y + thumb_tip_y) / 2.0) - 0.8) * scale,
    )
    pts[4] = LandmarkPoint(0.5 - 0.08 * scale, 0.8 + (thumb_tip_y - 0.8) * scale)

    fingers = [
        (5, 6, 7, 8, -0.04, index_ext),
        (9, 10, 11, 12, -0.01, middle_ext),
        (13, 14, 15, 16, 0.02, ring_ext),
        (17, 18, 19, 20, 0.05, pinky_ext),
    ]
    for mcp, pip, dip, tip, x_off, extended in fingers:
        pts[mcp] = s(x_off, -0.14)
        pts[pip] = s(x_off, -0.22)
        if extended:
            pts[dip] = s(x_off, -0.28)
            pts[tip] = s(x_off, -0.34)
        else:
            pts[dip] = s(x_off, -0.18)
            pts[tip] = s(x_off, -0.13)
    return pts


def test_sleeping_ignores_all_gestures() -> None:
    cfg = HeyHandyConfig(stability_frames=2).normalized()
    sm = GestureStateMachine(cfg)
    palm = _make_hand(index_ext=True, middle_ext=True, ring_ext=True, pinky_ext=True)
    for i in range(5):
        assert sm.process_detection("Open_Palm", 0.95, palm, now=1.0 + i * 0.05) is None
    assert not sm.is_armed


def test_wake_window_arms_and_expires() -> None:
    cfg = HeyHandyConfig(wake_window_s=6.0, stability_frames=2).normalized()
    sm = GestureStateMachine(cfg)
    sm.wake(now=10.0)
    assert sm.is_armed
    assert sm.remaining_seconds(12.0) == 4.0
    assert sm.tick(15.9) is False
    assert sm.tick(16.0) is True
    assert not sm.is_armed


def test_eating_jitter_rejected_without_stability_consensus() -> None:
    cfg = HeyHandyConfig(stability_frames=4).normalized()
    sm = GestureStateMachine(cfg)
    sm.wake(now=0.0)
    palm = _make_hand(index_ext=True, middle_ext=True, ring_ext=True, pinky_ext=True)
    # 2 brief frames (e.g. moving fork) followed by none should never fire
    assert sm.process_detection("Open_Palm", 0.92, palm, now=0.1) is None
    assert sm.process_detection("Open_Palm", 0.92, palm, now=0.2) is None
    assert sm.process_detection(None, 0.0, None, now=0.3) is None
    assert sm.process_detection(None, 0.0, None, now=0.4) is None


def test_geometry_guard_rejects_tiny_distant_hand_and_sideways_thumb() -> None:
    cfg = HeyHandyConfig(stability_frames=2, min_hand_span=0.08).normalized()
    sm = GestureStateMachine(cfg)
    sm.wake(now=0.0)

    # Distant background hand smaller than min_hand_span
    tiny_palm = _make_hand(index_ext=True, middle_ext=True, ring_ext=True, pinky_ext=True, scale=0.1)
    assert sm.process_detection("Open_Palm", 0.95, tiny_palm, now=0.1) is None
    assert sm.process_detection("Open_Palm", 0.95, tiny_palm, now=0.2) is None

    # Sideways thumb (not pointing genuinely up)
    flat_thumb = _make_hand(thumb_tip_y=0.62, thumb_mcp_y=0.63)
    assert validate_gesture_geometry("Thumb_Up", flat_thumb) is False

    # Genuine thumbs up & thumbs down pass
    thumb_up = _make_hand(thumb_tip_y=0.45, thumb_mcp_y=0.60)
    thumb_down = _make_hand(thumb_tip_y=0.76, thumb_mcp_y=0.60)
    assert validate_gesture_geometry("Thumb_Up", thumb_up) is True
    assert validate_gesture_geometry("Thumb_Down", thumb_down) is True


def test_discrete_gesture_fires_once_with_cooldown_and_grace() -> None:
    cfg = HeyHandyConfig(
        wake_window_s=8.0,
        post_action_grace_s=3.0,
        action_cooldown_s=1.4,
        stability_frames=3,
    ).normalized()
    sm = GestureStateMachine(cfg)
    sm.wake(now=0.0)

    victory = _make_hand(index_ext=True, middle_ext=True, ring_ext=False, pinky_ext=False)
    assert sm.process_detection("Victory", 0.9, victory, now=0.1) is None
    assert sm.process_detection("Victory", 0.9, victory, now=0.2) is None
    ev = sm.process_detection("Victory", 0.9, victory, now=0.3)
    assert ev is not None
    assert ev.action == "fullscreen"
    assert ev.continuous is False
    # Remaining time reset to post_action_grace_s (3.0s -> expires at 3.3s)
    assert abs(sm.remaining_seconds(0.3) - 3.0) < 1e-6

    # Re-holding immediately during 1.4s cooldown must not double-trigger
    for idx in range(5):
        assert sm.process_detection("Victory", 0.9, victory, now=0.5 + idx * 0.1) is None

    # After cooldown (at 1.8s+) it can fire again
    assert sm.process_detection("Victory", 0.9, victory, now=1.8) is None
    assert sm.process_detection("Victory", 0.9, victory, now=1.9) is None
    ev2 = sm.process_detection("Victory", 0.9, victory, now=2.0)
    assert ev2 is not None
    assert ev2.action == "fullscreen"


def test_continuous_volume_repeats_and_extends_wake_window() -> None:
    cfg = HeyHandyConfig(
        wake_window_s=3.0,
        post_action_grace_s=2.0,
        volume_repeat_s=0.25,
        stability_frames=3,
    ).normalized()
    sm = GestureStateMachine(cfg)
    sm.wake(now=0.0)

    thumb_up = _make_hand(thumb_tip_y=0.45, thumb_mcp_y=0.60)
    assert sm.process_detection("Thumb_Up", 0.9, thumb_up, now=2.5) is None
    assert sm.process_detection("Thumb_Up", 0.9, thumb_up, now=2.6) is None
    ev1 = sm.process_detection("Thumb_Up", 0.9, thumb_up, now=2.7)
    assert ev1 is not None and ev1.action == "volume_up" and ev1.continuous
    # Extended beyond original 3.0s deadline so volume adjustment isn't cut off
    assert sm.remaining_seconds(2.7) >= 4.0

    # No repeat before 0.25s
    assert sm.process_detection("Thumb_Up", 0.9, thumb_up, now=2.85) is None
    # Repeats once >= 0.25s elapses
    ev2 = sm.process_detection("Thumb_Up", 0.9, thumb_up, now=3.0)
    assert ev2 is not None and ev2.action == "volume_up"

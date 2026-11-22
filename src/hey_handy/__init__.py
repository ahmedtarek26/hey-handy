"""Hey Handy — Wake-word gated hand gesture controller for active media tabs."""

from __future__ import annotations

__all__ = ["__version__", "ensure_qt_env"]
__version__ = "0.1.0"


def ensure_qt_env() -> None:
    """Prevent OpenCV-bundled Qt plugin paths or headless GTK themes from clashing with PySide6."""
    import os

    plugin_path = os.environ.get("QT_QPA_PLATFORM_PLUGIN_PATH", "")
    if "cv2" in plugin_path:
        os.environ.pop("QT_QPA_PLATFORM_PLUGIN_PATH", None)
    if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
        os.environ["QT_QPA_PLATFORMTHEME"] = ""

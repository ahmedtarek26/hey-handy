"""Verify browser extension manifest & content-script media controls via Node."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXT = ROOT / "extension"


def test_extension_manifest_is_valid_unified_mv3() -> None:
    manifest = json.loads((EXT / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["manifest_version"] == 3
    assert manifest["background"]["service_worker"] == "background.js"
    assert manifest["background"]["scripts"] == ["background.js"]
    assert "scripting" in manifest["permissions"]
    assert "tabs" in manifest["permissions"]
    assert "gecko" in manifest["browser_specific_settings"]


def test_extension_content_script_controls_video_and_audio_tabs() -> None:
    node = shutil.which("node")
    assert node is not None, "node is required to run extension DOM smoke tests"

    script = r"""
    const fs = require("fs");
    const assert = require("assert");
    const vm = require("vm");

    function makeMedia(tag, { paused = false, duration = 120, volume = 0.6 } = {}) {
      const el = {
        tagName: tag.toUpperCase(),
        paused,
        ended: false,
        readyState: 4,
        currentSrc: "https://example.com/media.mp4",
        src: "https://example.com/media.mp4",
        currentTime: 42.5,
        duration,
        volume,
        muted: false,
        style: {},
        classList: new Set(),
        parentElement: null,
        getBoundingClientRect: () => ({ width: 800, height: 450 }),
        closest: () => null,
        play: async () => { el.paused = false; },
        pause: () => { el.paused = true; },
      };
      el.classList.add = (c) => Set.prototype.add.call(el.classList, c);
      el.classList.remove = (c) => Set.prototype.delete.call(el.classList, c);
      return el;
    }

    const video = makeMedia("video", { paused: false });
    const audio = makeMedia("audio", { paused: true, volume: 0.4 });
    let mediaNodes = [video];

    const docEl = {
      classList: new Set(),
      appendChild: () => {},
    };
    docEl.classList.add = (c) => Set.prototype.add.call(docEl.classList, c);
    docEl.classList.remove = (c) => Set.prototype.delete.call(docEl.classList, c);

    const sandbox = {
      window: null,
      document: {
        title: "Eating Lunch Video",
        documentElement: docEl,
        body: { classList: docEl.classList },
        head: { appendChild: () => {} },
        fullscreenElement: null,
        exitFullscreen: async () => {},
        getElementById: () => null,
        createElement: () => ({ style: {}, attachShadow: () => ({ innerHTML: "", getElementById: () => ({ className: "", textContent: "", classList: docEl.classList }) }) }),
        querySelector: () => null,
        querySelectorAll: (sel) => (sel === "video, audio" ? mediaNodes : []),
      },
      setTimeout,
      clearTimeout,
    };
    sandbox.window = {
      addEventListener: () => {},
    };
    sandbox.globalThis = sandbox;

    const code = fs.readFileSync(process.argv[1], "utf8");
    vm.runInNewContext(code, sandbox);

    (async () => {
      // 1. Pause stops video and keeps timestamp
      let r = await sandbox.window.__heyHandyHandle({ action: "pause" });
      assert.strictEqual(r.handled, true);
      assert.strictEqual(video.paused, true);
      assert.strictEqual(video.currentTime, 42.5);

      // 2. Play/Pause resumes from same timestamp
      r = await sandbox.window.__heyHandyHandle({ action: "play_pause" });
      assert.strictEqual(r.handled, true);
      assert.strictEqual(video.paused, false);
      assert.strictEqual(video.currentTime, 42.5);

      // 3. Volume up/down and mute
      r = await sandbox.window.__heyHandyHandle({ action: "volume_up", step: 10 });
      assert.strictEqual(r.volumePercent, 70);
      r = await sandbox.window.__heyHandyHandle({ action: "volume_down", step: 15 });
      assert.strictEqual(r.volumePercent, 55);
      r = await sandbox.window.__heyHandyHandle({ action: "mute" });
      assert.strictEqual(r.muted, true);

      // 4. Fullscreen toggles cinema container & windowFullscreen hint
      r = await sandbox.window.__heyHandyHandle({ action: "fullscreen" });
      assert.strictEqual(r.handled, true);
      assert.strictEqual(r.windowFullscreen, "enter");
      assert.strictEqual(video.classList.has("hh-fs-container"), true);

      r = await sandbox.window.__heyHandyHandle({ action: "fullscreen" });
      assert.strictEqual(r.windowFullscreen, "restore");
      assert.strictEqual(video.classList.has("hh-fs-container"), false);

      // 5. Audio-only tab support
      mediaNodes = [audio];
      r = await sandbox.window.__heyHandyHandle({ action: "play_pause" });
      assert.strictEqual(r.handled, true);
      assert.strictEqual(r.mediaType, "audio");
      assert.strictEqual(audio.paused, false);
      console.log("EXT_JS_OK");
    })().catch((err) => {
      console.error(err);
      process.exit(1);
    });
    """

    proc = subprocess.run(
        [node, "-e", script, str(EXT / "content.js")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, f"stderr={proc.stderr}\nstdout={proc.stdout}"
    assert "EXT_JS_OK" in proc.stdout

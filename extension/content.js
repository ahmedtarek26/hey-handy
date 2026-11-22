/* Hey Handy content script — controls active tab video/audio & renders isolated HUD pill. */
(() => {
  if (window.__heyHandyInjected) return;
  window.__heyHandyInjected = true;

  const STATE_KEY = "__heyHandyState";
  const STYLE_ID = "hey-handy-fullscreen-style";
  const HUD_ID = "hey-handy-hud-host";

  function getState() {
    if (!window[STATE_KEY]) {
      window[STATE_KEY] = {
        lastMedia: null,
        pseudoFsContainer: null,
        pseudoFsVideo: null,
        hudTimer: null,
      };
    }
    return window[STATE_KEY];
  }

  function findAllMedia(root = document, out = []) {
    if (!root || !root.querySelectorAll) return out;
    const direct = root.querySelectorAll("video, audio");
    for (const el of direct) out.push(el);

    const all = root.querySelectorAll("*");
    for (const el of all) {
      if (el.shadowRoot) {
        findAllMedia(el.shadowRoot, out);
      }
    }
    return out;
  }

  function elementScore(el) {
    if (el.readyState === 0 && !el.currentSrc && !el.src && !el.srcObject) {
      return -1;
    }
    let score = 0;
    const isPlaying = !el.paused && !el.ended && el.readyState > 1;
    if (isPlaying) score += 1000;
    if (getState().lastMedia === el) score += 250;
    if (el.tagName === "VIDEO") {
      const rect = el.getBoundingClientRect();
      if (rect.width > 40 && rect.height > 40) {
        score += 120 + Math.min(200, Math.round((rect.width * rect.height) / 5000));
      } else {
        score += 20;
      }
    } else {
      score += 60;
    }
    if (el.currentTime > 0) score += 40;
    if (Number.isFinite(el.duration) && el.duration > 0) score += 30;
    if (!el.muted && el.volume > 0) score += 15;
    return score;
  }

  function pickBestMedia() {
    const list = findAllMedia();
    if (!list.length) return null;
    let best = null;
    let bestScore = -1;
    for (const el of list) {
      const s = elementScore(el);
      if (s > bestScore) {
        bestScore = s;
        best = el;
      }
    }
    return bestScore >= 0 ? best : null;
  }

  function findSiteButton(action) {
    const selectorsByAction = {
      play_pause: [
        '[data-testid="control-button-playpause"]',
        ".ytp-play-button",
        '[data-a-target="player-play-pause-button"]',
        ".playControl",
        'button[aria-label*="Pause" i]',
        'button[aria-label*="Play" i]',
      ],
      pause: [
        '[data-testid="control-button-playpause"][aria-label*="Pause" i]',
        '.ytp-play-button[data-title-no-tooltip="Pause"]',
        'button[aria-label*="Pause" i]',
      ],
      play: [
        '[data-testid="control-button-playpause"][aria-label*="Play" i]',
        '.ytp-play-button[data-title-no-tooltip="Play"]',
        'button[aria-label*="Play" i]',
      ],
      fullscreen: [
        ".ytp-fullscreen-button",
        '[data-a-target="player-fullscreen-button"]',
        'button[aria-label*="Full screen" i]',
        'button[aria-label*="Fullscreen" i]',
      ],
    };
    const candidates = selectorsByAction[action] || [];
    for (const sel of candidates) {
      const btn = document.querySelector(sel);
      if (btn) return btn;
    }
    return null;
  }

  function ensurePseudoFsStyles() {
    if (document.getElementById(STYLE_ID)) return;
    const style = document.createElement("style");
    style.id = STYLE_ID;
    style.textContent = `
      html.hh-fs-lock, body.hh-fs-lock {
        overflow: hidden !important;
      }
      .hh-fs-container {
        position: fixed !important;
        inset: 0 !important;
        width: 100vw !important;
        height: 100vh !important;
        max-width: 100vw !important;
        max-height: 100vh !important;
        margin: 0 !important;
        padding: 0 !important;
        z-index: 2147483645 !important;
        background: #000 !important;
      }
      .hh-fs-video {
        position: absolute !important;
        inset: 0 !important;
        top: 0 !important;
        left: 0 !important;
        width: 100% !important;
        height: 100% !important;
        max-width: 100vw !important;
        max-height: 100vh !important;
        object-fit: contain !important;
      }
    `;
    (document.head || document.documentElement).appendChild(style);
  }

  function findPlayerContainer(video) {
    const known = video.closest(
      ".html5-video-player, [data-uia='player'], .video-js, .plyr, [data-a-target='video-player']"
    );
    if (known) return known;

    const vRect = video.getBoundingClientRect();
    let cur = video.parentElement;
    let best = video;
    while (cur && cur !== document.body && cur !== document.documentElement) {
      const r = cur.getBoundingClientRect();
      if (r.width <= Math.max(vRect.width * 1.35, vRect.width + 60) &&
          r.height <= Math.max(vRect.height * 1.35, vRect.height + 80)) {
        best = cur;
        cur = cur.parentElement;
      } else {
        break;
      }
    }
    return best;
  }

  function enterPseudoFullscreen(video) {
    ensurePseudoFsStyles();
    const st = getState();
    const container = findPlayerContainer(video);
    document.documentElement.classList.add("hh-fs-lock");
    if (document.body) document.body.classList.add("hh-fs-lock");
    container.classList.add("hh-fs-container");
    if (container !== video) video.classList.add("hh-fs-video");
    st.pseudoFsContainer = container;
    st.pseudoFsVideo = video;
    if (typeof Event === "function" && typeof window.dispatchEvent === "function") {
      window.dispatchEvent(new Event("resize"));
    }
  }

  function exitPseudoFullscreen() {
    const st = getState();
    document.documentElement.classList.remove("hh-fs-lock");
    if (document.body) document.body.classList.remove("hh-fs-lock");
    if (st.pseudoFsContainer) st.pseudoFsContainer.classList.remove("hh-fs-container");
    if (st.pseudoFsVideo) st.pseudoFsVideo.classList.remove("hh-fs-video");
    st.pseudoFsContainer = null;
    st.pseudoFsVideo = null;
    if (typeof Event === "function" && typeof window.dispatchEvent === "function") {
      window.dispatchEvent(new Event("resize"));
    }
  }

  function renderHud(hud) {
    const hostParent = document.fullscreenElement || document.documentElement;
    if (!hostParent) return;
    let host = document.getElementById(HUD_ID);
    if (!host) {
      host = document.createElement("div");
      host.id = HUD_ID;
      host.style.cssText =
        "position:fixed;top:18px;right:18px;z-index:2147483647;pointer-events:none;";
      const shadow = host.attachShadow({ mode: "open" });
      shadow.innerHTML = `
        <style>
          .pill {
            display: flex;
            align-items: center;
            gap: 10px;
            padding: 10px 15px;
            border-radius: 14px;
            background: rgba(15, 18, 25, 0.90);
            border: 1px solid rgba(255, 255, 255, 0.14);
            box-shadow: 0 10px 28px rgba(0, 0, 0, 0.42);
            backdrop-filter: blur(10px);
            font-family: system-ui, -apple-system, Segoe UI, sans-serif;
            color: #f8fafc;
            min-width: 195px;
            opacity: 0;
            transform: translateY(-6px);
            transition: opacity 150ms ease, transform 150ms ease;
          }
          .pill.visible {
            opacity: 1;
            transform: translateY(0);
          }
          .dot {
            width: 10px;
            height: 10px;
            border-radius: 999px;
            background: #2dd4bf;
            box-shadow: 0 0 10px rgba(45, 212, 191, 0.75);
            flex-shrink: 0;
          }
          .dot.action {
            background: #22c55e;
            box-shadow: 0 0 10px rgba(34, 197, 94, 0.75);
          }
          .title {
            font-size: 13px;
            font-weight: 600;
            line-height: 1.2;
          }
          .sub {
            font-size: 11px;
            color: #94a3b8;
            line-height: 1.25;
            margin-top: 2px;
          }
        </style>
        <div class="pill" id="pill">
          <div class="dot" id="dot"></div>
          <div>
            <div class="title" id="title">Hey Handy</div>
            <div class="sub" id="sub">Ready</div>
          </div>
        </div>
      `;
    }
    if (host.parentNode !== hostParent) {
      hostParent.appendChild(host);
    }

    const shadow = host.shadowRoot;
    const pill = shadow.getElementById("pill");
    const dot = shadow.getElementById("dot");
    const title = shadow.getElementById("title");
    const sub = shadow.getElementById("sub");
    const st = getState();

    clearTimeout(st.hudTimer);
    if (hud.state === "sleeping") {
      pill.classList.remove("visible");
      return;
    }

    if (hud.state === "armed") {
      dot.className = "dot";
      title.textContent = "Hey Handy • Ready";
      sub.textContent = hud.alwaysOn
        ? "Always-on gesture mode"
        : `Show a gesture (${hud.remaining ?? 8}s)`;
      pill.classList.add("visible");
      return;
    }

    if (hud.state === "action") {
      dot.className = "dot action";
      title.textContent = hud.label || "Hey Handy";
      sub.textContent = hud.detail || "Active tab";
      pill.classList.add("visible");
      st.hudTimer = setTimeout(() => {
        pill.classList.remove("visible");
      }, 1800);
    }
  }

  function probeFrame() {
    const el = pickBestMedia();
    const hasSiteControl = Boolean(findSiteButton("play_pause"));
    let score = 0;
    let mediaType = "";
    if (el) {
      score = elementScore(el);
      mediaType = el.tagName === "VIDEO" ? "video" : "audio";
    } else if (hasSiteControl) {
      score = 10;
      mediaType = "audio";
    }
    return {
      score,
      mediaType,
      title: document.title || "",
      hasFullscreen: Boolean(document.fullscreenElement || getState().pseudoFsContainer),
    };
  }

  async function handleCommand(cmd) {
    if (!cmd || !cmd.action) return { handled: false };
    if (cmd.action === "probe") return probeFrame();
    if (cmd.action === "hud") {
      renderHud(cmd);
      return { handled: true };
    }

    const st = getState();
    const el = pickBestMedia();
    const mediaType = el ? (el.tagName === "VIDEO" ? "video" : "audio") : "";

    if (cmd.action === "play_pause") {
      if (el) {
        st.lastMedia = el;
        if (!el.paused && !el.ended) {
          el.pause();
          return {
            handled: true,
            label: "Paused",
            detail: document.title,
            paused: true,
            mediaType,
            title: document.title,
          };
        }
        try {
          await el.play();
        } catch (_) {
          const btn = findSiteButton("play_pause");
          if (btn) btn.click();
        }
        return {
          handled: true,
          label: "Resumed",
          detail: document.title,
          paused: false,
          mediaType,
          title: document.title,
        };
      }
      const btn = findSiteButton("play_pause");
      if (btn) {
        btn.click();
        return { handled: true, label: "Play / Pause", detail: document.title, title: document.title };
      }
      return { handled: false };
    }

    if (cmd.action === "pause") {
      const list = findAllMedia();
      let pausedAny = false;
      for (const item of list) {
        if (!item.paused && !item.ended) {
          st.lastMedia = item;
          item.pause();
          pausedAny = true;
        }
      }
      if (pausedAny || el) {
        if (el && !pausedAny) {
          st.lastMedia = el;
          el.pause();
        }
        return {
          handled: true,
          label: "Paused",
          detail: document.title,
          paused: true,
          mediaType,
          title: document.title,
        };
      }
      const btn = findSiteButton("pause") || findSiteButton("play_pause");
      if (btn) {
        btn.click();
        return { handled: true, label: "Paused", detail: document.title, title: document.title };
      }
      return { handled: false };
    }

    if (cmd.action === "play") {
      if (el) {
        st.lastMedia = el;
        try {
          await el.play();
        } catch (_) {
          const btn = findSiteButton("play") || findSiteButton("play_pause");
          if (btn) btn.click();
        }
        return {
          handled: true,
          label: "Resumed",
          detail: document.title,
          paused: false,
          mediaType,
          title: document.title,
        };
      }
      const btn = findSiteButton("play") || findSiteButton("play_pause");
      if (btn) {
        btn.click();
        return { handled: true, label: "Resumed", detail: document.title, title: document.title };
      }
      return { handled: false };
    }

    if (cmd.action === "fullscreen") {
      if (document.fullscreenElement) {
        try {
          await document.exitFullscreen();
        } catch (_) {}
        exitPseudoFullscreen();
        return {
          handled: true,
          label: "Exited Fullscreen",
          detail: document.title,
          windowFullscreen: "restore",
          mediaType,
          title: document.title,
        };
      }

      if (st.pseudoFsContainer) {
        exitPseudoFullscreen();
        return {
          handled: true,
          label: "Exited Fullscreen",
          detail: document.title,
          windowFullscreen: "restore",
          mediaType,
          title: document.title,
        };
      }

      const videos = findAllMedia().filter((m) => m.tagName === "VIDEO");
      const targetVideo = videos.length ? videos.sort((a, b) => elementScore(b) - elementScore(a))[0] : null;
      if (targetVideo) {
        enterPseudoFullscreen(targetVideo);
        return {
          handled: true,
          label: "Fullscreen",
          detail: document.title,
          windowFullscreen: "enter",
          mediaType: "video",
          title: document.title,
        };
      }

      return {
        handled: true,
        label: "Fullscreen",
        detail: document.title,
        windowFullscreen: "toggle",
        mediaType,
        title: document.title,
      };
    }

    if (cmd.action === "volume_up" || cmd.action === "volume_down") {
      if (!el) return { handled: false };
      const step = (Number(cmd.step) || 8) / 100;
      const delta = cmd.action === "volume_up" ? step : -step;
      if (cmd.action === "volume_up" && el.muted) el.muted = false;
      el.volume = Math.max(0, Math.min(1, Number((el.volume + delta).toFixed(3))));
      return {
        handled: true,
        volumePercent: Math.round(el.volume * 100),
        muted: el.muted,
        mediaType,
        title: document.title,
      };
    }

    if (cmd.action === "mute") {
      if (!el) return { handled: false };
      el.muted = !el.muted;
      return {
        handled: true,
        muted: el.muted,
        label: el.muted ? "Muted" : "Unmuted",
        detail: document.title,
        mediaType,
        title: document.title,
      };
    }

    return { handled: false };
  }

  window.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && getState().pseudoFsContainer) {
      exitPseudoFullscreen();
      try {
        (globalThis.browser ?? globalThis.chrome).runtime.sendMessage({
          type: "exit_window_fullscreen",
        });
      } catch (_) {}
    }
  });

  window.__heyHandyHandle = handleCommand;
})();

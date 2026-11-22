/* Hey Handy MV3 background worker — maintains localhost WebSocket & routes to active tab. */
const ext = globalThis.browser ?? globalThis.chrome;
const DEFAULT_WS_URL = "ws://127.0.0.1:17421";

let socket = null;
let keepAliveTimer = null;
let reconnectTimer = null;
let lastWindowState = new Map();
let connectedState = false;

function detectBrowserName() {
  const ua = navigator.userAgent || "";
  if (ua.includes("Firefox")) return "Firefox / Zen";
  if (ua.includes("Edg/")) return "Edge";
  if (ua.includes("Brave")) return "Brave";
  if (ua.includes("Chrome")) return "Chromium / Chrome";
  return "Browser";
}

async function getWsUrl() {
  try {
    const data = await ext.storage.local.get({ wsUrl: DEFAULT_WS_URL });
    return data.wsUrl || DEFAULT_WS_URL;
  } catch (_) {
    return DEFAULT_WS_URL;
  }
}

async function getActiveTab() {
  try {
    const focused = await ext.tabs.query({ active: true, lastFocusedWindow: true });
    const candidate = focused.find((t) => t.id && !String(t.url || "").startsWith("devtools://"));
    if (candidate) return candidate;

    const normal = await ext.tabs.query({ active: true, windowType: "normal" });
    return normal[0] || null;
  } catch (_) {
    return null;
  }
}

async function runInAllFrames(tabId, cmd) {
  try {
    const results = await ext.scripting.executeScript({
      target: { tabId, allFrames: true },
      func: (payload) => (window.__heyHandyHandle ? window.__heyHandyHandle(payload) : { missing: true }),
      args: [cmd],
    });
    const needsInject = results.some((r) => r?.result?.missing);
    if (needsInject) {
      await ext.scripting.executeScript({
        target: { tabId, allFrames: true },
        files: ["content.js"],
      });
      return await ext.scripting.executeScript({
        target: { tabId, allFrames: true },
        func: (payload) => (window.__heyHandyHandle ? window.__heyHandyHandle(payload) : { handled: false }),
        args: [cmd],
      });
    }
    return results;
  } catch (_) {
    return [];
  }
}

async function runInFrame(tabId, frameId, cmd) {
  try {
    const res = await ext.scripting.executeScript({
      target: { tabId, frameIds: [frameId] },
      func: (payload) => (window.__heyHandyHandle ? window.__heyHandyHandle(payload) : { handled: false }),
      args: [cmd],
    });
    return res?.[0]?.result || { handled: false };
  } catch (_) {
    return { handled: false };
  }
}

async function toggleWindowFullscreen(tab, mode) {
  if (!tab || typeof tab.windowId !== "number") return;
  try {
    const win = await ext.windows.get(tab.windowId);
    if (mode === "enter") {
      if (win.state !== "fullscreen") {
        lastWindowState.set(tab.windowId, win.state || "normal");
        await ext.windows.update(tab.windowId, { state: "fullscreen" });
      }
    } else if (mode === "restore") {
      if (win.state === "fullscreen") {
        const prev = lastWindowState.get(tab.windowId) || "normal";
        await ext.windows.update(tab.windowId, { state: prev === "fullscreen" ? "normal" : prev });
      }
    } else if (mode === "toggle") {
      if (win.state === "fullscreen") {
        const prev = lastWindowState.get(tab.windowId) || "normal";
        await ext.windows.update(tab.windowId, { state: prev === "fullscreen" ? "normal" : prev });
      } else {
        lastWindowState.set(tab.windowId, win.state || "normal");
        await ext.windows.update(tab.windowId, { state: "fullscreen" });
      }
    }
  } catch (_) {}
}

async function probeActiveTab() {
  const tab = await getActiveTab();
  if (!tab || !tab.id) {
    return { tab: null, frameId: 0, mediaType: "", title: "" };
  }
  const results = await runInAllFrames(tab.id, { action: "probe" });
  let bestFrame = 0;
  let bestScore = -1;
  let bestMediaType = "";
  for (const item of results) {
    const r = item?.result;
    if (r && typeof r.score === "number" && r.score > bestScore) {
      bestScore = r.score;
      bestFrame = item.frameId ?? 0;
      bestMediaType = r.mediaType || "";
    }
  }
  return {
    tab,
    frameId: bestFrame,
    mediaType: bestMediaType,
    title: tab.title || "",
  };
}

async function executeMediaCommand(cmd) {
  const tab = await getActiveTab();
  if (!tab || !tab.id) {
    return { handled: false, error: "No active tab" };
  }

  const results = await runInAllFrames(tab.id, { action: "probe" });
  let bestFrame = 0;
  let bestScore = -1;
  for (const item of results) {
    const r = item?.result;
    if (r && typeof r.score === "number" && r.score > bestScore) {
      bestScore = r.score;
      bestFrame = item.frameId ?? 0;
    }
  }

  const out = await runInFrame(tab.id, bestFrame, cmd);
  if (out && out.windowFullscreen) {
    await toggleWindowFullscreen(tab, out.windowFullscreen);
  }
  return {
    ...out,
    title: out?.title || tab.title || "",
  };
}

async function pushHudToActiveTab(msg) {
  const tab = await getActiveTab();
  if (!tab || !tab.id) return;
  await runInFrame(tab.id, 0, {
    action: "hud",
    state: msg.state,
    remaining: msg.remaining,
    alwaysOn: msg.alwaysOn,
    label: msg.label,
    detail: msg.detail,
  });
}

function sendJson(obj) {
  if (socket && socket.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify(obj));
  }
}

async function sendTabStatus() {
  const probe = await probeActiveTab();
  sendJson({
    type: "tab_status",
    browser: detectBrowserName(),
    title: probe.title,
    mediaType: probe.mediaType,
  });
}

function startKeepAlive() {
  stopKeepAlive();
  keepAliveTimer = setInterval(() => {
    sendJson({ type: "ping" });
  }, 20000);
}

function stopKeepAlive() {
  if (keepAliveTimer) {
    clearInterval(keepAliveTimer);
    keepAliveTimer = null;
  }
}

function scheduleReconnect() {
  if (reconnectTimer) return;
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null;
    connectWebSocket();
  }, 3000);
}

async function connectWebSocket() {
  if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)) {
    return;
  }
  const url = await getWsUrl();
  try {
    socket = new WebSocket(url);
  } catch (_) {
    connectedState = false;
    scheduleReconnect();
    return;
  }

  socket.onopen = async () => {
    connectedState = true;
    startKeepAlive();
    const probe = await probeActiveTab();
    sendJson({
      type: "hello",
      browser: detectBrowserName(),
      title: probe.title,
      mediaType: probe.mediaType,
    });
  };

  socket.onmessage = async (event) => {
    let msg;
    try {
      msg = JSON.parse(event.data);
    } catch (_) {
      return;
    }
    if (!msg || typeof msg !== "object") return;

    if (msg.type === "command") {
      const result = await executeMediaCommand(msg);
      sendJson({
        type: "command_result",
        id: msg.id,
        ...result,
      });
    } else if (msg.type === "hud") {
      await pushHudToActiveTab(msg);
    }
  };

  socket.onclose = () => {
    connectedState = false;
    stopKeepAlive();
    socket = null;
    scheduleReconnect();
  };

  socket.onerror = () => {
    try {
      socket?.close();
    } catch (_) {}
  };
}

ext.tabs.onActivated.addListener(() => {
  sendTabStatus();
});
ext.tabs.onUpdated.addListener((_tabId, info) => {
  if (info.status === "complete" || info.title) {
    sendTabStatus();
  }
});

ext.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg?.type === "popup_status") {
    probeActiveTab().then((probe) => {
      sendResponse({
        connected: connectedState,
        title: probe.title,
        mediaType: probe.mediaType,
      });
    });
    return true;
  }
  if (msg?.type === "popup_action") {
    executeMediaCommand({ action: msg.action, step: 8 }).then((res) => {
      sendResponse(res);
    });
    return true;
  }
  if (msg?.type === "reconnect") {
    connectWebSocket();
    sendResponse({ ok: true });
    return false;
  }
  if (msg?.type === "exit_window_fullscreen") {
    getActiveTab().then((tab) => {
      if (tab) toggleWindowFullscreen(tab, "restore");
    });
    return false;
  }
  return false;
});

ext.alarms.create("hh-keepalive", { periodInMinutes: 0.5 });
ext.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === "hh-keepalive") {
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      connectWebSocket();
    } else {
      sendJson({ type: "ping" });
    }
  }
});

connectWebSocket();

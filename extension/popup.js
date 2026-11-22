const ext = globalThis.browser ?? globalThis.chrome;

async function refresh() {
  try {
    const res = await ext.runtime.sendMessage({ type: "popup_status" });
    const dot = document.getElementById("dot");
    const status = document.getElementById("status");
    const tabTitle = document.getElementById("tabTitle");
    if (res?.connected) {
      dot.classList.add("ok");
      status.textContent = "Connected to Hey Handy app";
    } else {
      dot.classList.remove("ok");
      status.textContent = "Waiting for Hey Handy app (ws://127.0.0.1:17421)";
      ext.runtime.sendMessage({ type: "reconnect" }).catch(() => {});
    }
    const kind = res?.mediaType ? ` (${res.mediaType})` : "";
    tabTitle.textContent = (res?.title || "No active tab") + kind;
  } catch (_) {}
}

for (const btn of document.querySelectorAll("button[data-action]")) {
  btn.addEventListener("click", async () => {
    const action = btn.dataset.action;
    await ext.runtime.sendMessage({ type: "popup_action", action });
    refresh();
  });
}

refresh();

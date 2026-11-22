# Publishing Hey Handy Extensions to Public Browser Stores

Hey Handy uses one shared extension codebase in [`extension/`](../extension) and builds clean store-ready ZIP packages for every major browser using [`scripts/package_extensions.py`](../scripts/package_extensions.py):

```bash
uv run python scripts/package_extensions.py
```

This generates two store-ready ZIP archives in `dist/`:
1. `dist/hey-handy-chromium-edge-mv3.zip` → **Chrome Web Store**, **Microsoft Edge Add-ons**, Brave, Vivaldi, Opera, Arc
2. `dist/hey-handy-firefox-zen-mv3.zip` → **Firefox Add-ons (AMO)**, Firefox, Zen Browser, LibreWolf

---

## 1. Firefox / Zen Browser / LibreWolf (Mozilla Add-ons — Free)

1. Create a free developer account at [addons.mozilla.org/developers](https://addons.mozilla.org/developers/).
2. Click **Submit a New Add-on** → choose **On this site** (public listing) or **On your own** (signed `.xpi` you can host on GitHub Releases!).
3. Upload `dist/hey-handy-firefox-zen-mv3.zip` (already includes `"data_collection_permissions": { "required": ["none"] }` for Mozilla's MV3 linter).
4. Note for reviewers: upload the repository source archive or link `https://github.com/ahmedtarek26/hey-handy` (no build/minification step is used — all JS is plain readable source).

---

## 2. Microsoft Edge Add-ons (Free)

1. Register a free developer account in [Microsoft Partner Center (Edge)](https://partner.microsoft.com/dashboard/microsoftedge/).
2. Create a new item and upload `dist/hey-handy-chromium-edge-mv3.zip`.
3. Store graphic assets ready to upload:
   - Screenshot (`1280×800`): [`docs/store-screenshot-1280x800.png`](store-screenshot-1280x800.png)
   - Small Promo Tile (`440×280`): [`docs/store-promo-440x280.png`](store-promo-440x280.png)
   - Icon (`128×128`): [`extension/icons/icon128.png`](../extension/icons/icon128.png)
4. Privacy Policy URL: `https://github.com/ahmedtarek26/hey-handy/blob/main/PRIVACY.md`

---

## 3. Chrome Web Store (Chrome, Chromium, Brave, Opera, Vivaldi, Arc)

1. Register at the [Chrome Web Store Developer Dashboard](https://chrome.google.com/webstore/devconsole) ($5 one-time Google developer fee).
2. Click **New Item** and upload `dist/hey-handy-chromium-edge-mv3.zip`.
3. Privacy Policy URL: `https://github.com/ahmedtarek26/hey-handy/blob/main/PRIVACY.md`
4. Use these exact permission justifications in the **Privacy practices** tab:
   - **Single purpose:** *Controls media playback, fullscreen, and volume on the user's active browser tab via gestures detected by the local Hey Handy desktop companion app.*
   - **`tabs`:** *Reads only the active tab ID/title to target playback commands and show active tab status in the popup and desktop companion.*
   - **`scripting` + `<all_urls>`:** *Injects the local content script into the active tab when a user gesture is triggered so HTML5 `<video>` and `<audio>` elements (including iframes and Shadow DOM players) can pause, resume, toggle fullscreen, and adjust volume on any site.*
   - **`storage`:** *Stores the local WebSocket URL (`ws://127.0.0.1:17421`) in browser local storage.*
   - **`alarms`:** *Maintains periodic keepalive checks for the localhost WebSocket connection to the desktop app.*
   - **Remote code:** *No — all JavaScript is bundled directly inside the extension package.*

---

## 4. Safari (macOS)

On macOS with Xcode installed, convert the extension folder directly into a Safari Web Extension app:

```bash
xcrun safari-web-extension-converter extension/ --app-name "Hey Handy Safari"
```

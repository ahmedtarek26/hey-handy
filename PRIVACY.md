# Privacy Policy — Hey Handy Browser Companion

**Effective Date:** November 22, 2026

Hey Handy respects your privacy. All voice wake-word detection, webcam hand gesture recognition, and active-tab media control run **100% locally on your own device**.

## Data Collection & Transmission

- **No Personal Data Collected:** The Hey Handy browser extension does **not** collect, store, sell, or transmit your browsing history, page contents, video/audio titles, personal information, analytics, or telemetry to any external server or third party.
- **Localhost Communication Only:** The extension connects exclusively to the Hey Handy desktop application running on your own machine (`ws://127.0.0.1:17421`) to receive playback/volume/fullscreen commands and display the local on-screen HUD indicator.
- **Local Storage:** The extension only stores your optional custom localhost WebSocket URL locally using `chrome.storage.local` / `browser.storage.local`.

## Browser Permissions Justification

- `tabs`: Identify the currently active tab so playback/fullscreen commands apply only to the media you are watching or listening to.
- `scripting` & `<all_urls>`: Locate and control `<video>` and `<audio>` elements inside the active tab (including embedded player iframes) when you issue a hand gesture.
- `storage`: Persist your local desktop bridge port configuration.
- `alarms`: Keep the local WebSocket connection to the desktop app alive under Manifest V3 service worker lifecycle rules.

## Contact

Questions or issues can be filed at: https://github.com/ahmedtarek26/hey-handy/issues

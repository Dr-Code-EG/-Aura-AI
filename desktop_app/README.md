# Aura Desktop — Simple build

A click-to-run, cross-platform companion to the original Aura overlay,
built with **PyQt6 + QtWebEngine**. Two providers, no `.env` editing,
no `ai_providers.json` to hand-craft.

## Why this exists

The original Aura is a full-featured, Windows-only stealth overlay
(`main.py` + `window_manager.py`). Setting it up requires editing
`.env`, populating `ai_providers.json` with multiple keys, and running
`run.bat`. This simplified build is for users who just want:

> "I want a real desktop program. When I press a button while my exam
> is open, take a screenshot, send it to the AI, and show me the
> answer."

## Two providers

* **Gemini** — pastes a Gemini API key once in Settings; calls
  `generativelanguage.googleapis.com` directly with the screenshot as an
  inline image part.
* **ChatGPT (login)** — embeds `chatgpt.com` in a `QWebEngineView` with a
  *persistent* profile. Sign in to ChatGPT once; the cookies stick
  across restarts. Pressing **Answer** uploads the screenshot via the
  page's own file-input, types your question, clicks Send and reads the
  reply back from the DOM. **No API key required.**

## Run from source

```bash
pip install -r requirements-desktop.txt
python aura_desktop.py
```

Or on Windows just double-click `aura_desktop.bat` — it creates a venv,
installs the deps and launches the app.

## Build a real `.exe`

```bash
pip install pyinstaller
pyinstaller aura_desktop.spec
```

The bundle ends up at `dist/AuraDesktop/AuraDesktop.exe`.

## Files

| File                                     | Purpose |
|------------------------------------------|---------|
| `desktop_app/app.py`                     | Entry point; wires QApplication + global hotkey. |
| `desktop_app/overlay_window.py`          | Always-on-top floating UI with **Answer** / **ChatGPT** / **Settings** tabs. |
| `desktop_app/capture.py`                 | `mss`-backed cross-platform screen capture → PNG bytes. |
| `desktop_app/gemini_client.py`           | Minimal Gemini Vision client over `httpx`. |
| `desktop_app/chatgpt_browser.py`         | Embedded ChatGPT browser + JS bridge. |
| `desktop_app/resources/chatgpt_inject.js`| Page-side bridge: attach file → type → send → read response. |
| `desktop_app/hotkey.py`                  | Global hotkey listener (`pynput`). |
| `desktop_app/settings_store.py`          | `~/.aura_desktop/config.json` for keys + UI prefs. |
| `desktop_app/settings_dialog.py`         | One-screen settings UI. |
| `desktop_app/worker.py`                  | `QThread` wrapper for Gemini calls. |

## Persistent state

Everything user-specific lives in `~/.aura_desktop/`:

* `config.json` — Gemini key, default model, hotkey, default question.
* `browser_profile/` — QtWebEngine cookies / localStorage that keep
  ChatGPT logged in.

Delete that folder to reset.

## Hotkey

Default global hotkey is `Ctrl+Shift+A`. While *any* application has
focus — including the exam window — pressing it triggers the same flow
as the **Answer** button: hide → screenshot → send to provider → show
the reply in the floating panel.

## Limitations

* The ChatGPT bridge depends on the current DOM structure of
  `chatgpt.com`. If OpenAI changes class names or the upload control,
  selectors in `resources/chatgpt_inject.js` need updating.
* `pynput` global hotkeys on macOS need accessibility permission.
* Linux: install system Qt + xcb + libxkbcommon packages if PyQt6 wheels
  fail to launch.

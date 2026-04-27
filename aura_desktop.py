"""Top-level launcher for Aura Desktop — the simplified PyQt6 build.

Run with:
    python aura_desktop.py

This is a separate, lightweight entry point from ``main.py`` (which still
launches the full pywebview-based stealth overlay). The desktop build
exposes a click-to-run UI with two providers: Gemini (via API key) and
ChatGPT (via an embedded logged-in browser).
"""

from desktop_app.app import main

if __name__ == "__main__":
    raise SystemExit(main())

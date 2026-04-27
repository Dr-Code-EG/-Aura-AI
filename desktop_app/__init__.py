"""Aura Desktop — a real, click-to-run desktop application.

A simplified PyQt6-based companion to the original Aura overlay.

The user clicks one button (or presses a global hotkey), the app captures
the current screen and asks the configured AI provider — Gemini via API
key or ChatGPT via an embedded logged-in browser session — to answer the
question that's on screen. The answer is shown in a floating panel that
stays on top of the exam window.
"""

__version__ = "0.1.0"

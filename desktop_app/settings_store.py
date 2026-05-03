"""Persistent JSON settings stored in the user's home directory.

Everything configurable from the in-app settings dialog is persisted
into a single ``~/.drcode/config.json`` file so a regular user never
has to touch a text editor. The embedded ChatGPT browser profile —
cookies, local storage, logged-in session — lives alongside it.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any


CONFIG_DIR = Path(os.path.expanduser("~")) / ".drcode"
CONFIG_FILE = CONFIG_DIR / "config.json"
BROWSER_PROFILE_DIR = CONFIG_DIR / "browser_profile"


@dataclass
class Settings:
    """User-visible settings."""

    hotkey: str = "ctrl+shift+a"
    extra_question: str = (
        "You are looking at a screenshot of an exam question. Answer the "
        "question that is visible on the screen. Be concise but show the "
        "reasoning briefly."
    )
    auto_hide_window: bool = True
    capture_delay_ms: int = 250

    @classmethod
    def load(cls) -> "Settings":
        if not CONFIG_FILE.exists():
            return cls()
        try:
            data: dict[str, Any] = json.loads(CONFIG_FILE.read_text("utf-8"))
        except (OSError, json.JSONDecodeError):
            return cls()
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        clean = {k: v for k, v in data.items() if k in known}
        return cls(**clean)

    def save(self) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(
            json.dumps(asdict(self), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )


def ensure_browser_profile_dir() -> Path:
    BROWSER_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    return BROWSER_PROFILE_DIR

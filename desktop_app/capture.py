"""Cross-platform screen capture utilities.

We prefer ``mss`` because it is fast and works on Windows, macOS and Linux
without external dependencies. ``Pillow`` is used to encode the captured
frame as PNG bytes — the form most vision models expect.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

try:
    import mss
    import mss.tools
except ImportError as exc:  # pragma: no cover - import-time guard
    raise ImportError(
        "mss is required for screen capture. Install with `pip install mss`."
    ) from exc

from PIL import Image


@dataclass
class Screenshot:
    """A captured screenshot with both PIL and PNG-bytes representations."""

    image: Image.Image
    png_bytes: bytes
    width: int
    height: int

    @property
    def mime_type(self) -> str:
        return "image/png"


def capture_primary_screen() -> Screenshot:
    """Capture the primary monitor and return it as PNG bytes."""
    with mss.mss() as sct:
        # monitors[0] is the union of all monitors; monitors[1] is primary.
        target = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
        raw = sct.grab(target)
        image = Image.frombytes("RGB", raw.size, raw.rgb)

    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    png_bytes = buffer.getvalue()
    return Screenshot(
        image=image,
        png_bytes=png_bytes,
        width=image.width,
        height=image.height,
    )


def capture_all_screens() -> Screenshot:
    """Capture all monitors stitched together (the virtual desktop)."""
    with mss.mss() as sct:
        target = sct.monitors[0]
        raw = sct.grab(target)
        image = Image.frombytes("RGB", raw.size, raw.rgb)

    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return Screenshot(
        image=image,
        png_bytes=buffer.getvalue(),
        width=image.width,
        height=image.height,
    )

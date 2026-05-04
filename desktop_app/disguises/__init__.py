"""Visual disguises the floating window can wear.

Each disguise is a ``QWidget`` that emits a ``clicked`` signal when
the user single-clicks anywhere on it. The ``OverlayWindow`` swaps
between disguises based on the ``disguise`` setting; everything else
(screenshot capture, ChatGPT bridge, answer routing, right-click
menu) stays the same.

The registry below is the single source of truth — adding a new
disguise means appending a new entry here and shipping its widget
class. ``label`` is what the user sees in the Calibrate dialog;
``answer_target`` tells the overlay where to print the answer:

  ``"title"`` — the answer replaces the window's title bar text
                (default for clock-shaped disguises).
  ``"tooltip"``— the answer is set as a hover tooltip; the disguise
                stays visually unchanged.
  ``"label"`` — the disguise itself has an inline text label that
                gets repurposed (e.g. the digital clock's digits get
                briefly replaced by the answer).

Each widget is responsible for honouring ``set_answer(text)`` so the
overlay window can plumb the answer in regardless of which disguise
is active.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from PyQt6.QtWidgets import QWidget


@dataclass(frozen=True)
class DisguiseSpec:
    key: str
    label: str
    factory: Callable[[QWidget | None], QWidget]
    answer_target: str  # "title" | "tooltip" | "label"


def _build_registry() -> list[DisguiseSpec]:
    # Imports are local to avoid pulling Qt into the module just to
    # describe the registry shape.
    from .analog_clock import AnalogClockDisguise
    from .battery import BatteryDisguise
    from .calendar import CalendarDisguise
    from .cpu_bar import CpuBarDisguise
    from .digital_clock import DigitalClockDisguise
    from .status_bar import StatusBarDisguise
    from .sticky_note import StickyNoteDisguise
    from .volume_mixer import VolumeMixerDisguise
    from .weather import WeatherDisguise
    from .wifi import WifiDisguise

    return [
        DisguiseSpec(
            key="analog_clock",
            label="Analog clock",
            factory=AnalogClockDisguise,
            answer_target="title",
        ),
        DisguiseSpec(
            key="digital_clock",
            label="Digital clock",
            factory=DigitalClockDisguise,
            answer_target="label",
        ),
        DisguiseSpec(
            key="status_bar",
            label="Horizontal status bar",
            factory=StatusBarDisguise,
            answer_target="label",
        ),
        DisguiseSpec(
            key="battery",
            label="Battery indicator",
            factory=BatteryDisguise,
            answer_target="tooltip",
        ),
        DisguiseSpec(
            key="wifi",
            label="Wi-Fi indicator",
            factory=WifiDisguise,
            answer_target="tooltip",
        ),
        DisguiseSpec(
            key="volume_mixer",
            label="Volume mixer",
            factory=VolumeMixerDisguise,
            answer_target="tooltip",
        ),
        DisguiseSpec(
            key="weather",
            label="Weather widget",
            factory=WeatherDisguise,
            answer_target="label",
        ),
        DisguiseSpec(
            key="calendar",
            label="Mini calendar",
            factory=CalendarDisguise,
            answer_target="label",
        ),
        DisguiseSpec(
            key="sticky_note",
            label="Sticky note",
            factory=StickyNoteDisguise,
            answer_target="label",
        ),
        DisguiseSpec(
            key="cpu_bar",
            label="CPU usage bar",
            factory=CpuBarDisguise,
            answer_target="tooltip",
        ),
    ]


_REGISTRY: list[DisguiseSpec] | None = None


def all_disguises() -> list[DisguiseSpec]:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = _build_registry()
    return _REGISTRY


def find(key: str) -> DisguiseSpec:
    for d in all_disguises():
        if d.key == key:
            return d
    return all_disguises()[0]

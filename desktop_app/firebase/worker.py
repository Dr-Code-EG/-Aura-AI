"""Run blocking :class:`ActivationService` calls off the Qt main thread.

The Firebase REST client is built on synchronous ``urllib.request``
calls, each with a 10-second timeout. Calling them on the Qt event
thread freezes the UI for as long as the network round-trip takes —
on Windows the OS even shows a "Not Responding" overlay if it lasts
more than ~5 seconds.

This module provides a tiny ``QThread``-based worker that executes a
single ``ActivationService`` method on a background thread and emits
its return value back to the main thread via a ``pyqtSignal``.

Usage::

    worker = ActivationWorker(service, "heartbeat")
    worker.finished.connect(on_result)   # on_result runs on main thread
    worker.start()
"""

from __future__ import annotations

from typing import Any, Callable

from PyQt6.QtCore import QThread, pyqtSignal


class ActivationWorker(QThread):
    """One-shot ``QThread`` that runs ``service.<method>(*args, **kwargs)``."""

    finished_with_result = pyqtSignal(str)
    failed = pyqtSignal(Exception)

    def __init__(
        self,
        callable_: Callable[..., str],
        *args: Any,
        parent: Any = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(parent)
        self._callable = callable_
        self._args = args
        self._kwargs = kwargs

    def run(self) -> None:  # type: ignore[override]
        try:
            result = self._callable(*self._args, **self._kwargs)
        except Exception as exc:  # pragma: no cover — surfaced to UI
            self.failed.emit(exc)
            return
        self.finished_with_result.emit(str(result))

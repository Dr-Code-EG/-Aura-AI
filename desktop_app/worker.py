"""Background worker that runs Gemini calls off the GUI thread."""

from __future__ import annotations

from PyQt6.QtCore import QObject, QThread, pyqtSignal

from .gemini_client import GeminiClient


class GeminiWorker(QObject):
    """Run a single Gemini Vision call and emit the result back to the UI."""

    finished = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(
        self,
        api_key: str,
        model: str,
        png_bytes: bytes,
        question: str,
        system_instruction: str = "",
    ) -> None:
        super().__init__()
        self._api_key = api_key
        self._model = model
        self._png = png_bytes
        self._question = question
        self._system = system_instruction

    def run(self) -> None:
        try:
            with GeminiClient(self._api_key, self._model) as client:
                result = client.answer_about_image(
                    self._png,
                    self._question,
                    system_instruction=self._system or None,
                )
            self.finished.emit(result.text)
        except Exception as exc:  # pragma: no cover - surfaced to UI
            self.failed.emit(str(exc))


def run_gemini_async(
    api_key: str,
    model: str,
    png_bytes: bytes,
    question: str,
    on_done,
    on_error,
    system_instruction: str = "",
) -> tuple[QThread, GeminiWorker]:
    """Spin up a QThread, run Gemini, and route results back to the caller."""
    thread = QThread()
    worker = GeminiWorker(
        api_key=api_key,
        model=model,
        png_bytes=png_bytes,
        question=question,
        system_instruction=system_instruction,
    )
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.finished.connect(on_done)
    worker.failed.connect(on_error)
    worker.finished.connect(thread.quit)
    worker.failed.connect(thread.quit)
    thread.finished.connect(worker.deleteLater)
    thread.finished.connect(thread.deleteLater)
    thread.start()
    return thread, worker

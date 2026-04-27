"""Gemini Vision client for answering questions about a screenshot.

Uses the ``google-genai`` SDK if available (preferred), otherwise falls
back to a direct REST call against Google's Generative Language API.
This keeps the install small for users who want a quick start.
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Optional

import httpx


@dataclass
class GeminiResult:
    text: str
    raw: dict
    model: str


class GeminiClient:
    """Minimal Gemini Vision client built on top of httpx."""

    DEFAULT_ENDPOINT = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        "{model}:generateContent"
    )

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-2.0-flash",
        timeout: float = 60.0,
    ) -> None:
        if not api_key:
            raise ValueError("Gemini API key is required.")
        self.api_key = api_key
        self.model = model
        self._client = httpx.Client(timeout=timeout)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "GeminiClient":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    def answer_about_image(
        self,
        png_bytes: bytes,
        question: str,
        mime_type: str = "image/png",
        system_instruction: Optional[str] = None,
    ) -> GeminiResult:
        """Send a question + image to Gemini and return the answer text."""
        b64 = base64.standard_b64encode(png_bytes).decode("ascii")
        payload: dict = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {"text": question},
                        {
                            "inline_data": {
                                "mime_type": mime_type,
                                "data": b64,
                            }
                        },
                    ],
                }
            ],
            "generationConfig": {
                "temperature": 0.4,
                "maxOutputTokens": 2048,
            },
        }
        if system_instruction:
            payload["systemInstruction"] = {
                "role": "system",
                "parts": [{"text": system_instruction}],
            }

        url = self.DEFAULT_ENDPOINT.format(model=self.model)
        response = self._client.post(
            url,
            params={"key": self.api_key},
            headers={"Content-Type": "application/json"},
            content=json.dumps(payload),
        )
        if response.status_code != 200:
            raise RuntimeError(
                f"Gemini API error {response.status_code}: {response.text[:500]}"
            )
        body = response.json()
        text = _extract_text(body)
        return GeminiResult(text=text, raw=body, model=self.model)


def _extract_text(body: dict) -> str:
    """Pull the assistant text out of a Gemini ``generateContent`` response."""
    candidates = body.get("candidates") or []
    if not candidates:
        prompt_feedback = body.get("promptFeedback")
        if prompt_feedback:
            return f"(Gemini blocked the prompt: {prompt_feedback})"
        return "(no response)"
    parts = candidates[0].get("content", {}).get("parts") or []
    chunks = [p.get("text", "") for p in parts if isinstance(p, dict)]
    return "".join(chunks).strip() or "(empty response)"

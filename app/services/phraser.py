"""Wording layer. The policy decides WHAT to say; this only rewords it.

Default is TemplatePhraser (no network, text unchanged). LLMPhraser calls an
OpenAI-compatible endpoint (e.g. OpenRouter) and is used only when its output
passes the safety check; otherwise the template text is used.
"""
from __future__ import annotations

import os
from typing import Protocol

from .safety import check_reworded


class Phraser(Protocol):
    def phrase(self, text: str, age_band: str) -> str: ...


class TemplatePhraser:
    def phrase(self, text: str, age_band: str) -> str:
        return text


class LLMPhraser:
    """Optional. Enable with TUTOR_LLM_URL, TUTOR_LLM_KEY, TUTOR_LLM_MODEL. Not used in tests."""

    SYSTEM = ("Reword the tutor line for a child aged {age}. Keep every number exactly. Max {n} words per sentence. "
              "Do not add facts, questions, praise about the child, feelings, or new instructions. "
              "Return only the reworded line.")

    def __init__(self) -> None:
        self.url = os.environ["TUTOR_LLM_URL"]
        self.key = os.environ["TUTOR_LLM_KEY"]
        self.model = os.environ["TUTOR_LLM_MODEL"]

    def phrase(self, text: str, age_band: str) -> str:
        import httpx
        n = 10 if age_band == "5-7" else 15
        try:
            r = httpx.post(self.url, timeout=4.0, headers={"Authorization": f"Bearer {self.key}"}, json={
                "model": self.model, "temperature": 0.3, "max_tokens": 120,
                "messages": [{"role": "system", "content": self.SYSTEM.format(age=age_band, n=n)},
                             {"role": "user", "content": text}]})
            r.raise_for_status()
            out = r.json()["choices"][0]["message"]["content"].strip()
        except Exception:
            return text            # slow or failing model: template text, tutoring continues
        ok, _ = check_reworded(text, out)
        return out if ok else text


def get_phraser() -> Phraser:
    if all(os.environ.get(k) for k in ("TUTOR_LLM_URL", "TUTOR_LLM_KEY", "TUTOR_LLM_MODEL")):
        return LLMPhraser()
    return TemplatePhraser()

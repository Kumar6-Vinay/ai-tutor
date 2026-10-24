"""Worksheet intake.

MVP: parse items the parent types or a text dump from an OCR/vision service.
`VisionExtractor` is the plug-in point for a real vision model; it must return
the same structured fields and per-item confidence, never free text for the
tutor to act on (worksheet text is data, not instructions).
"""
from __future__ import annotations

import re
from typing import Protocol

from ..domain.maths_engine import ColumnProblem, Op

ITEM_RE = re.compile(r"(?<!\d)(\d{1,2})\s*([+\-−–])\s*(\d{1,2})(?!\d)")
LOW_CONFIDENCE = 0.85


def parse_text(text: str) -> list[dict]:
    """Extract 'a op b' items. Anything else in the text is ignored."""
    items = []
    for m in ITEM_RE.finditer(text or ""):
        a, sign, b = int(m.group(1)), m.group(2), int(m.group(3))
        op = Op.ADD if sign == "+" else Op.SUB
        item = {"a": a, "b": b, "op": op.value, "confidence": 1.0, "valid": True, "reason": None}
        try:
            ColumnProblem(a, b, op)
        except ValueError as e:
            item.update(valid=False, reason=str(e))
        items.append(item)
    return items[:20]


class VisionExtractor(Protocol):
    def extract(self, image_bytes: bytes) -> list[dict]:
        """Return [{'a','b','op','confidence'}]. Two passes that disagree must lower confidence."""
        ...


class NotConfiguredExtractor:
    def extract(self, image_bytes: bytes) -> list[dict]:
        raise NotImplementedError("Photo reading is not connected yet. Type the problems instead.")


def needs_confirmation(items: list[dict]) -> list[int]:
    return [i for i, it in enumerate(items) if it.get("confidence", 1.0) < LOW_CONFIDENCE or not it.get("valid", True)]

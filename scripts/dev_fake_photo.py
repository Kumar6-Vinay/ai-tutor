"""Local testing only: run the app with a fake photo reader (no API key, no network).

    uvicorn scripts.dev_fake_photo:app --reload

Any image you upload "reads" as the same mixed sheet, with one problem marked low-confidence
and two exercises that are not sums, so you can see the whole parent flow.
"""
from app.main import app  # noqa: F401
import app.main as main


class FakeVision:
    configured = True

    def extract(self, image_bytes: bytes):
        return [
            {"a": 52, "b": 27, "op": "-", "confidence": 0.97},
            {"a": 23, "b": 14, "op": "+", "confidence": 0.95},
            {"a": 63, "b": 38, "op": "-", "confidence": 0.55},   # shows the "not sure" flag
            {"a": 38, "b": 47, "op": "+", "confidence": 0.96},
            {"a": 71, "b": 46, "op": "-", "confidence": 0.94},
        ], 2


main.vision = FakeVision()

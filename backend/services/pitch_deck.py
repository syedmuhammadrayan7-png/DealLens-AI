from __future__ import annotations

from io import BytesIO

from backend.config import Settings


class PitchDeckError(ValueError):
    pass


def extract_pitch_deck(file_name: str, content_type: str | None, content: bytes, settings: Settings) -> str:
    if content_type not in {"application/pdf", "application/x-pdf"} and not file_name.lower().endswith(".pdf"):
        raise PitchDeckError("Pitch deck must be a PDF file.")
    if not content:
        raise PitchDeckError("Pitch deck file is empty.")
    if len(content) > settings.max_pitch_deck_mb * 1024 * 1024:
        raise PitchDeckError(f"Pitch deck exceeds the {settings.max_pitch_deck_mb} MB limit.")
    try:
        from pypdf import PdfReader
        reader = PdfReader(BytesIO(content))
        text = "\n".join((page.extract_text() or "") for page in reader.pages).strip()
    except Exception as exc:
        raise PitchDeckError("Unable to read the PDF pitch deck.") from exc
    return text[:50_000]

"""Tesseract confidence extraction for OCR quality assessment."""

from __future__ import annotations

import io
from pathlib import Path

import fitz
import pytesseract
from PIL import Image

from scholardoc_ocr.types import SignalResult


def extract_page_confidence(
    pdf_path: Path, page_num: int, langs: str = "eng+fra"
) -> list[dict]:
    """Extract per-word confidence scores from a PDF page via Tesseract.

    Args:
        pdf_path: Path to the PDF file.
        page_num: Zero-based page index.
        langs: Tesseract language string (e.g. "eng+fra").

    Returns:
        List of {"text": str, "conf": int} dicts for words with valid confidence.
    """
    with fitz.open(pdf_path) as doc:
        page = doc[page_num]
        pix = page.get_pixmap(dpi=300)
        img = Image.open(io.BytesIO(pix.tobytes("png")))

    data = pytesseract.image_to_data(img, lang=langs, output_type=pytesseract.Output.DICT)

    results = []
    for text, conf in zip(data["text"], data["conf"]):
        conf = int(conf)
        if text.strip() and conf > 0:
            results.append({"text": text.strip(), "conf": conf})

    return results


class ConfidenceSignal:
    """Scores OCR confidence from Tesseract word-level data."""

    def __init__(self, langs: str = "eng+fra"):
        self.langs = langs

    def score_from_data(self, confidence_data: list[dict]) -> SignalResult:
        """Compute a 0-1 confidence score from word-level data.

        Args:
            confidence_data: List of {"text": str, "conf": int} dicts.

        Returns:
            SignalResult with weighted mean confidence normalized to 0-1.
        """
        valid = [w for w in confidence_data if w.get("conf", -1) > 0 and w.get("text", "").strip()]

        if not valid:
            return SignalResult(
                name="confidence",
                score=0.5,
                passed=True,
                details={"word_count": 0, "reason": "no_data"},
            )

        weights = [max(1, len(w["text"])) for w in valid]
        total_weight = sum(weights)
        weighted_sum = sum(w["conf"] * wt for w, wt in zip(valid, weights))
        mean_conf = weighted_sum / total_weight
        normalized = mean_conf / 100.0

        confs = [w["conf"] for w in valid]
        low_conf_words = [w["text"] for w in valid if w["conf"] < 30]

        return SignalResult(
            name="confidence",
            score=normalized,
            passed=normalized >= 0.5,
            details={
                "word_count": len(valid),
                "mean_conf": round(mean_conf, 2),
                "min_conf": min(confs),
                "low_conf_words": low_conf_words[:20],
            },
        )

    def score_from_pdf(self, pdf_path: Path, page_num: int) -> SignalResult:
        """Extract confidence from a PDF page and score it.

        Args:
            pdf_path: Path to the PDF file.
            page_num: Zero-based page index.

        Returns:
            SignalResult with confidence score.
        """
        data = extract_page_confidence(pdf_path, page_num, self.langs)
        return self.score_from_data(data)

"""Recoverability scoring and confidence estimation.

Carving cannot guarantee recovery, so every candidate file is given a realistic
confidence (High/Medium/Low) and a recoverability grade
(Excellent/Good/Average/Poor/Unknown) based on observable evidence.
"""
from __future__ import annotations

CONFIDENCE_HIGH = "High"
CONFIDENCE_MEDIUM = "Medium"
CONFIDENCE_LOW = "Low"

REC_EXCELLENT = "Excellent"
REC_GOOD = "Good"
REC_AVERAGE = "Average"
REC_POOR = "Poor"
REC_UNKNOWN = "Unknown"


def score_carved(
    *,
    footer_found: bool,
    validated: bool,
    size: int,
    min_size: int,
    max_size: int,
    in_bad_range: bool,
) -> tuple[str, str]:
    """Return ``(confidence, recoverability)`` for a carved file."""
    points = 0
    if footer_found:
        points += 2
    if validated:
        points += 2
    if min_size <= size <= max_size:
        points += 1
    if size < min_size:
        points -= 1
    if in_bad_range:
        points -= 2

    if points >= 4:
        confidence = CONFIDENCE_HIGH
    elif points >= 2:
        confidence = CONFIDENCE_MEDIUM
    else:
        confidence = CONFIDENCE_LOW

    if in_bad_range:
        recoverability = REC_POOR
    elif footer_found and validated:
        recoverability = REC_EXCELLENT
    elif footer_found or validated:
        recoverability = REC_GOOD
    elif min_size <= size <= max_size:
        recoverability = REC_AVERAGE
    else:
        recoverability = REC_UNKNOWN
    return confidence, recoverability


def score_metadata(*, header_valid: bool, overwritten: bool) -> tuple[str, str]:
    """Scoring for metadata-based (quick scan) results."""
    if overwritten:
        return CONFIDENCE_LOW, REC_POOR
    if header_valid:
        return CONFIDENCE_HIGH, REC_GOOD
    return CONFIDENCE_MEDIUM, REC_AVERAGE

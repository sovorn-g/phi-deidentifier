"""Hybrid detection pipeline: rules + NER + optional LLM, merged deterministically.

Contracts: CONTRACTS.md §8.
"""

from __future__ import annotations

import logging
import re

from phi.config import get_settings
from phi.detect.llm import detect_llm
from phi.detect.ner import detect_ner
from phi.detect.rules import detect_rules
from phi.models import DeidConfig, DetectionResult, EntityType, PHISpan

log = logging.getLogger(__name__)

_LAYER_PRECEDENCE = {"rule": 3, "ner": 2, "llm": 1}

# When two same-layer spans of different types have identical length, prefer the
# more specific structured identifier over a generic phone/date match.
_TYPE_PRIORITY = {
    EntityType.NHI: 10,
    EntityType.MEDICARE: 10,
    EntityType.IHI: 10,
    EntityType.MRN: 9,
    EntityType.ID: 8,
    EntityType.EMAIL: 7,
    EntityType.URL: 7,
    EntityType.IP: 7,
    EntityType.PHONE: 6,
    EntityType.DATE: 5,
    EntityType.POSTCODE: 4,
    EntityType.AGE: 3,
    EntityType.LOCATION: 2,
    EntityType.ORG: 2,
    EntityType.PERSON: 2,
}

# Patterns emitted by redaction strategies — never re-detect them (idempotency, §9).
_REDACTED_TOKEN_PATTERNS = [
    re.compile(r"\[REDACTED:[A-Z]+\]"),
    re.compile(r"\[[A-Z]+:[0-9a-f]{10}\]"),
]


def _precedence(span: PHISpan) -> int:
    return _LAYER_PRECEDENCE.get(span.source, 0)


def _already_redacted(text: str) -> list[tuple[int, int]]:
    """Return character ranges already occupied by redaction tokens."""
    ranges: list[tuple[int, int]] = []
    for pat in _REDACTED_TOKEN_PATTERNS:
        for m in pat.finditer(text):
            ranges.append((m.start(), m.end()))
    return ranges


def _filter_redacted(spans: list[PHISpan], text: str) -> list[PHISpan]:
    """Drop predicted spans that sit inside existing redaction tokens."""
    redacted = _already_redacted(text)
    if not redacted:
        return spans

    def inside(span: PHISpan) -> bool:
        for s, e in redacted:
            if s <= span.start and span.end <= e:
                return True
        return False

    return [s for s in spans if not inside(s)]


def _merge_spans(spans: list[PHISpan]) -> list[PHISpan]:
    """Resolve overlaps deterministically per CONTRACTS §8.

    Returns non-overlapping spans sorted by start.
    """
    if not spans:
        return []

    # Sort by start; ties by precedence desc then score desc then end desc.
    sorted_spans = sorted(
        spans,
        key=lambda s: (s.start, -_precedence(s), -s.score, -s.end),
    )
    merged: list[PHISpan] = []

    for span in sorted_spans:
        if not merged:
            merged.append(span)
            continue

        last = merged[-1]
        if span.start >= last.end:
            merged.append(span)
            continue

        # Overlap exists.
        if _precedence(span) != _precedence(last):
            # Higher precedence wins entirely.
            if _precedence(span) > _precedence(last):
                merged[-1] = span
            # else keep last
            continue

        if span.type == last.type:
            # Same layer + same type -> union.
            union = last.merge(span)
            # Re-slice text from whichever span covers the union; caller
            # should not rely on text for merged spans.
            merged[-1] = union
        else:
            # Same layer + different type -> keep longer; tie -> higher score / type priority.
            if (span.end - span.start) > (last.end - last.start):
                merged[-1] = span
            elif (span.end - span.start) == (last.end - last.start):
                if _TYPE_PRIORITY.get(span.type, 0) > _TYPE_PRIORITY.get(last.type, 0):
                    merged[-1] = span
                elif span.score > last.score:
                    merged[-1] = span
            # else keep last

    return merged


def detect(text: str, config: DeidConfig | None = None) -> DetectionResult:
    """Run enabled detection layers and merge results."""
    config = config or DeidConfig()
    settings = get_settings()
    regions = config.regions or settings.regions_list

    spans: list[PHISpan] = []

    if config.use_rules:
        spans.extend(detect_rules(text, regions))
    if config.use_ner:
        spans.extend(detect_ner(text, regions, threshold=config.ner_threshold))
    if config.use_llm:
        spans.extend(detect_llm(text, spans, regions))

    spans = _filter_redacted(spans, text)
    merged = _merge_spans(spans)

    # Sanity: assert non-overlapping invariant.
    for i in range(len(merged) - 1):
        if merged[i].end > merged[i + 1].start:
            raise RuntimeError(f"overlap remained after merge: {merged[i]} vs {merged[i + 1]}")

    return DetectionResult(text=text, spans=merged)

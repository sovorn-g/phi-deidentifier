"""Tests for the detection pipeline and merge logic.

Contracts: CONTRACTS.md §8.
"""

from __future__ import annotations

from phi.detect.pipeline import _merge_spans
from phi.models import EntityType, PHISpan


def test_merge_rule_wins_over_ner() -> None:
    spans = [
        PHISpan(start=0, end=7, type=EntityType.NHI, text="ABC1235", source="rule", score=0.9),
        PHISpan(start=0, end=7, type=EntityType.PERSON, text="ABC1235", source="ner", score=0.85),
    ]
    merged = _merge_spans(spans)
    assert len(merged) == 1
    assert merged[0].source == "rule"
    assert merged[0].type == EntityType.NHI


def test_merge_same_layer_same_type_unions() -> None:
    spans = [
        PHISpan(start=0, end=5, type=EntityType.PERSON, text="Peter", source="ner", score=0.8),
        PHISpan(start=3, end=11, type=EntityType.PERSON, text="er Jensen", source="ner", score=0.8),
    ]
    merged = _merge_spans(spans)
    assert len(merged) == 1
    assert merged[0].start == 0
    assert merged[0].end == 11


def test_merge_non_overlapping_sorted() -> None:
    spans = [
        PHISpan(start=10, end=15, type=EntityType.DATE, text="01/01", source="rule"),
        PHISpan(start=0, end=5, type=EntityType.PERSON, text="Alice", source="ner"),
    ]
    merged = _merge_spans(spans)
    assert [m.start for m in merged] == [0, 10]
    for i in range(len(merged) - 1):
        assert merged[i].end <= merged[i + 1].start


def test_fixture_rich_detects_identifiers() -> None:
    from phi.detect.pipeline import detect
    from phi.models import DeidConfig

    text = "NHI: ABC1235\nDOB: 15/03/1980\nPhone: 021 123 4567\nMRN: 123456"
    result = detect(text, DeidConfig())
    types = {s.type for s in result.spans}
    assert EntityType.NHI in types
    assert EntityType.DATE in types
    assert EntityType.PHONE in types
    assert EntityType.MRN in types

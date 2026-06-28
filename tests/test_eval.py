"""Tests for span-level evaluation logic.

Contracts: CONTRACTS.md §12.
"""

from __future__ import annotations

from phi.eval.score import _match_greedy, score_note
from phi.models import EntityType, PHISpan


def test_iou_matching() -> None:
    gold = [PHISpan(start=0, end=10, type=EntityType.PERSON, text="John Smith", source="gold")]
    pred = [PHISpan(start=2, end=8, type=EntityType.PERSON, text="hn Smi", source="ner")]
    scores = score_note(gold, pred)
    assert scores[EntityType.PERSON].tp_relaxed == 1
    assert scores[EntityType.PERSON].tp_strict == 0


def test_type_mismatch_counts_as_miss() -> None:
    gold = [PHISpan(start=0, end=10, type=EntityType.PERSON, text="John Smith", source="gold")]
    pred = [PHISpan(start=0, end=10, type=EntityType.ORG, text="John Smith", source="ner")]
    scores = score_note(gold, pred)
    assert scores[EntityType.PERSON].tp_relaxed == 0
    assert scores[EntityType.ORG].tp_relaxed == 0


def test_one_pred_one_gold() -> None:
    gold = [
        PHISpan(start=0, end=5, type=EntityType.PERSON, text="Alice", source="gold"),
        PHISpan(start=10, end=15, type=EntityType.PERSON, text="Bob", source="gold"),
    ]
    pred = [PHISpan(start=0, end=5, type=EntityType.PERSON, text="Alice", source="ner")]
    scores = score_note(gold, pred)
    assert scores[EntityType.PERSON].tp_relaxed == 1
    assert scores[EntityType.PERSON].total_gold == 2
    assert scores[EntityType.PERSON].total_pred == 1


def test_greedy_one_to_one() -> None:
    gold = [
        PHISpan(start=0, end=5, type=EntityType.PERSON, text="John", source="gold"),
        PHISpan(start=6, end=10, type=EntityType.PERSON, text="Jane", source="gold"),
    ]
    pred = [
        PHISpan(start=0, end=7, type=EntityType.PERSON, text="John J", source="ner"),
    ]
    matched = _match_greedy(gold, pred, strict=False)
    assert matched == 1  # one predicted span can match only one gold span

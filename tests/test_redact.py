"""Tests for redaction strategies.

Contracts: CONTRACTS.md §9.
"""

from __future__ import annotations

import pytest

from phi.deidentify import deidentify
from phi.models import DeidConfig, DetectionResult, EntityType, PHISpan
from phi.redact.strategies import redact


def _simple_result(text: str) -> DetectionResult:
    return DetectionResult(
        text=text,
        spans=[
            PHISpan(start=6, end=16, type=EntityType.PERSON, text="Jane Smith"),
            PHISpan(start=23, end=33, type=EntityType.DATE, text="12/04/1980"),
        ],
    )


def test_mask_strategy() -> None:
    text = "Name: Jane Smith, DOB: 12/04/1980"
    result = _simple_result(text)
    out = redact(result, "mask")
    assert out == "Name: [REDACTED:PERSON], DOB: [REDACTED:DATE]"


def test_hash_strategy_requires_key() -> None:
    with pytest.raises(ValueError):
        redact(_simple_result("x"), "hash")


def test_hash_strategy_consistent() -> None:
    text = "Name: Jane Smith, DOB: 12/04/1980"
    result = _simple_result(text)
    out1 = redact(result, "hash", hash_key="secret")
    out2 = redact(result, "hash", hash_key="secret")
    assert out1 == out2
    assert "[PERSON:" in out1 and "[DATE:" in out1


def test_surrogate_strategy_consistency() -> None:
    text = "Name: Jane Smith, DOB: 12/04/1980"
    result = _simple_result(text)
    out1 = redact(result, "surrogate", hash_key="secret")
    out2 = redact(result, "surrogate", hash_key="secret")
    assert out1 == out2
    assert "Jane Smith" not in out1
    assert "12/04/1980" not in out1


def test_idempotency() -> None:
    text = "Name: Jane Smith, DOB: 12/04/1980"
    config = DeidConfig(strategy="mask")
    first = deidentify(text, config)
    second = deidentify(first.redacted_text, config)
    assert first.redacted_text == second.redacted_text

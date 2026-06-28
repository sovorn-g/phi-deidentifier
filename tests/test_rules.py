"""Unit tests for rule-based recognizers and checksums.

Contracts: CONTRACTS.md §5, §11.
"""

from __future__ import annotations

import pytest

from phi.detect.rules import (
    IhiRecognizer,
    MedicareRecognizer,
    NhiOldRecognizer,
    PhoneRecognizerPhi,
    ihi_valid,
    luhn_valid,
    medicare_valid,
    nhi_old_valid,
)
from phi.models import EntityType

# ---------------------------------------------------------------------------
# Worked vectors
# ---------------------------------------------------------------------------

def test_nhi_old_worked_vector() -> None:
    assert nhi_old_valid("ABC1235")  # CONTRACTS §5 worked example
    assert not nhi_old_valid("ABC1234")  # plan's invalid example


def test_medicare_worked_vector() -> None:
    # Base 31899770 -> check digit 2, IRN 1 => valid card 3189977021
    assert medicare_valid("3189977021")


def test_ihi_worked_vector() -> None:
    assert ihi_valid("8003607906279049")


# ---------------------------------------------------------------------------
# Luhn helper
# ---------------------------------------------------------------------------

def test_luhn_helper() -> None:
    assert luhn_valid("4532015112830366")
    assert not luhn_valid("4532015112830367")


# ---------------------------------------------------------------------------
# Presidio recognizers
# ---------------------------------------------------------------------------

def test_nhi_recognizer() -> None:
    rec = NhiOldRecognizer()
    text = "NHI ABC1235 is valid; ABC1234 is not."
    results = rec.analyze(text=text, entities=[EntityType.NHI.value])
    assert len(results) == 1
    assert text[results[0].start : results[0].end] == "ABC1235"


def test_medicare_recognizer() -> None:
    rec = MedicareRecognizer()
    text = "Medicare 3189977021 valid, 3189977012 invalid."
    results = rec.analyze(text=text, entities=[EntityType.MEDICARE.value])
    assert len(results) == 1
    assert text[results[0].start : results[0].end] == "3189977021"


def test_ihi_recognizer() -> None:
    rec = IhiRecognizer()
    text = "IHI 8003607906279049 valid."
    results = rec.analyze(text=text, entities=[EntityType.IHI.value])
    assert len(results) == 1


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Call 021 242 2679", "021 242 2679"),
        ("Call +64 21 242 2679", "+64 21 242 2679"),
        ("Call 0410 877 925", "0410 877 925"),
    ],
)
def test_phone_recognizer(text: str, expected: str) -> None:
    rec = PhoneRecognizerPhi(regions=["NZ", "AU"])
    results = rec.analyze(text=text, entities=[EntityType.PHONE.value])
    assert len(results) == 1
    assert text[results[0].start : results[0].end] == expected


# ---------------------------------------------------------------------------
# Fixture acceptance: sparse.txt must not validate the checksum look-alike
# ---------------------------------------------------------------------------

def test_sparse_fixture_rejects_look_alike() -> None:
    from phi.detect.rules import NhiOldRecognizer

    text = "Previous entry ABC1234 failed validation."
    rec = NhiOldRecognizer()
    results = rec.analyze(text=text, entities=[EntityType.NHI.value])
    assert len(results) == 0

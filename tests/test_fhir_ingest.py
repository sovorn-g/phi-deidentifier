"""Tests for synthetic FHIR Bundle ingestion."""

from __future__ import annotations

from pathlib import Path

from phi.deidentify import deidentify
from phi.ingest.fhir import extract_fhir_text, load_fhir_bundle
from phi.models import DeidConfig, EntityType

SAMPLE = Path("data/fhir/Stanley_Balistreri_08ce8462-f56a-4fd6-b986-ea75c5c6edb2.json")


def test_extract_fhir_text_normalizes_patient_and_clinical_sections() -> None:
    text = extract_fhir_text(load_fhir_bundle(SAMPLE), max_clinical_items=5)

    assert "Patient demographics" in text
    assert "Patient name: Mr. Stanley Balistreri" in text
    assert "Birth date: 1992-04-30" in text
    assert "Social Security Number: 999-48-4828" in text
    assert "Care team and facilities" in text
    assert "Clinical timeline" in text


def test_fhir_extracted_text_can_be_deidentified() -> None:
    text = extract_fhir_text(load_fhir_bundle(SAMPLE), max_clinical_items=5)
    result = deidentify(text, DeidConfig(strategy="mask", regions=["US", "NZ", "AU"]))
    types = {span.type for span in result.spans}

    assert EntityType.PERSON in types
    assert EntityType.DATE in types
    assert EntityType.ID in types
    assert "Stanley Balistreri" not in result.redacted_text
    assert "999-48-4828" not in result.redacted_text

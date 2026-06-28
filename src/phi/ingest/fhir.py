"""Extract note-like text from synthetic FHIR Bundles and de-identify it.

This adapter is intentionally small: it normalizes common FHIR resources into
plain text, then hands that text to the PHI de-identification pipeline.
"""

from __future__ import annotations

import argparse
import json
import re
from html import unescape
from pathlib import Path
from typing import Any

from phi.deidentify import deidentify
from phi.models import DeidConfig

JsonObject = dict[str, Any]


def load_fhir_bundle(path: Path) -> JsonObject:
    """Load a FHIR JSON Bundle from disk."""
    return json.loads(path.read_text(encoding="utf-8"))


def iter_resources(bundle: JsonObject, resource_type: str | None = None) -> list[JsonObject]:
    """Return resources from a FHIR Bundle, optionally filtered by type."""
    resources = [
        entry.get("resource", {})
        for entry in bundle.get("entry", [])
        if isinstance(entry.get("resource"), dict)
    ]
    if resource_type is None:
        return resources
    return [r for r in resources if r.get("resourceType") == resource_type]


def _coding_text(value: JsonObject | list[JsonObject] | None) -> str | None:
    if not value:
        return None
    if isinstance(value, list):
        for item in value:
            text = _coding_text(item)
            if text:
                return text
        return None
    if value.get("text"):
        return str(value["text"])
    for coding in value.get("coding", []):
        if coding.get("display"):
            return str(coding["display"])
    return None


def _human_name(name: JsonObject) -> str:
    parts: list[str] = []
    parts.extend(str(p) for p in name.get("prefix", []))
    parts.extend(str(g) for g in name.get("given", []))
    family = name.get("family")
    if family:
        parts.append(str(family))
    return " ".join(parts).strip()


def _address(address: JsonObject) -> str:
    parts: list[str] = []
    parts.extend(str(line) for line in address.get("line", []))
    for field in ("city", "state", "postalCode", "country"):
        if address.get(field):
            parts.append(str(address[field]))
    return ", ".join(parts)


def _identifier_label(identifier: JsonObject) -> str:
    label = _coding_text(identifier.get("type"))
    if label:
        return label
    system = str(identifier.get("system", "")).lower()
    if "ssn" in system:
        return "Social Security Number"
    if "passport" in system:
        return "Passport Number"
    if "synthea" in system:
        return "FHIR patient id"
    return "Identifier"


def _strip_html(value: str) -> str:
    without_tags = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", unescape(without_tags)).strip()


def _resource_label(resource: JsonObject) -> str | None:
    return (
        _coding_text(resource.get("code"))
        or _coding_text(resource.get("type"))
        or _coding_text(resource.get("reasonCode", [{}])[0] if resource.get("reasonCode") else None)
    )


def _patient_lines(patient: JsonObject) -> list[str]:
    lines: list[str] = []
    for name in patient.get("name", []):
        rendered = _human_name(name)
        if rendered:
            lines.append(f"Patient name: {rendered}")
    if patient.get("birthDate"):
        lines.append(f"Birth date: {patient['birthDate']}")
    if patient.get("gender"):
        lines.append(f"Gender: {patient['gender']}")
    for telecom in patient.get("telecom", []):
        system = telecom.get("system", "contact")
        if telecom.get("value"):
            lines.append(f"{str(system).title()}: {telecom['value']}")
    for address in patient.get("address", []):
        rendered = _address(address)
        if rendered:
            lines.append(f"Address: {rendered}")
    for identifier in patient.get("identifier", []):
        if identifier.get("value"):
            lines.append(f"{_identifier_label(identifier)}: {identifier['value']}")
    return lines


def _care_team_lines(orgs: list[JsonObject], practitioners: list[JsonObject]) -> list[str]:
    lines: list[str] = []
    for org in orgs:
        if org.get("name"):
            lines.append(f"Organization: {org['name']}")
        for address in org.get("address", [])[:1]:
            rendered = _address(address)
            if rendered:
                lines.append(f"Organization address: {rendered}")
    for practitioner in practitioners:
        for name in practitioner.get("name", [])[:1]:
            rendered = _human_name(name)
            if rendered:
                lines.append(f"Practitioner: {rendered}")
    return lines


_CLINICAL_TYPES = {
    "Encounter",
    "Condition",
    "Observation",
    "Procedure",
    "MedicationRequest",
    "DiagnosticReport",
    "CarePlan",
    "AllergyIntolerance",
    "Immunization",
}


def _resource_date(resource: JsonObject) -> str | None:
    date = (
        resource.get("effectiveDateTime")
        or resource.get("authoredOn")
        or resource.get("performedDateTime")
        or resource.get("recordedDate")
        or resource.get("date")
        or resource.get("period", {}).get("start")
    )
    return str(date)[:10] if date else None


def _clinical_timeline_lines(resources: list[JsonObject], max_items: int) -> list[str]:
    lines: list[str] = []
    for resource in resources:
        resource_type = resource.get("resourceType")
        if resource_type not in _CLINICAL_TYPES:
            continue
        label = _resource_label(resource)
        if not label:
            text = resource.get("text", {}).get("div")
            label = _strip_html(str(text)) if text else None
        if not label:
            continue
        prefix = f"{resource_type}"
        date = _resource_date(resource)
        if date:
            prefix += f" on {date}"
        lines.append(f"{prefix}: {label}")
        if len(lines) >= max_items:
            break
    return lines


def extract_fhir_text(bundle: JsonObject, max_clinical_items: int = 30) -> str:
    """Normalize a FHIR Bundle into readable text for the de-identifier."""
    lines: list[str] = []

    patients = iter_resources(bundle, "Patient")
    if patients:
        lines.append("Patient demographics")
        lines.extend(_patient_lines(patients[0]))

    care_team = _care_team_lines(
        iter_resources(bundle, "Organization")[:3],
        iter_resources(bundle, "Practitioner")[:3],
    )
    if care_team:
        lines.extend(["", "Care team and facilities", *care_team])

    clinical_lines = _clinical_timeline_lines(iter_resources(bundle), max_clinical_items)
    if clinical_lines:
        lines.extend(["", "Clinical timeline", *clinical_lines])

    return "\n".join(lines).strip() + "\n"


def deidentify_fhir_bundle(
    path: Path,
    config: DeidConfig | None = None,
    max_clinical_items: int = 30,
) -> tuple[str, str]:
    """Return extracted FHIR text and its redacted version."""
    text = extract_fhir_text(load_fhir_bundle(path), max_clinical_items=max_clinical_items)
    result = deidentify(text, config or DeidConfig(regions=["US", "NZ", "AU"]))
    return text, result.redacted_text


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract and de-identify text from a FHIR Bundle.")
    parser.add_argument("file", type=Path, help="Path to a FHIR Bundle JSON file.")
    parser.add_argument(
        "--strategy",
        choices=["mask", "hash", "surrogate"],
        default="mask",
        help="Redaction strategy (default: mask).",
    )
    parser.add_argument("--extract-only", action="store_true", help="Print extracted text without redaction.")
    parser.add_argument("--no-ner", action="store_true", help="Disable the NER layer.")
    parser.add_argument("--llm", action="store_true", help="Enable the optional LLM second pass.")
    parser.add_argument("--max-clinical-items", type=int, default=30)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    bundle = load_fhir_bundle(args.file)
    text = extract_fhir_text(bundle, max_clinical_items=args.max_clinical_items)
    if args.extract_only:
        print(text)
        return 0

    config = DeidConfig(
        strategy=args.strategy,  # type: ignore[arg-type]
        use_ner=not args.no_ner,
        use_llm=args.llm,
        regions=["US", "NZ", "AU"],
    )
    result = deidentify(text, config)
    print(result.redacted_text)
    if result.audit:
        print("\n--- Audit ---")
        for entry in result.audit:
            print(f"{entry.type.value}: {entry.count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

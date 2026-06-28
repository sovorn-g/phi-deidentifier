"""Core data model shared across detection, redaction, and evaluation.

Contracts: CONTRACTS.md §3, §4, §10, §11.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class EntityType(StrEnum):
    """HIPAA-18-aligned entity types used for gold labels and predictions."""

    # Names / orgs / places (NER-led)
    PERSON = "PERSON"
    LOCATION = "LOCATION"
    ORG = "ORG"

    # Structured identifiers (rule-led)
    DATE = "DATE"
    AGE = "AGE"
    PHONE = "PHONE"
    EMAIL = "EMAIL"
    URL = "URL"
    IP = "IP"
    MRN = "MRN"
    NHI = "NHI"
    MEDICARE = "MEDICARE"
    IHI = "IHI"
    POSTCODE = "POSTCODE"
    ID = "ID"


SourceType = Literal["rule", "ner", "llm", "gold"]
StrategyName = Literal["mask", "hash", "surrogate"]


class PHISpan(BaseModel):
    """A single PHI span in a note.

    Offsets are character-level, half-open ``[start, end)`` so that
    ``note[start:end] == text`` exactly.
    """

    start: int = Field(..., ge=0)
    end: int = Field(..., ge=0)
    type: EntityType
    text: str
    score: float = Field(default=1.0, ge=0.0, le=1.0)
    source: SourceType = "rule"
    recognizer: str | None = None

    @field_validator("end")
    @classmethod
    def _end_after_start(cls, v: int, info) -> int:
        if (info.data.get("start") or 0) > v:
            raise ValueError("end must be >= start")
        return v

    def overlaps(self, other: PHISpan) -> bool:
        """True if any character overlaps with ``other``."""
        return self.start < other.end and other.start < self.end

    def iou(self, other: PHISpan) -> float:
        """Intersection-over-union of the two spans (0..1)."""
        inter_start = max(self.start, other.start)
        inter_end = min(self.end, other.end)
        inter = max(0, inter_end - inter_start)
        if inter == 0:
            return 0.0
        union = max(self.end, other.end) - min(self.start, other.start)
        return inter / union

    def merge(self, other: PHISpan) -> PHISpan:
        """Return the union of two spans (same layer/type assumed)."""
        start = min(self.start, other.start)
        end = max(self.end, other.end)
        return PHISpan(
            start=start,
            end=end,
            type=self.type,
            text="",  # caller should re-slice if needed
            score=max(self.score, other.score),
            source=self.source,
            recognizer=self.recognizer or other.recognizer,
        )


class DetectionResult(BaseModel):
    """Output of a detection pipeline: original text + merged, sorted spans."""

    text: str
    spans: list[PHISpan]


class AuditEntry(BaseModel):
    """Privacy-safe audit entry: counts and types only, never the PHI value."""

    type: EntityType
    count: int


class DeidConfig(BaseModel):
    """Configuration for the public ``deidentify`` API."""

    strategy: StrategyName = "mask"
    use_rules: bool = True
    use_ner: bool = True
    use_llm: bool = False
    ner_threshold: float = Field(default=0.40, ge=0.0, le=1.0)
    regions: list[str] = Field(default_factory=lambda: ["NZ", "AU"])


class DeidResult(BaseModel):
    """Output of ``deidentify(text, config)``."""

    redacted_text: str
    spans: list[PHISpan]  # positions in the ORIGINAL text
    audit: list[AuditEntry]

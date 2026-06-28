"""Rule-based recognizers with verified checksums.

Contracts: CONTRACTS.md §5.
"""

from __future__ import annotations

import logging
import re

import phonenumbers
from dateparser import parse as dateparser_parse
from presidio_analyzer import (
    AnalyzerEngine,
    EntityRecognizer,
    Pattern,
    PatternRecognizer,
    RecognizerResult,
)
from presidio_analyzer.nlp_engine import NlpArtifacts

from phi.models import EntityType, PHISpan

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Checksum validators
# ---------------------------------------------------------------------------

def _alpha_index(c: str) -> int:
    alpha = "ABCDEFGHJKLMNPQRSTUVWXYZ"
    return alpha.index(c.upper()) + 1


def nhi_old_valid(text: str) -> bool:
    """Validate old-format NZ NHI ``LLLNNNC``."""
    alpha = "ABCDEFGHJKLMNPQRSTUVWXYZ"
    if len(text) != 7:
        return False
    letters, digits, check = text[:3], text[3:6], text[6]
    if any(c not in alpha for c in letters) or not digits.isdigit() or not check.isdigit():
        return False
    vals = [_alpha_index(c) for c in letters] + [int(d) for d in digits]
    weights = [7, 6, 5, 4, 3, 2]
    checksum = sum(v * w for v, w in zip(vals, weights, strict=False)) % 11
    if checksum == 0:
        return False
    expected = 11 - checksum
    if expected == 10:
        return False
    return int(check) == expected


def medicare_valid(text: str) -> bool:
    """Validate AU Medicare 10-digit number (base + check + IRN)."""
    digits_only = re.sub(r"\D", "", text)
    if len(digits_only) != 10:
        return False
    if digits_only[0] not in "23456":
        return False
    digits = [int(c) for c in digits_only]
    weights = [1, 3, 7, 9, 1, 3, 7, 9]
    return digits[8] == sum(d * w for d, w in zip(digits[:8], weights, strict=False)) % 10


def luhn_valid(text: str) -> bool:
    """Validate Luhn (mod 10) checksum."""
    digits_only = re.sub(r"\D", "", text)
    if len(digits_only) < 2:
        return False
    digits = [int(c) for c in digits_only]
    total = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def ihi_valid(text: str) -> bool:
    """Validate AU IHI: 16 digits starting with 800360, Luhn check."""
    digits_only = re.sub(r"\D", "", text)
    return len(digits_only) == 16 and digits_only.startswith("800360") and luhn_valid(digits_only)


# ---------------------------------------------------------------------------
# Presidio recognizer helpers
# ---------------------------------------------------------------------------

def _to_phispan(result: RecognizerResult, text: str, source: str) -> PHISpan:
    return PHISpan(
        start=result.start,
        end=result.end,
        type=EntityType(result.entity_type),
        text=text[result.start : result.end],
        score=result.score,
        source=source,  # type: ignore[arg-type]
        recognizer=getattr(result, "analysis_explanation", None)
        and getattr(result.analysis_explanation, "recognizer_name", None),
    )


def _span_list(recognizer: EntityRecognizer, text: str) -> list[PHISpan]:
    """Run a Presidio recognizer directly and return typed PHISpans."""
    results = recognizer.analyze(text=text, entities=[recognizer.supported_entities[0]])
    return [_to_phispan(r, text, "rule") for r in results]


# ---------------------------------------------------------------------------
# Checksum-based recognizers
# ---------------------------------------------------------------------------

class NhiOldRecognizer(PatternRecognizer):
    """NZ NHI old format ``LLLNNNC`` with mod-11 checksum."""

    def __init__(self) -> None:
        super().__init__(
            supported_entity=EntityType.NHI.value,
            name="NhiOldRecognizer",
            patterns=[Pattern(name="nhi_old", regex=r"\b[A-HJ-NP-Z]{3}\d{4}\b", score=0.9)],
            context=["nhi", "national health index"],
            supported_language="en",
        )

    def validate_result(self, pattern_text: str) -> bool | None:  # noqa: D102
        return nhi_old_valid(pattern_text)


class NhiNewRecognizer(PatternRecognizer):
    """NZ NHI new format ``LLLNNLX``: pattern only, no checksum enforcement."""

    def __init__(self) -> None:
        super().__init__(
            supported_entity=EntityType.NHI.value,
            name="NhiNewRecognizer",
            patterns=[Pattern(name="nhi_new", regex=r"\b[A-HJ-NP-Z]{3}\d{2}[A-HJ-NP-Z]{2}\b", score=0.6)],
            context=["nhi", "national health index"],
            supported_language="en",
        )


class MedicareRecognizer(PatternRecognizer):
    """AU Medicare card number with weighted mod-10 check digit."""

    def __init__(self) -> None:
        super().__init__(
            supported_entity=EntityType.MEDICARE.value,
            name="MedicareRecognizer",
            patterns=[
                Pattern(name="medicare", regex=r"\b[2-6]\d{7}\s?\d\s?\d?\b", score=0.9)
            ],
            context=["medicare"],
            supported_language="en",
        )

    def validate_result(self, pattern_text: str) -> bool | None:  # noqa: D102
        return medicare_valid(pattern_text)


class IhiRecognizer(PatternRecognizer):
    """AU IHI 16-digit Luhn identifier."""

    def __init__(self) -> None:
        super().__init__(
            supported_entity=EntityType.IHI.value,
            name="IhiRecognizer",
            patterns=[
                Pattern(
                    name="ihi",
                    regex=r"\b8003\s?60\s?\d{4}\s?\d{4}\s?\d{2}\b",
                    score=0.9,
                )
            ],
            context=["ihi", "individual healthcare identifier"],
            supported_language="en",
        )

    def validate_result(self, pattern_text: str) -> bool | None:  # noqa: D102
        return ihi_valid(pattern_text)


# ---------------------------------------------------------------------------
# Other rule recognizers
# ---------------------------------------------------------------------------

class PhoneRecognizerPhi(EntityRecognizer):
    """Phone numbers via the ``phonenumbers`` library for configured regions."""

    def __init__(self, regions: list[str] | None = None) -> None:
        self.regions = regions or ["NZ", "AU"]
        super().__init__(supported_entities=[EntityType.PHONE.value], supported_language="en", name="PhoneRecognizerPhi")

    def analyze(
        self, text: str, entities: list[str], nlp_artifacts: NlpArtifacts | None = None
    ) -> list[RecognizerResult]:
        results: list[RecognizerResult] = []
        seen: set[tuple[int, int]] = set()
        for region in self.regions:
            for match in phonenumbers.PhoneNumberMatcher(text, region=region):
                key = (match.start, match.end)
                if key in seen:
                    continue
                seen.add(key)
                parsed = match.number
                if phonenumbers.region_code_for_number(parsed) in self.regions:
                    results.append(
                        RecognizerResult(
                            entity_type=EntityType.PHONE.value,
                            start=match.start,
                            end=match.end,
                            score=0.9,
                        )
                    )
        return results


class DateRecognizerCustom(EntityRecognizer):
    """Day-first dates using regex + dateparser."""

    PATTERNS = [
        # dd/mm/yyyy or d/m/yy
        r"\b\d{1,2}/\d{1,2}/\d{2,4}\b",
        # d Mon yyyy or dd Month yyyy
        r"\b\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4}\b",
        # ISO
        r"\b\d{4}-\d{2}-\d{2}\b",
    ]

    def __init__(self) -> None:
        super().__init__(supported_entities=[EntityType.DATE.value], supported_language="en", name="DateRecognizerCustom")
        self._regex = re.compile("|".join(f"({p})" for p in self.PATTERNS), re.IGNORECASE)

    def analyze(
        self, text: str, entities: list[str], nlp_artifacts: NlpArtifacts | None = None
    ) -> list[RecognizerResult]:
        results: list[RecognizerResult] = []
        seen: set[tuple[int, int]] = set()
        for m in self._regex.finditer(text):
            key = (m.start(), m.end())
            if key in seen:
                continue
            seen.add(key)
            parsed = dateparser_parse(
                m.group(),
                settings={"DATE_ORDER": "DMY", "STRICT_PARSING": False, "REQUIRE_PARTS": ["day", "month", "year"]},
            )
            if parsed:
                results.append(
                    RecognizerResult(
                        entity_type=EntityType.DATE.value,
                        start=m.start(),
                        end=m.end(),
                        score=0.85,
                    )
                )
        return results


class MrnRecognizer(EntityRecognizer):
    """Medical record number patterns, returning only the numeric part."""

    REGEX = re.compile(r"\b(?:MRN|UR|U/R)[:\s#]*(\d{5,8})\b", re.IGNORECASE)

    def __init__(self) -> None:
        super().__init__(supported_entities=[EntityType.MRN.value], supported_language="en", name="MrnRecognizer")

    def analyze(
        self, text: str, entities: list[str], nlp_artifacts: NlpArtifacts | None = None
    ) -> list[RecognizerResult]:
        return [
            RecognizerResult(
                entity_type=EntityType.MRN.value,
                start=m.start(1),
                end=m.end(1),
                score=0.85,
            )
            for m in self.REGEX.finditer(text)
        ]


class AgeRecognizer(PatternRecognizer):
    """Age expressions; all ages flagged, eval scores >89 strictly."""

    def __init__(self) -> None:
        super().__init__(
            supported_entity=EntityType.AGE.value,
            name="AgeRecognizer",
            patterns=[
                Pattern(name="age_yo", regex=r"\b(\d{1,3})\s*(?:yo|y/o)\b", score=0.75),
                Pattern(name="age_years", regex=r"\b(\d{1,3})\s*(?:years?\s*old)\b", score=0.75),
            ],
            supported_language="en",
        )


class LocationRecognizer(EntityRecognizer):
    """Address lines and city+postcode combinations."""

    STREET_RE = re.compile(
        r"\b\d{1,5}\s+[A-Za-z]+(?:[\s\-'][A-Za-z]+)*\s+"
        r"(?:Street|St|Road|Rd|Avenue|Ave|Drive|Dr|Lane|Ln|Court|Ct|Place|Pl|Way|"
        r"Terrace|Tce|Crescent|Cres|Parade|Pde|Boulevard|Blvd|Cutting|Esplanade|Highway|Hwy)\b",
        re.IGNORECASE,
    )
    CITY_POSTCODE_RE = re.compile(
        r"\b([A-Za-z]+(?:\s+[A-Za-z]+)?)\s*,?\s+(\d{4})\b",
        re.IGNORECASE,
    )
    ADDRESS_WORDS = {"address", "street", "road", "ave", "avenue", "drive", "suburb", "city", "lives", "lived"}

    def __init__(self) -> None:
        super().__init__(supported_entities=[EntityType.LOCATION.value], supported_language="en", name="LocationRecognizer")

    def analyze(
        self, text: str, entities: list[str], nlp_artifacts: NlpArtifacts | None = None
    ) -> list[RecognizerResult]:
        results: list[RecognizerResult] = []
        seen: set[tuple[int, int]] = set()
        lower = text.lower()

        for m in self.STREET_RE.finditer(text):
            key = (m.start(), m.end())
            seen.add(key)
            results.append(
                RecognizerResult(
                    entity_type=EntityType.LOCATION.value,
                    start=m.start(),
                    end=m.end(),
                    score=0.75,
                )
            )

        for m in self.CITY_POSTCODE_RE.finditer(text):
            city_start, city_end = m.start(1), m.end(1)
            key = (city_start, city_end)
            if key in seen:
                continue
            window = lower[max(0, city_start - 50) : m.end() + 10]
            if any(w in window for w in self.ADDRESS_WORDS):
                seen.add(key)
                results.append(
                    RecognizerResult(
                        entity_type=EntityType.LOCATION.value,
                        start=city_start,
                        end=city_end,
                        score=0.6,
                    )
                )
        return results


class PostcodeRecognizer(EntityRecognizer):
    """4-digit postcodes gated by address context on the same line."""

    ADDRESS_WORDS = {
        "address", "street", "road", "ave", "avenue", "drive", "suburb", "city",
        "town", "postcode", "post", "nz", "australia", "auckland", "wellington",
        "sydney", "melbourne", "brisbane", "perth", "adelaide", "unit",
    }

    def __init__(self) -> None:
        super().__init__(supported_entities=[EntityType.POSTCODE.value], supported_language="en", name="PostcodeRecognizer")
        self._regex = re.compile(r"\b\d{4}\b")

    def _line_has_context(self, line: str) -> bool:
        lower = line.lower()
        return any(re.search(rf"\b{re.escape(w)}\b", lower) for w in self.ADDRESS_WORDS)

    def analyze(
        self, text: str, entities: list[str], nlp_artifacts: NlpArtifacts | None = None
    ) -> list[RecognizerResult]:
        results: list[RecognizerResult] = []
        for line_start, line in self._iter_lines(text):
            if not self._line_has_context(line):
                continue
            for m in self._regex.finditer(line):
                results.append(
                    RecognizerResult(
                        entity_type=EntityType.POSTCODE.value,
                        start=line_start + m.start(),
                        end=line_start + m.end(),
                        score=0.7,
                    )
                )
        return results

    @staticmethod
    def _iter_lines(text: str):
        start = 0
        for line in text.splitlines(keepends=True):
            yield start, line
            start += len(line)


# ---------------------------------------------------------------------------
# Recognizer registry
# ---------------------------------------------------------------------------

def build_rule_recognizers(regions: list[str] | None = None) -> list[EntityRecognizer]:
    """Return all deterministic rule recognizers."""
    return [
        NhiOldRecognizer(),
        NhiNewRecognizer(),
        MedicareRecognizer(),
        IhiRecognizer(),
        PhoneRecognizerPhi(regions=regions),
        DateRecognizerCustom(),
        MrnRecognizer(),
        AgeRecognizer(),
        LocationRecognizer(),
        PostcodeRecognizer(),
    ]


def add_rule_recognizers(engine: AnalyzerEngine, regions: list[str] | None = None) -> AnalyzerEngine:
    """Add custom rule recognizers to a Presidio AnalyzerEngine."""
    for rec in build_rule_recognizers(regions):
        engine.registry.add_recognizer(rec)
    return engine


# ---------------------------------------------------------------------------
# Direct rule detection (testing / CLI)
# ---------------------------------------------------------------------------

def detect_rules(text: str, regions: list[str] | None = None) -> list[PHISpan]:
    """Run only the rule-based recognizers and return typed spans."""
    recognizers = build_rule_recognizers(regions)
    spans: list[PHISpan] = []
    for rec in recognizers:
        spans.extend(_span_list(rec, text))
    # Built-in Presidio recognizers for email/url/ip
    engine = AnalyzerEngine()
    for rec in recognizers:
        engine.registry.add_recognizer(rec)
    engine_results = engine.analyze(text=text, language="en", entities=[])
    # Map Presidio entity names to our EntityType names.
    builtin_map = {
        "EMAIL_ADDRESS": EntityType.EMAIL,
        "URL": EntityType.URL,
        "IP_ADDRESS": EntityType.IP,
    }
    for r in engine_results:
        if r.entity_type in builtin_map:
            spans.append(
                PHISpan(
                    start=r.start,
                    end=r.end,
                    type=builtin_map[r.entity_type],
                    text=text[r.start : r.end],
                    score=r.score,
                    source="rule",
                    recognizer=f"presidio:{r.entity_type}",
                )
            )
    return spans

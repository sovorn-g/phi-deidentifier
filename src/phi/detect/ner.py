"""NER detection layer using Presidio + spaCy ``en_core_web_lg``.

Contracts: CONTRACTS.md §6.
"""

from __future__ import annotations

import logging
from functools import lru_cache

from presidio_analyzer import AnalyzerEngine, RecognizerResult
from presidio_analyzer.nlp_engine import NlpEngineProvider

from phi.detect.rules import add_rule_recognizers
from phi.models import EntityType, PHISpan

log = logging.getLogger(__name__)

# spaCy -> PHI entity-type mapping (CONTRACTS §6).
# Presidio's SpacyRecognizer emits PERSON, LOCATION, ORGANIZATION, DATE_TIME, NRP.
_NER_TYPE_MAP: dict[str, EntityType] = {
    "PERSON": EntityType.PERSON,
    "LOCATION": EntityType.LOCATION,
    "ORGANIZATION": EntityType.ORG,
}

# Structured types are owned by the rule layer.
_DROPPED_NER_TYPES = {"DATE_TIME", "PHONE_NUMBER", "EMAIL_ADDRESS", "URL", "IP_ADDRESS"}


@lru_cache
def _make_analyzer_engine(regions: tuple[str, ...]) -> AnalyzerEngine:
    """Create a cached Presidio AnalyzerEngine backed by spaCy en_core_web_lg."""
    nlp_config = {
        "nlp_engine_name": "spacy",
        "models": [{"lang_code": "en", "model_name": "en_core_web_lg"}],
    }
    provider = NlpEngineProvider(nlp_configuration=nlp_config)
    engine = AnalyzerEngine(nlp_engine=provider.create_engine())
    # Add our deterministic recognizers on top so the same analyzer can run
    # the full hybrid stack; the pipeline layers are still separable.
    add_rule_recognizers(engine, list(regions))
    return engine


def _to_phispan(result: RecognizerResult, text: str) -> PHISpan:
    return PHISpan(
        start=result.start,
        end=result.end,
        type=EntityType(_NER_TYPE_MAP.get(result.entity_type, EntityType.ID.value)),
        text=text[result.start : result.end],
        score=result.score,
        source="ner",
        recognizer="spacy:en_core_web_lg",
    )


_NOISY_ORG_TOKENS = {
    "nhi", "ihi", "medicare", "mrn", "ur", "u/r", "dob", "phone", "email", "fax",
    "address", "postcode", "patient", "clinic", "hospital",
}


def _is_noisy_ner(span: PHISpan) -> bool:
    """Filter obvious NER false positives that the rule layer should own."""
    txt = span.text.strip()
    if span.type == EntityType.PERSON and any(c.isdigit() for c in txt):
        return True
    if span.type == EntityType.ORG and txt.lower() in _NOISY_ORG_TOKENS:
        return True
    if "\n" in txt:
        return True
    return False


def detect_ner(text: str, regions: list[str], threshold: float = 0.40) -> list[PHISpan]:
    """Run spaCy NER through Presidio and return mapped PHISpans."""
    engine = _make_analyzer_engine(tuple(regions))
    results = engine.analyze(
        text=text,
        language="en",
        entities=list(_NER_TYPE_MAP.keys()),
        score_threshold=threshold,
    )
    spans = []
    for r in results:
        if r.entity_type not in _NER_TYPE_MAP:
            continue
        span = _to_phispan(r, text)
        if _is_noisy_ner(span):
            log.debug("filtering noisy NER span: %s", span.text)
            continue
        spans.append(span)
    return spans

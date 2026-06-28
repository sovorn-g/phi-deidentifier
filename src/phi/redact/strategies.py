"""Redaction strategies: mask, hash, surrogate.

Contracts: CONTRACTS.md §9.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import re
from datetime import datetime, timedelta

from faker import Faker

from phi.models import DetectionResult, EntityType, PHISpan, StrategyName

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalize(text: str) -> str:
    """Casefold and collapse internal whitespace."""
    return re.sub(r"\s+", " ", text.casefold()).strip()


def _entity_key(entity_type: EntityType, text: str, hash_key: str) -> str:
    """Deterministic 10-char hex token for an entity."""
    payload = f"{entity_type.value}:{_normalize(text)}"
    mac = hmac.new(hash_key.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256)
    return mac.hexdigest()[:10]


def _seed_int(entity_type: EntityType, text: str, hash_key: str) -> int:
    """Integer seed derived from the entity key for Faker consistency."""
    return int(_entity_key(entity_type, text, hash_key), 16)


# ---------------------------------------------------------------------------
# Surrogate generation
# ---------------------------------------------------------------------------

_SURROGATE_FAKER = Faker()


def _format_preserving_id(text: str) -> str:
    """Keep the same shape (digits/letters) but replace each character."""
    out = []
    for ch in text:
        if ch.isdigit():
            out.append(str((int(ch) + 7) % 10))
        elif ch.isalpha():
            base = ord("A") if ch.isupper() else ord("a")
            out.append(chr(base + ((ord(ch.upper()) - ord("A") + 13) % 26)))
        else:
            out.append(ch)
    return "".join(out)


def _surrogate_for(span: PHISpan, hash_key: str) -> str:
    seed = _seed_int(span.type, span.text, hash_key)
    faker = Faker()
    faker.seed_instance(seed)

    match span.type:
        case EntityType.PERSON:
            return faker.name()
        case EntityType.DATE:
            # Date-shift: preserve rough era, change by a deterministic offset.
            days = seed % 365 * 3
            shifted = datetime(2000, 1, 1) + timedelta(days=days)
            return shifted.strftime("%d/%m/%Y")
        case EntityType.PHONE:
            return faker.phone_number()
        case EntityType.EMAIL:
            return faker.email()
        case EntityType.URL:
            return faker.url()
        case EntityType.IP:
            return faker.ipv4()
        case EntityType.LOCATION:
            return faker.city()
        case EntityType.ORG:
            return faker.company()
        case EntityType.POSTCODE:
            return f"{seed % 9000 + 1000}"
        case EntityType.AGE:
            return str(seed % 90 + 10)
        case EntityType.MRN | EntityType.NHI | EntityType.MEDICARE | EntityType.IHI | EntityType.ID:
            return _format_preserving_id(span.text)
        case _:
            return faker.word()


# ---------------------------------------------------------------------------
# Strategy dispatch
# ---------------------------------------------------------------------------

def _replacement(span: PHISpan, strategy: StrategyName, hash_key: str) -> str:
    match strategy:
        case "mask":
            return f"[REDACTED:{span.type.value}]"
        case "hash":
            return f"[{span.type.value}:{_entity_key(span.type, span.text, hash_key)}]"
        case "surrogate":
            return _surrogate_for(span, hash_key)
        case _:
            raise ValueError(f"unknown strategy: {strategy}")


def redact(result: DetectionResult, strategy: StrategyName, hash_key: str | None = None) -> str:
    """Apply redaction strategy to detection result, rewriting right-to-left."""
    if strategy in ("hash", "surrogate") and not hash_key:
        raise ValueError(f"strategy {strategy} requires PHI_HASH_KEY")
    hash_key = hash_key or ""

    text = result.text
    # Sort by start descending so offsets remain valid as we mutate.
    for span in sorted(result.spans, key=lambda s: s.start, reverse=True):
        replacement = _replacement(span, strategy, hash_key)
        text = text[: span.start] + replacement + text[span.end :]
    return text


def audit_entries(result: DetectionResult) -> list[tuple[EntityType, int]]:
    """Return (type, count) pairs for the audit log."""
    counts: dict[EntityType, int] = {}
    for span in result.spans:
        counts[span.type] = counts.get(span.type, 0) + 1
    return sorted(counts.items(), key=lambda x: x[0].value)

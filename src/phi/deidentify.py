"""Public API: deidentify(text, config).

Contracts: CONTRACTS.md §10, §11.
"""

from __future__ import annotations

from phi.config import get_settings
from phi.detect.pipeline import detect
from phi.models import AuditEntry, DeidConfig, DeidResult
from phi.redact.strategies import audit_entries, redact


def deidentify(text: str, config: DeidConfig | None = None) -> DeidResult:
    """Detect PHI in ``text`` and redact using the configured strategy."""
    config = config or DeidConfig()
    settings = get_settings()

    detection = detect(text, config)
    hash_key = settings.phi_hash_key or ""
    redacted = redact(detection, config.strategy, hash_key)

    audit = [AuditEntry(type=t, count=c) for t, c in audit_entries(detection)]
    return DeidResult(
        redacted_text=redacted,
        spans=detection.spans,
        audit=audit,
    )

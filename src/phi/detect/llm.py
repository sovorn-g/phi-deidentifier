"""Optional LLM second pass to catch residual context-dependent PHI.

Contracts: CONTRACTS.md §7.
"""

from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from phi.config import get_settings
from phi.models import EntityType, PHISpan

log = logging.getLogger(__name__)

_SYSTEM = """You are a clinical PHI detector. Your job is to find any remaining Protected Health Information (PHI) in the clinical note that has not already been listed.

Return a JSON object with a single key "spans" containing a list of objects. Each object must have:
- "text": the exact substring from the note
- "type": one of PERSON, LOCATION, ORG, DATE, AGE, PHONE, EMAIL, URL, IP, MRN, NHI, MEDICARE, IHI, POSTCODE, ID

Do not transform or redact the text. Do not return offsets. Only return PHI that is not already listed below."""


class _LLMSpan(BaseModel):
    text: str = Field(..., min_length=1)
    type: str


class _LLMOutput(BaseModel):
    spans: list[_LLMSpan] = Field(default_factory=list)


def _complete_with_clinical_core(system: str, user: str, schema: type[_LLMOutput]) -> _LLMOutput | None:
    try:
        from clinical_core.llm import LLMClient

        return LLMClient().complete(system, user, schema)
    except Exception as exc:  # noqa: BLE001
        log.warning("clinical_core LLM call failed: %s", exc)
        return None


def _complete_with_litellm(system: str, user: str, schema: type[_LLMOutput]) -> _LLMOutput | None:
    try:
        import litellm
    except ImportError:
        log.warning("litellm not installed; LLM pass unavailable")
        return None

    settings = get_settings()
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    try:
        response = litellm.completion(
            model=settings.llm_model,
            messages=messages,
            temperature=0.0,
            response_format={"type": "json_object"},
        )
        content = response["choices"][0]["message"]["content"] or "{}"
        return schema.model_validate_json(content)
    except Exception as exc:  # noqa: BLE001
        log.warning("direct LiteLLM call failed: %s", exc)
        return None


def _resolve_offset(text: str, substring: str, consumed: set[tuple[int, int]]) -> tuple[int, int] | None:
    """Find the first occurrence of substring not in consumed ranges."""
    start = 0
    while True:
        idx = text.find(substring, start)
        if idx == -1:
            return None
        end = idx + len(substring)
        if not any(s < end and idx < e for s, e in consumed):
            return idx, end
        start = end


def detect_llm(
    text: str,
    existing_spans: list[PHISpan],
    regions: list[str],
) -> list[PHISpan]:
    """Run an LLM second pass and return any additional PHI spans."""
    settings = get_settings()
    if not settings.phi_use_llm:
        log.debug("LLM pass disabled in settings")
        return []

    existing_block = "\n".join(
        f"- {s.text!r} ({s.type.value})" for s in existing_spans
    ) or "(none)"
    user = f"Clinical note:\n{text}\n\nAlready detected spans:\n{existing_block}\n\nRegions: {', '.join(regions)}"

    result = _complete_with_clinical_core(_SYSTEM, user, _LLMOutput)
    if result is None:
        result = _complete_with_litellm(_SYSTEM, user, _LLMOutput)
    if result is None:
        return []

    consumed = {(s.start, s.end) for s in existing_spans}
    new_spans: list[PHISpan] = []
    for ls in result.spans:
        offset = _resolve_offset(text, ls.text, consumed)
        if offset is None:
            log.debug("LLM returned text not found or already consumed: %r", ls.text)
            continue
        start, end = offset
        consumed.add((start, end))
        try:
            etype = EntityType(ls.type.upper())
        except ValueError:
            log.debug("LLM returned unknown entity type: %s", ls.type)
            continue
        new_spans.append(
            PHISpan(
                start=start,
                end=end,
                type=etype,
                text=text[start:end],
                score=0.75,
                source="llm",
                recognizer=settings.llm_model,
            )
        )
    return new_spans

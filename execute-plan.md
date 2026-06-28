# PHI De-identifier — Execution Plan

> **Tier:** 🟢 Small · **Est. effort:** 1–3 days · **Status:** 🔴 Not started
> **Reuses:** `clinical_core` (LLM wrapper, optional) · **Feeds into:** B1, B2, B3 (privacy layer)
>
> **Before coding, read [CONTRACTS.md](CONTRACTS.md)** — it pins the things this plan leaves implicit and
> that a coding agent must not invent: the `labels.json` gold-span schema, the `PHISpan`/`EntityType` model,
> the **verified** NZ NHI / AU Medicare / AU IHI checksum algorithms (with test vectors), the rule↔NER↔LLM
> merge precedence, the redaction-strategy formats, the `clinical_core` reuse path, and the **span-level
> matching rule** the recall metric is measured with. This plan is the *what/why*; CONTRACTS is the *how*.

---

## 1. Overview
Detect and redact Protected Health Information (PHI) from free-text clinical notes — names, dates,
contact details, identifiers (incl. **NZ NHI** and AU **Medicare/IHI** numbers) — using a hybrid of
rule-based, NER, and LLM detection, with configurable redaction strategies.

## 2. Why This Project (Market Context)
Privacy is the #1 blocker to health-AI adoption. Demonstrating a defensible de-identification pipeline
signals clinical-grade maturity and directly addresses every clinic/startup's first question:
*"What about patient data?"* It's also the gate that lets you safely demo everything else.

## 3. Success Criteria
- [ ] Detect & redact the HIPAA 18 identifier categories + NZ NHI + AU IHI/Medicare patterns.
- [ ] Configurable output: mask / hash / realistic surrogate replacement.
- [ ] Precision & recall reported on a labelled synthetic test set (target: **span-level, type-aware,
      partial-overlap** recall ≥ 0.95 on the *identifier* subset — matching rule defined in CONTRACTS §12;
      report both relaxed and strict columns, and frame the number as illustrative on ~30 synthetic notes).
- [ ] CLI + minimal UI; processes a note in < 3s.

## 4. Tech Stack
Python 3.11+, [Microsoft Presidio](https://github.com/microsoft/presidio) (analyzer + anonymizer),
spaCy `en_core_web_lg` (general NER for names/places; scispaCy is **not** used for PERSON — see CONTRACTS §6),
`phonenumbers`, `dateparser`, `faker`, regex, LiteLLM/Anthropic (optional LLM second-pass), pytest. Streamlit demo.

## 5. Data Source
Synthea-generated notes + hand-crafted synthetic notes seeded with known PHI (so ground-truth labels
exist for scoring). **No real PHI.**

## 6. Prerequisites & Dependencies
- `clinical_core` LLM wrapper (optional LLM pass).
- Presidio + a spaCy model installed.

## 7. Execution Phases

### Phase 0 — Setup & Labelled Corpus
**Objectives:** Repo + a scorable test set.
**Key tasks:**
- [ ] Init repo, env, Presidio + spaCy model install.
- [ ] Generate/author ~30 synthetic notes with embedded, labelled PHI spans (JSON ground truth).
**Deliverable:** `data/notes/` + `data/labels.json`.
**Acceptance:** Loader yields (text, gold spans) pairs.

### Phase 1 — Rule-Based Detection
**Objectives:** High-precision deterministic catches.
**Key tasks:**
- [ ] Regex recognizers: dates, phones, emails, MRN, **NZ NHI** (`LLLNNNC`, e.g. valid `ABC1235` — note
      the plan's old `ABC1234` is checksum-invalid), AU Medicare/IHI, addresses, postcodes.
- [ ] Custom Presidio recognizers for the NZ/AU-specific IDs — **validate the checksum, don't just
      pattern-match** (NHI mod-11, Medicare weighted mod-10, IHI Luhn; algorithms + test vectors in CONTRACTS §5).
**Deliverable:** Rule recognizer module.
**Acceptance:** Catches all structured-format identifiers in test set.

### Phase 2 — NER-Based Detection
**Objectives:** Catch names, locations, orgs.
**Key tasks:**
- [ ] Wire Presidio analyzer + spaCy **`en_core_web_lg`** (general NER) for person/location/org entities.
      ⚠️ Not scispaCy — scispaCy models target diseases/chemicals/genes and emit no PERSON; see CONTRACTS §6.
- [ ] Tune confidence thresholds; merge overlapping spans with Phase 1 per the precedence rule (CONTRACTS §8).
**Deliverable:** Combined detection pipeline.
**Acceptance:** Recall ≥ 0.90 pre-LLM on names/locations.

### Phase 3 — LLM Second Pass + Redaction Strategies
**Objectives:** Close the gap + flexible output.
**Key tasks:**
- [ ] Optional LLM pass to catch context-dependent PHI the rules/NER miss (e.g., "the patient's
      daughter Jane").
- [ ] Redaction strategies: `[REDACTED:TYPE]` mask, deterministic hash, faker-style surrogate.
- [ ] Idempotency + audit log of what was removed (types/counts only).
**Deliverable:** `deidentify(text, strategy)`.
**Acceptance:** All three strategies produce valid, reversible-where-intended output.

### Phase 4 — Evaluation & Demo
**Objectives:** Prove it and present it.
**Key tasks:**
- [ ] Score precision/recall/F1 per entity type vs. gold labels; commit report.
- [ ] Streamlit: paste note → highlighted detected PHI → redacted output + strategy toggle.
- [ ] README with metrics table, architecture diagram, privacy framing.
**Deliverable:** Eval report + demo + README.
**Acceptance:** Recall ≥ 0.95 on identifiers; demo runs from fresh clone.

## 8. Portfolio Deliverables
Metrics table (precision/recall by type), architecture diagram, demo GIF. LinkedIn angle:
*"A defensible PHI de-identification pipeline — the unglamorous foundation every health-AI product
needs."*

## 9. Risks & Notes
- Recall matters more than precision here (a missed identifier is a breach; an over-redaction is an
  inconvenience) — tune accordingly.
- Document explicitly that this is a portfolio demo, **not** a certified de-id solution.

## 10. Definition of Done
Hybrid pipeline + 3 redaction strategies working, metrics committed, demo recorded, README published.

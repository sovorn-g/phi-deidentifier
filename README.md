# PHI De-identifier

A hybrid, defensible PHI de-identification pipeline for clinical free text. It combines **rule-based recognizers** (with verified checksums), **spaCy NER**, and an optional **LLM second pass**, then redacts with one of three strategies: `mask`, `hash`, or `surrogate`.

> **Portfolio demo, not a certified de-identification solution.**  
> Built and evaluated on ~30 synthetic notes with embedded gold-span labels.

---

## Why this matters

Privacy is the first question every clinic or health-AI startup asks. A de-identification pipeline that can point to documented algorithms, deterministic merge rules, and measured recall is the unglamorous foundation that makes every other clinical-AI demo safe.

---

## Quick start

```bash
# 1. Install dependencies (uv-managed)
uv sync --extra dev

# 2. Run the test suite (offline, LLM disabled)
uv run pytest -q

# 3. De-identify a single note
uv run python -m phi.cli fixtures/rich.txt --strategy mask

# 4. Run the evaluation report
uv run python -m phi.eval.score

# 5. Launch the interactive demo
uv run streamlit run src/phi/app.py
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                         Input note                          │
└─────────────────────────┬───────────────────────────────────┘
                          ▼
        ┌─────────────────┴─────────────────┐
        │  Rule-based recognizers (§5)      │  ← deterministic, high precision
        │  NHI/Medicare/IHI checksums,      │
        │  phones, dates, emails, URLs,     │
        │  IPs, MRNs, ages, postcodes       │
        └─────────────────┬─────────────────┘
                          ▼
        ┌─────────────────┴─────────────────┐
        │  spaCy NER (en_core_web_lg)       │  ← PERSON / LOCATION / ORG
        └─────────────────┬─────────────────┘
                          ▼
        ┌─────────────────┴─────────────────┐
        │  Optional LLM second pass         │  ← context-dependent residual PHI
        └─────────────────┬─────────────────┘
                          ▼
        ┌─────────────────┴─────────────────┐
        │  Deterministic merge (§8)         │  ← rule > ner > llm
        └─────────────────┬─────────────────┘
                          ▼
        ┌─────────────────┴─────────────────┐
        │  Redaction: mask / hash / surrogate│
        └───────────────────────────────────┘
```

Key design choices:
- **Checksums are mandatory** for NZ NHI (old format), AU Medicare, and AU IHI. Pattern-matching alone is not enough.
- **Rule layer owns structured identifiers; NER owns names/places/orgs.** Merge precedence prevents a postcode from swallowing a date.
- **LLM is optional and default-off.** The project runs, tests, and scores entirely offline.
- **Idempotency:** redacted tokens are never re-detected, so `deidentify(deidentify(x)) == deidentify(x)`.

---

## Redaction strategies

| Strategy | Example output | Properties |
|----------|----------------|------------|
| `mask` | `[REDACTED:PERSON]` | Irreversible, non-consistent |
| `hash` | `[PERSON:a3f9b2c1d0]` | Deterministic, consistent across notes, pseudonymous |
| `surrogate` | `Emily Johnson` | Realistic fake of same type, consistent per entity |

Hash and surrogate require `PHI_HASH_KEY` in `.env`.

---

## Evaluation

Matching rule: **span-level, type-aware, partial-overlap** with `IoU ≥ 0.5`. A stricter exact-boundary column is also reported.

Latest run on the synthetic corpus (`uv run python -m phi.eval.score`):

| Aggregate | Relaxed P / R / F1 | Strict P / R / F1 |
|-----------|-------------------|-------------------|
| Identifiers | 1.000 / **0.993** / 0.996 | 1.000 / **0.993** / 0.996 |
| Overall | 0.985 / 0.985 / 0.985 | 0.965 / 0.965 / 0.965 |

Per-type table is written to [`eval/report.md`](eval/report.md).

> These numbers are **illustrative on a small synthetic set** authored alongside the recognizers. They are not a validation claim on real clinical data.

---

## HIPAA-18 to entity-type mapping

| HIPAA category | EntityType | Notes |
|----------------|------------|-------|
| Name | `PERSON` | |
| Dates (except year) | `DATE` | Includes DOB, admission dates |
| Phone / Fax | `PHONE` | |
| Email | `EMAIL` | |
| SSN | `ID` | Out of scope for text notes |
| MRN | `MRN` | |
| Health plan / account # | `ID` | |
| Certificate / license # | `ID` | |
| Vehicle / device id | `ID` | |
| URL / IP | `URL` / `IP` | |
| Biometric / full-face photo | — | Out of scope for a text pipeline |
| Address (geographic subdivisions) | `LOCATION` / `POSTCODE` | |
| Age > 89 | `AGE` | All ages flagged; >89 scored strictly |
| NZ NHI | `NHI` | Old-format checksum validated |
| AU Medicare | `MEDICARE` | Weighted mod-10 check digit |
| AU IHI | `IHI` | Luhn checksum |

---

## Project layout

```
phi-deidentifier/
├── src/phi/
│   ├── detect/
│   │   ├── rules.py          # regex + checksum recognizers
│   │   ├── ner.py            # Presidio + spaCy NER
│   │   ├── llm.py            # optional LLM second pass
│   │   └── pipeline.py       # merge logic
│   ├── redact/
│   │   └── strategies.py     # mask / hash / surrogate
│   ├── eval/
│   │   └── score.py          # span-level P/R/F1
│   ├── config/settings.py    # pydantic-settings
│   ├── models.py             # PHISpan, EntityType, DeidConfig
│   ├── corpus.py             # gold-label loader
│   ├── deidentify.py         # public API
│   ├── cli.py                # command-line tool
│   └── app.py                # Streamlit demo
├── data/
│   ├── notes/                # synthetic notes
│   └── labels.json           # gold spans
├── fixtures/                 # rich.txt, au.txt, sparse.txt
├── tests/                    # pytest suite
├── scripts/generate_corpus.py
├── eval/report.md
└── pyproject.toml
```

---

## Configuration

Copy `.env.example` to `.env` and set:

```bash
PHI_HASH_KEY=change-me-to-a-long-random-secret   # required for hash/surrogate
LLM_MODEL=anthropic/claude-haiku-4-5             # optional
ANTHROPIC_API_KEY=sk-ant-...                     # only if use_llm=True
```

The LLM layer is controlled by `use_llm` in `DeidConfig` and defaults to **False**, so tests and evaluation run offline.

---

## License

MIT — portfolio / educational use.

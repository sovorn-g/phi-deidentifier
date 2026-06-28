# PHI De-identifier

Detect and redact protected health information (PHI) in clinical free-text notes.

The pipeline combines deterministic rules, spaCy/Presidio named-entity recognition, and an optional LLM second pass. It can redact detected PHI as typed masks, deterministic hash tokens, or realistic surrogate values.

This is a demonstration project for synthetic clinical notes. It is not a certified de-identification product and should not be used as the only privacy control for real patient data.

## What It Detects

- Names, organizations, locations, addresses, and postcodes
- Dates, ages, phone numbers, emails, URLs, and IP addresses
- Medical record numbers and generic identifiers
- New Zealand NHI numbers
- Australian Medicare numbers
- Australian Individual Healthcare Identifiers (IHI)

NZ NHI, AU Medicare, and AU IHI detection includes checksum validation where the identifier format supports it. This reduces false positives from look-alike numbers.

## Quick Start

Install dependencies:

```bash
uv sync --extra dev
```

Run the tests:

```bash
uv run pytest -q
```

De-identify a sample note:

```bash
uv run python -m phi.cli fixtures/rich.txt --strategy mask
```

Run the evaluation report:

```bash
uv run python -m phi.eval.score
```

Launch the Streamlit demo:

```bash
uv run streamlit run src/phi/app.py
```

## CLI Usage

```bash
uv run python -m phi.cli path/to/note.txt --strategy mask
```

Available strategies:

| Strategy | Example | Description |
| --- | --- | --- |
| `mask` | `[REDACTED:PERSON]` | Replaces each span with its entity type. |
| `hash` | `[PERSON:a3f9b2c1d0]` | Stable pseudonymous token based on `PHI_HASH_KEY`. |
| `surrogate` | `Emily Johnson` | Stable fake value of the same general type. |

Use `--no-ner` to disable spaCy/Presidio NER:

```bash
uv run python -m phi.cli fixtures/rich.txt --strategy mask --no-ner
```

Use `--llm` to enable the optional LLM second pass:

```bash
uv run python -m phi.cli fixtures/rich.txt --strategy mask --llm
```

## Python API

```python
from phi.deidentify import deidentify
from phi.models import DeidConfig

text = "Patient Jane Smith, NHI ABC1235, was seen on 15/03/1980."

result = deidentify(
    text,
    DeidConfig(strategy="mask", use_llm=False),
)

print(result.redacted_text)
print(result.audit)
```

`result.spans` contains detected spans with offsets into the original text. The audit output reports counts by entity type only; it does not include PHI values.

## Configuration

Copy `.env.example` to `.env` when using hash/surrogate redaction or the optional LLM pass.

```bash
PHI_HASH_KEY=change-me-to-a-long-random-secret
LLM_MODEL=anthropic/claude-haiku-4-5
API_KEY=sk-...
PHI_REGIONS=NZ,AU
```

Configuration fields:

| Variable | Required | Description |
| --- | --- | --- |
| `PHI_HASH_KEY` | For `hash` and `surrogate` | Secret used to create stable hash tokens and surrogate values. |
| `LLM_MODEL` | For `--llm` | LiteLLM model name, such as `anthropic/claude-haiku-4-5`, `openai/gpt-4o-mini`, or another supported provider/model. |
| `API_KEY` | For `--llm` | Provider API key used by LiteLLM. |
| `PHI_REGIONS` | No | Comma-separated phone parsing regions. Defaults to `NZ,AU`. |

The LLM pass is off by default. Tests and evaluation run offline unless `--llm` or `DeidConfig(use_llm=True)` is used.

The generic `API_KEY` variable lets users switch providers by changing `LLM_MODEL`.

## How It Works

```text
Input note
  -> rule recognizers
  -> spaCy/Presidio NER
  -> optional LLM second pass
  -> deterministic overlap merge
  -> redaction strategy
  -> redacted note + privacy-safe audit counts
```

Detection layers:

- Rules handle structured identifiers, dates, phone numbers, emails, URLs, IPs, MRNs, ages, and postcodes.
- NER handles people, places, and organizations.
- The optional LLM pass looks for residual context-dependent PHI that rules and NER may miss.

When spans overlap, rule-based spans take precedence over NER spans, and NER spans take precedence over LLM spans. This keeps checksum-validated identifiers from being overwritten by broader entity matches.

## Evaluation

The repository includes 30 synthetic notes in `data/notes/` and gold labels in `data/labels.json`.

Run:

```bash
uv run python -m phi.eval.score
```

Latest synthetic-corpus result:

| Aggregate | Relaxed P / R / F1 | Strict P / R / F1 |
| --- | --- | --- |
| Identifiers | 1.000 / 0.993 / 0.996 | 1.000 / 0.993 / 0.996 |
| Overall | 0.985 / 0.985 / 0.985 | 0.965 / 0.965 / 0.965 |

Relaxed matching is span-level, type-aware matching with character overlap. Strict matching requires exact span boundaries. The full per-type table is written to `eval/report.md`.

These metrics are measured only on the included synthetic notes. They are useful for regression testing and demonstration, not proof of performance on real clinical data.

## Entity Types

| Entity type | Examples |
| --- | --- |
| `PERSON` | Patient, family member, clinician names |
| `LOCATION` | Street addresses, suburbs, cities, facilities |
| `ORG` | Clinics, hospitals, employers |
| `DATE` | DOB, admission date, appointment date |
| `AGE` | Ages in text |
| `PHONE` | NZ/AU phone numbers |
| `EMAIL` | Email addresses |
| `URL` | Web addresses |
| `IP` | IP addresses |
| `MRN` | Local medical record numbers |
| `NHI` | New Zealand National Health Index |
| `MEDICARE` | Australian Medicare card number |
| `IHI` | Australian Individual Healthcare Identifier |
| `POSTCODE` | NZ/AU 4-digit postcodes when address context is present |
| `ID` | Generic account, device, certificate, or other identifiers |

## Project Layout

```text
src/phi/
  app.py                 Streamlit demo
  cli.py                 Command-line interface
  deidentify.py          Public API
  models.py              Entity and result models
  corpus.py              Synthetic corpus loader
  config/settings.py     Environment-based settings
  detect/
    rules.py             Regex and checksum recognizers
    ner.py               Presidio/spaCy NER
    llm.py               Optional LiteLLM second pass
    pipeline.py          Detection and merge pipeline
  redact/
    strategies.py        Mask, hash, and surrogate redaction
  eval/
    score.py             Evaluation metrics

data/
  notes/                 Synthetic notes
  labels.json            Gold spans

fixtures/                Small sample notes for tests and demos
tests/                   Pytest suite
eval/report.md           Latest evaluation report
```

## Limitations

- The included corpus is synthetic and small.
- Performance on real clinical notes is not validated.
- Free-text de-identification is imperfect; missed PHI is possible.
- Images, biometrics, and full-face photos are outside the scope of this text-only pipeline.
- The optional LLM pass sends note text to the configured model provider. Do not enable it for sensitive data unless the provider and data-handling arrangement are appropriate.

## License

MIT

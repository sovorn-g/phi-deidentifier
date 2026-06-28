# CONTRACTS — PHI De-identifier

> Companion to [execute-plan.md](execute-plan.md). The plan says **what** and **why**; this file pins
> the **interfaces, schemas, algorithms, and methods** a coding agent would otherwise have to invent.
> For a *scoring* project the label schema and the matching rule are load-bearing — if an agent guesses
> them, the headline recall number is meaningless. Pin them here, change them deliberately.
>
> Status of each contract: 🔒 = frozen (eval/output depends on it), 🟡 = sensible default, change if needed.
>
> **Provenance note:** the NZ NHI / AU Medicare / AU IHI checksum algorithms in §5 were verified against
> published specs (sources cited inline) — not transcribed from memory. The plan's own example `ABC1234`
> is in fact checksum-**invalid** (correct check digit is 5 → `ABC1235`); that is exactly the class of
> error this file exists to prevent. Do not "simplify" the checksums back to a bare pattern match.

---

## 1. Repo layout & packaging 🔒

New standalone git repo `phi-deidentifier/`, `src/` layout, `uv`-managed, mirroring the sibling
`fhir-clinical-summarizer`. Two top-level packages: `phi` (this project) and a consumed dependency on
`clinical_core` (from the sibling repo — see §2).

```
phi-deidentifier/
├── pyproject.toml              # uv-managed; ruff + pytest + coverage config here
├── .env.example                # LLM_MODEL, the matching API key, PHI_HASH_KEY (§7)
├── .pre-commit-config.yaml     # ruff (lint+format), end-of-file, trailing-whitespace
├── README.md                   # Phase 4 deliverable
├── .pi/
│   ├── execute-plan.md
│   └── CONTRACTS.md            # this file
├── data/
│   ├── notes/                  # note_001.txt … note_030.txt (synthetic; committed)
│   └── labels.json             # gold spans (§3) — the eval ground truth
├── fixtures/                   # curated unit-test notes (subset of data/notes, see §11)
├── src/
│   └── phi/
│       ├── __init__.py
│       ├── config/
│       │   └── settings.py     # pydantic-settings; reads .env (thresholds, flags, hash key)
│       ├── models.py           # PHISpan, EntityType, DetectionResult, AuditEntry (§3, §4)
│       ├── corpus.py           # loader: yields (note_id, text, gold_spans) (§3)
│       ├── detect/
│       │   ├── rules.py        # regex + checksum recognizers + custom Presidio recognizers (§5)
│       │   ├── ner.py          # Presidio analyzer + spaCy NER (§6)
│       │   ├── llm.py          # optional LLM second pass (§7-LLM)
│       │   └── pipeline.py     # run all enabled layers → merge → DetectionResult (§8)
│       ├── redact/
│       │   └── strategies.py   # mask | hash | surrogate (§9)
│       ├── deidentify.py       # public API: deidentify(text, config) (§10)
│       ├── eval/
│       │   └── score.py        # span-level P/R/F1 vs gold (§12)
│       ├── cli.py              # `python -m phi.cli <note.txt> --strategy mask`
│       └── app.py              # Streamlit demo (§Phase 4)
└── tests/
    ├── conftest.py             # loads fixtures/ + labels subset
    ├── test_rules.py           # checksum unit tests incl. the §5 vectors
    ├── test_pipeline.py
    ├── test_redact.py          # idempotency + type-consistency (§9)
    └── test_eval.py
```

Import surface: `from phi.deidentify import deidentify, DeidConfig`,
`from phi.detect.pipeline import detect`, `from phi.models import PHISpan, EntityType`.

---

## 2. Reusing `clinical_core` (the LLM pass) 🟡

The plan lists `clinical_core` (LLM wrapper) as a reuse. Reality check from the sibling repo: as of this
writing `clinical_core` lives **inside `fhir-clinical-summarizer/src/`** and its `llm/` module may not be
built yet. Therefore **the LLM second pass is loosely coupled and optional** — the project must run, test,
and score with the LLM layer disabled.

- **Preferred:** path-install the sibling so `clinical_core` is importable, via `pyproject.toml`:
  ```toml
  [tool.uv.sources]
  clinical-core = { path = "../fhir-clinical-summarizer", editable = true }
  ```
  and call its wrapper (`from clinical_core.llm import complete` — structured output via Pydantic schema).
- **Fallback (if `clinical_core.llm` is absent):** `phi/detect/llm.py` makes a single direct LiteLLM call
  using the same `LLM_MODEL` env contract as the sibling (§7). Do **not** build a provider abstraction —
  LiteLLM is the abstraction.
- The pipeline checks `config.use_llm` (default **False**). With it False, no API key is needed and the
  whole test suite + eval runs offline. CI and the acceptance harness (§13) run with it False.

---

## 3. The label schema — `data/labels.json` 🔒

This is the most important contract in the project: the eval (§12) reads it directly. Get this wrong and
every reported number is wrong.

- **Offsets are character offsets into the UTF-8 note text, half-open `[start, end)`** (Python slice
  semantics: `text[start:end]` returns exactly `span.text`). Not byte offsets, not token offsets, not
  1-indexed.
- One JSON file for the whole corpus. `text` is redundant (recoverable from offsets) but **required** so a
  human and the loader can assert `text[start:end] == span.text` and catch drift.
- `type` is a member of the `EntityType` enum (§4) — exact string, uppercase.

```json
{
  "version": "1",
  "notes": [
    {
      "id": "note_001",
      "file": "data/notes/note_001.txt",
      "spans": [
        { "start": 0,  "end": 13, "type": "PERSON",   "text": "Margaret Chen" },
        { "start": 41, "end": 48, "type": "NHI",      "text": "ABC1235" },
        { "start": 70, "end": 80, "type": "DATE",     "text": "03/04/1976" }
      ]
    }
  ]
}
```

`corpus.py` contract:
```python
def load_corpus(root: Path = Path(".")) -> list[GoldNote]: ...
# GoldNote = (id: str, text: str, spans: list[PHISpan])  — spans have source="gold"
# On load, ASSERT text[s.start:s.end] == s.text for every span; raise on mismatch (offset drift).
```

---

## 4. Core data model 🔒

Pydantic v2 in `phi/models.py`. **One span type** is reused for gold labels and predictions; the `source`
field distinguishes them.

```python
class EntityType(str, Enum):
    # — Names / orgs / places (NER-led) —
    PERSON = "PERSON"
    LOCATION = "LOCATION"          # address lines, suburbs, cities, hospitals-as-place
    ORG = "ORG"                    # clinics, employers
    # — Structured identifiers (rule-led; the "identifiers" recall target, §12) —
    DATE = "DATE"                  # any date incl. DOB, admission; HIPAA dates
    AGE = "AGE"                    # ages > 89 are PHI under HIPAA; flag all ages, score >89 strictly
    PHONE = "PHONE"
    EMAIL = "EMAIL"
    URL = "URL"
    IP = "IP"
    MRN = "MRN"                    # local medical record number
    NHI = "NHI"                    # NZ National Health Index (§5)
    MEDICARE = "MEDICARE"          # AU Medicare card number (§5)
    IHI = "IHI"                    # AU Individual Healthcare Identifier (§5)
    POSTCODE = "POSTCODE"          # NZ/AU 4-digit
    ID = "ID"                      # generic account/device/license/other HIPAA id

class PHISpan(BaseModel):
    start: int                     # char offset, half-open [start, end)
    end: int
    type: EntityType
    text: str                      # must equal note[start:end]
    score: float = 1.0             # 1.0 for rule/gold; recognizer confidence for ner/llm
    source: Literal["rule", "ner", "llm", "gold"] = "rule"
    recognizer: str | None = None  # e.g. "NhiRecognizer", "spacy:en_core_web_lg", "llm"

class DetectionResult(BaseModel):
    text: str
    spans: list[PHISpan]           # merged, non-overlapping, sorted by start (§8)
```

**HIPAA-18 coverage map.** The enum above covers the 18 categories; the ones not given a dedicated member
(SSN, account #, certificate/license #, device id, vehicle id, biometric, full-face photo) collapse into
`ID` for text notes (photos/biometrics are out of scope for a text de-identifier — note this in the README,
do not silently claim them). Map each HIPAA category to its enum member in a table in the README.

---

## 5. Rule-based recognizers + verified checksums 🔒

`phi/detect/rules.py`. High precision is the job here. The three local IDs (NHI, Medicare, IHI) carry real
checksums — **validate the checksum, don't just pattern-match**, or precision craters on look-alike numbers.
Each is a custom Presidio `EntityRecognizer` (or a `PatternRecognizer` + a `validate_result` hook).

### 5.1 NZ NHI — old format `LLLNNNC` 🔒
Format: 3 letters + 3 digits + 1 numeric check digit (7 chars), letters exclude **I** and **O**.
Algorithm (NZ Ministry of Health / HISO 10046):
```
ALPHA = "ABCDEFGHJKLMNPQRSTUVWXYZ"          # I, O removed; value = index+1 (A=1 … Z=24)
weights = [7, 6, 5, 4, 3, 2]                 # applied to chars 1..6 (the 3 letters + 3 digits)
vals = [ALPHA.index(c)+1 for c in letters] + [int(d) for d in digits3]
checksum = sum(v*w for v, w in zip(vals, weights)) % 11
if checksum == 0:            -> INVALID
check_digit = 11 - checksum
if check_digit == 10:        -> INVALID   (cannot be expressed as a single digit)
# else the 7th char must equal check_digit
```
Regex (candidate): `\b[A-HJ-NP-Z]{3}\d{4}\b` → then run the checksum on it.
**Worked vector (commit as a unit test):** `ABC1235` → letters A,B,C = 1,2,3; digits 1,2,3;
`1·7+2·6+3·5+1·4+2·3+3·2 = 50`; `50 % 11 = 6`; `11-6 = 5` ✓. The plan's `ABC1234` fails (expects 5).
New format `LLLNNLX` (3 letters, 2 digits, 1 letter, 1 alpha check) **also exists**; its check uses a
modulus-23-or-24 base-24 scheme and **published sources disagree on the modulus**. Therefore: pattern-match
the new format `\b[A-HJ-NP-Z]{3}\d{2}[A-HJ-NP-Z]{2}\b` and emit it as `NHI`, but **flag-only — do not reject
new-format NHIs on checksum**. Pin the modulus against HISO 10046 before enforcing.
Sources: [Wikipedia NHI Number](https://en.wikipedia.org/wiki/NHI_Number),
[NZ check-digit calculator](https://nop.nz/checkdigits/),
[mcshaz NHI validator gist](https://gist.github.com/mcshaz/b41dc6bd4aa3104d54da677e2b4f6b45).

### 5.2 AU Medicare card number — 10 digits 🔒
Position 1–8 = base; position 9 = check digit; position 10 = IRN (issue number, starts at 1).
```
first digit ∈ {2,3,4,5,6}
weights = [1, 3, 7, 9, 1, 3, 7, 9]           # applied to the first 8 digits
check_digit (9th) == sum(d_i * w_i for i in 1..8) % 10
```
**Worked vector:** base `31899770` → `3·1+1·3+8·7+9·9+9·1+7·3+7·7+0·9 = 232`; `232 % 10 = 2` → check digit `2`.
Full card e.g. `3189977012` (…`2` check, `1` IRN). Regex: `\b[2-6]\d{7}\s?\d\s?\d?\b` then validate.
Source: [Australian Health Identifiers — curmi.com](https://curmi.com/australian-health-identifiers/),
[NewDoc Medicare validator](https://www.newdoc.com.au/medicare-number-validator).

### 5.3 AU IHI — 16 digits, Luhn 🔒
Prefix `800360`, then 9 individual digits, then 1 Luhn check digit (16 total). Validate with **Luhn (mod 10)**.
**Worked vector:** base `800360790627904` → Luhn check digit `9` → `8003607906279049` ✓.
Regex: `\b8003\s?60\d{2}\s?\d{4}\s?\d{4}\s?\d{2}\b` (tolerate spaces) → strip spaces → Luhn.
(Related: HPI-I `800361…`, HPI-O `800362…`, same length+Luhn — out of scope unless they appear in notes.)
Source: [curmi.com](https://curmi.com/australian-health-identifiers/),
[Luhn algorithm](https://en.wikipedia.org/wiki/Luhn_algorithm).

### 5.4 Other rule recognizers 🟡
Use Presidio's built-ins where they exist; add patterns for NZ/AU shapes.

| Type | Rule | Notes |
|---|---|---|
| `EMAIL` | Presidio `EmailRecognizer` | |
| `URL` / `IP` | Presidio `UrlRecognizer` / `IpRecognizer` | |
| `PHONE` | `phonenumbers` lib, regions `["NZ","AU"]` | covers `+64`, `021…`, `+61`, `04…`, landlines |
| `DATE` | Presidio `DateRecognizer` + `dateparser` for `dd/mm/yyyy`, `d Mon yyyy`, ISO | **day-first** (NZ/AU) — never month-first |
| `POSTCODE` | `\b\d{4}\b` **context-gated** | only near address/suburb tokens to control precision |
| `MRN` | `\b(MRN|UR|U/R)[:\s#]*\d{5,8}\b` | local; tune to corpus |
| `AGE` | `\b(\d{1,3})\s*(?:yo|y/o|years? old)\b` | emit all; eval scores **>89** as the HIPAA-strict subset |

Precision guard: postcode and bare-number rules over-fire — gate them on surrounding context tokens, and let
§8 precedence drop a `POSTCODE` that overlaps a stronger ID.

---

## 6. NER layer 🔒

`phi/detect/ner.py` — Presidio `AnalyzerEngine` with a spaCy NLP engine.

- **Model: `en_core_web_lg` (general English), NOT scispaCy.** PERSON/LOCATION/ORG are *general* entities;
  scispaCy models (`en_core_sci_*`, `en_ner_bc5cdr_md`) target diseases/chemicals/genes and **do not emit
  PERSON** — wiring them up for name detection is a category error and will tank name recall. A scispaCy
  model may be added *later, additively*, only to reduce biomedical false positives; it is not the person
  detector. (This corrects the plan's Phase 2 wording.)
- Map Presidio/spaCy labels → `EntityType`: `PERSON→PERSON`, `GPE`/`LOC`/`FAC`→`LOCATION`, `ORG`→`ORG`.
- Confidence threshold default `0.40` in `settings.py` (recall-biased — see §12 risk note). `DATE`/`PHONE`
  from Presidio's NER are dropped here in favour of the rule layer (which owns structured types, §8).

Acceptance (plan Phase 2): recall ≥ 0.90 pre-LLM on `PERSON`/`LOCATION`/`ORG` over the corpus.

---

## 7. LLM second pass 🟡 (optional)

`phi/detect/llm.py`, gated by `config.use_llm` (default False). Purpose: context-dependent PHI the rules/NER
miss — e.g. *"the patient's daughter **Jane**"*, relationship-named people, nicknames, obfuscated dates.

- Input: the note text **plus** the spans already found, so the LLM only hunts the residual.
- Structured output (Pydantic) returning `list[PHISpan]` with `source="llm"`; the model returns the exact
  substring + type, and `llm.py` resolves offsets by locating the substring (first unconsumed occurrence) —
  never trust model-supplied integer offsets.
- Model via the `LLM_MODEL` env contract (default `anthropic/claude-opus-4-8`; set
  `anthropic/claude-haiku-4-5` for cheap runs). Reuse `clinical_core.llm.complete` if present, else one
  direct LiteLLM call (§2).
- Prompt must say, in spirit: *"Identify any remaining PHI (people, dates, locations, contact details, IDs)
  not already listed. Return only the exact text and a type. Do not transform or redact."*

---

## 8. Merge & precedence 🔒

`pipeline.py` runs each enabled layer, concatenates spans, then resolves overlaps **deterministically** (the
plan says "merge overlapping spans" without a rule — this is the rule):

1. **Layer precedence for type/identity:** `rule` > `ner` > `llm`. A checksum-validated structured ID always
   wins its character range.
2. **Overlap = any character intersection.** When two spans overlap:
   - Different layers → keep the higher-precedence layer's span; **discard** the lower one (do not merge a
     `POSTCODE` into a `PERSON`, etc.).
   - Same layer, same type → **union** into one span (`start=min`, `end=max`).
   - Same layer, different type → keep the **longer** span; tie → keep higher `score`.
3. Output spans are **non-overlapping, sorted by `start`**. This invariant is asserted in `test_pipeline.py`
   and is required by every redaction strategy (§9) and the scorer (§12).

Determinism: given the same input + config + (mocked) layers, `detect()` returns byte-identical spans.

---

## 9. Redaction strategies 🔒

`phi/redact/strategies.py`. All three consume a `DetectionResult` and rewrite **right-to-left** (highest
`start` first) so earlier offsets stay valid. `StrategyName = Literal["mask","hash","surrogate"]`.

| Strategy | Output for a span of type `T`, text `x` | Properties |
|---|---|---|
| `mask` | `[REDACTED:T]` | irreversible, non-consistent |
| `hash` | `[T:<token>]` where `token = HMAC_SHA256(key, T + ":" + normalize(x))[:10]` | deterministic, **consistent** (same entity → same token within and across notes), pseudonymous |
| `surrogate` | a fake value of the *same type* (Faker), seeded by the same HMAC → stable per entity | reads like a real note; consistent per entity |

- **Hash key:** `PHI_HASH_KEY` from `.env` (required for `hash`/`surrogate`; the salt is what makes tokens
  non-reversible without it). `normalize(x)` = casefold + collapse internal whitespace, so "Jane Doe" and
  "jane  doe" map to the same token.
- **Consistency:** within a note, the same person/date must always map to the same token/surrogate (so the
  redacted note stays internally coherent). Hash and surrogate both key off `HMAC(key, type+normalize(text))`
  → free consistency. `mask` is intentionally non-consistent.
- **Surrogate by type:** `PERSON`→`faker.name()`, `DATE`→`faker.date()` (date-shift, not random), `PHONE`→
  `faker.phone_number()`, `LOCATION`→`faker.address()`, IDs→format-preserving fakes. Seed Faker with an int
  derived from the HMAC so the same entity yields the same surrogate run-to-run.
- **Idempotency 🔒:** `deidentify(deidentify(text)) == deidentify(text)`. Implement by having the detector
  **skip already-emitted tokens** — the patterns `\[REDACTED:[A-Z]+\]`, `\[[A-Z]+:[0-9a-f]{10}\]` are never
  re-detected. Covered by `test_redact.py`.

---

## 10. Public API 🔒

`phi/deidentify.py`:
```python
class DeidConfig(BaseModel):
    strategy: Literal["mask", "hash", "surrogate"] = "mask"
    use_rules: bool = True
    use_ner: bool = True
    use_llm: bool = False
    ner_threshold: float = 0.40
    regions: list[str] = ["NZ", "AU"]

class DeidResult(BaseModel):
    redacted_text: str
    spans: list[PHISpan]          # what was detected (positions in the ORIGINAL text)
    audit: list[AuditEntry]       # §11

def deidentify(text: str, config: DeidConfig = DeidConfig()) -> DeidResult: ...
```

---

## 11. Audit log & fixtures 🔒

**Audit log — counts and types only, NEVER the PHI values.** Logging the redacted strings would defeat the
purpose.
```python
class AuditEntry(BaseModel):
    type: EntityType
    count: int                    # how many spans of this type were redacted
    # no `text`, no offsets of the original values — by design
```
Emit one entry per `EntityType` present, plus a total. This is the "what was removed" record for the README.

**Fixtures (committed, chosen for coverage — not random):**

| File | Must contain |
|---|---|
| `fixtures/rich.txt` | a NZ note: PERSON ×2 (incl. a relationship-named person for the LLM case), NHI, DATE, PHONE, ADDRESS+POSTCODE, MRN |
| `fixtures/au.txt` | an AU note: Medicare number, IHI, AU phone, suburb+postcode, age > 89 |
| `fixtures/sparse.txt` | minimal PHI + a checksum **look-alike** that must NOT validate (precision trap) |

`conftest.py` loads these plus their gold spans from `labels.json`. `test_rules.py` asserts the §5 worked
vectors validate and that the look-alikes in `sparse.txt` are rejected.

---

## 12. Evaluation method 🔒 (resolves the metric ambiguity)

`phi/eval/score.py`. The plan says "recall ≥ 0.95 on identifiers" without saying *how a span counts as
caught*. Pin it:

- **Matching is span-level, type-aware, partial-overlap.** A gold span `g` is **caught** iff some predicted
  span `p` exists with `p.type == g.type` and character overlap `IoU(p, g) ≥ 0.5`
  (`IoU = |intersection| / |union|`). One predicted span matches at most one gold span (greedy by highest
  IoU). Report **two columns**: this *relaxed* (overlap) score **and** a *strict* (exact-boundary,
  `p.start==g.start and p.end==g.end`) score, so the number isn't silently inflated.
- `recall = caught_gold / total_gold`, `precision = matched_pred / total_pred`, `F1 = 2PR/(P+R)`,
  **per `EntityType`** and micro-averaged overall.
- **"Identifiers" (the ≥0.95 target) = the structured subset:** `{NHI, MEDICARE, IHI, MRN, PHONE, EMAIL,
  DATE, IP, URL, POSTCODE, ID}`. `{PERSON, LOCATION, ORG, AGE}` are quasi-identifiers, reported but held to
  the Phase-2 ≥0.90 (pre-LLM) / best-effort (post-LLM) bar, not 0.95.
- Output: a markdown table (per-type P/R/F1, relaxed+strict) written to `eval/report.md` and committed.
- **Honesty note for the README:** the corpus is ~30 self-authored synthetic notes — small, and authored by
  the same person who wrote the recognizers. Report the number as *illustrative on a synthetic set*, not a
  validation claim. (Recall > precision is the right bias here: a missed identifier is a breach; an
  over-redaction is an inconvenience.)

Acceptance command: `uv run python -m phi.eval.score` → prints + writes `eval/report.md`; identifiers
relaxed-recall ≥ 0.95.

---

## 13. Acceptance harness (what "done" runs)

| Phase | Command that proves it |
|---|---|
| 0 | `uv run pytest -q` green; `uv run python -c "from phi.corpus import load_corpus; print(len(load_corpus()))"` |
| 1 | `uv run pytest tests/test_rules.py` — §5 worked vectors validate, look-alikes rejected |
| 2 | `uv run python -m phi.cli fixtures/rich.txt --strategy mask` — names/locations caught |
| 3 | `uv run pytest tests/test_redact.py` — 3 strategies + idempotency + consistency pass |
| 4 | `uv run python -m phi.eval.score` (report, identifiers recall ≥ 0.95) · `uv run streamlit run src/phi/app.py` |

End-to-end target (plan §3): **< 3s per note** with `use_llm=False`.

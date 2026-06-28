# PHI De-identifier Evaluation Report

Corpus: 30 synthetic notes with gold spans. Matching: IoU ≥ 0.5 (relaxed), exact boundaries (strict).

## Per-type metrics

| Type | Gold | Pred | P (relaxed) | R (relaxed) | F1 (relaxed) | P (strict) | R (strict) | F1 (strict) |
|------|------|------|-------------|-------------|--------------|------------|------------|-------------|
| DATE | 29 | 29 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| EMAIL | 13 | 13 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| IHI | 18 | 18 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| LOCATION | 24 | 27 | 0.889 | 1.000 | 0.941 | 0.778 | 0.875 | 0.824 |
| MEDICARE | 18 | 18 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| MRN | 12 | 12 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| NHI | 11 | 11 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| PERSON | 31 | 29 | 1.000 | 0.935 | 0.967 | 0.966 | 0.903 | 0.933 |
| PHONE | 29 | 29 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| POSTCODE | 13 | 13 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |

## Aggregates

- **Micro overall** — P/R/F1: 0.985 / 0.990 / 0.987 (relaxed); 0.965 / 0.970 / 0.967 (strict)
- **Identifiers** — P/R/F1: 1.000 / 1.000 / 1.000 (relaxed); 1.000 / 1.000 / 1.000 (strict)

_These metrics are illustrative on a small synthetic corpus authored alongside the recognizers; they do not constitute a validation claim._


"""Span-level P/R/F1 evaluation vs. gold labels.

Contracts: CONTRACTS.md §12.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from phi.corpus import load_corpus
from phi.deidentify import deidentify
from phi.models import DeidConfig, EntityType, PHISpan

IDENTIFIER_TYPES = {
    EntityType.NHI,
    EntityType.MEDICARE,
    EntityType.IHI,
    EntityType.MRN,
    EntityType.PHONE,
    EntityType.EMAIL,
    EntityType.DATE,
    EntityType.IP,
    EntityType.URL,
    EntityType.POSTCODE,
    EntityType.ID,
}


@dataclass
class TypeScores:
    tp_relaxed: int = 0
    tp_strict: int = 0
    total_gold: int = 0
    total_pred: int = 0

    @property
    def precision_relaxed(self) -> float:
        return self.tp_relaxed / self.total_pred if self.total_pred else 0.0

    @property
    def recall_relaxed(self) -> float:
        return self.tp_relaxed / self.total_gold if self.total_gold else 0.0

    @property
    def f1_relaxed(self) -> float:
        p, r = self.precision_relaxed, self.recall_relaxed
        return 2 * p * r / (p + r) if (p + r) else 0.0

    @property
    def precision_strict(self) -> float:
        return self.tp_strict / self.total_pred if self.total_pred else 0.0

    @property
    def recall_strict(self) -> float:
        return self.tp_strict / self.total_gold if self.total_gold else 0.0

    @property
    def f1_strict(self) -> float:
        p, r = self.precision_strict, self.recall_strict
        return 2 * p * r / (p + r) if (p + r) else 0.0


def _match_greedy(
    gold_spans: list[PHISpan], pred_spans: list[PHISpan], strict: bool
) -> int:
    """Count matched gold spans. One predicted span matches at most one gold span."""
    matched_gold: set[int] = set()
    matched_pred: set[int] = set()

    # Build candidate pairs sorted by IoU descending.
    candidates = []
    for gi, g in enumerate(gold_spans):
        for pi, p in enumerate(pred_spans):
            if g.type != p.type:
                continue
            if strict and (g.start != p.start or g.end != p.end):
                continue
            iou = g.iou(p)
            if not strict and iou < 0.5:
                continue
            candidates.append((iou, gi, pi))

    candidates.sort(reverse=True)
    for _, gi, pi in candidates:
        if gi in matched_gold or pi in matched_pred:
            continue
        matched_gold.add(gi)
        matched_pred.add(pi)

    return len(matched_gold)


def score_note(gold_spans: list[PHISpan], pred_spans: list[PHISpan]) -> dict[EntityType, TypeScores]:
    """Score a single note, returning per-type scores."""
    by_type: dict[EntityType, list[PHISpan]] = defaultdict(list)
    for g in gold_spans:
        by_type[g.type].append(g)
    for p in pred_spans:
        by_type[p.type].append(p)

    scores: dict[EntityType, TypeScores] = {}
    for etype in by_type:
        golds = [s for s in by_type[etype] if s.source == "gold"]
        preds = [s for s in by_type[etype] if s.source != "gold"]
        sc = TypeScores(total_gold=len(golds), total_pred=len(preds))
        sc.tp_relaxed = _match_greedy(golds, preds, strict=False)
        sc.tp_strict = _match_greedy(golds, preds, strict=True)
        scores[etype] = sc
    return scores


def aggregate(scores_per_note: list[dict[EntityType, TypeScores]]) -> dict[EntityType, TypeScores]:
    """Micro-average per-type scores across notes."""
    aggregated: dict[EntityType, TypeScores] = defaultdict(TypeScores)
    for note_scores in scores_per_note:
        for etype, sc in note_scores.items():
            agg = aggregated[etype]
            agg.tp_relaxed += sc.tp_relaxed
            agg.tp_strict += sc.tp_strict
            agg.total_gold += sc.total_gold
            agg.total_pred += sc.total_pred
    return aggregated


def micro_average(scores: dict[EntityType, TypeScores]) -> TypeScores:
    """Micro-average across all types."""
    micro = TypeScores()
    for sc in scores.values():
        micro.tp_relaxed += sc.tp_relaxed
        micro.tp_strict += sc.tp_strict
        micro.total_gold += sc.total_gold
        micro.total_pred += sc.total_pred
    return micro


def micro_average_subset(
    scores: dict[EntityType, TypeScores], subset: set[EntityType]
) -> TypeScores:
    """Micro-average across a subset of types (e.g., identifiers)."""
    micro = TypeScores()
    for etype, sc in scores.items():
        if etype in subset:
            micro.tp_relaxed += sc.tp_relaxed
            micro.tp_strict += sc.tp_strict
            micro.total_gold += sc.total_gold
            micro.total_pred += sc.total_pred
    return micro


def _fmt(x: float) -> str:
    return f"{x:.3f}"


def build_report(scores: dict[EntityType, TypeScores]) -> str:
    """Render a markdown metrics table."""
    lines = [
        "# PHI De-identifier Evaluation Report",
        "",
        "Corpus: 30 synthetic notes with gold spans. Matching: IoU ≥ 0.5 (relaxed), exact boundaries (strict).",
        "",
        "## Per-type metrics",
        "",
        "| Type | Gold | Pred | P (relaxed) | R (relaxed) | F1 (relaxed) | P (strict) | R (strict) | F1 (strict) |",
        "|------|------|------|-------------|-------------|--------------|------------|------------|-------------|",
    ]
    for etype in sorted(scores, key=lambda t: t.value):
        sc = scores[etype]
        lines.append(
            f"| {etype.value} | {sc.total_gold} | {sc.total_pred} | "
            f"{_fmt(sc.precision_relaxed)} | {_fmt(sc.recall_relaxed)} | {_fmt(sc.f1_relaxed)} | "
            f"{_fmt(sc.precision_strict)} | {_fmt(sc.recall_strict)} | {_fmt(sc.f1_strict)} |"
        )

    micro = micro_average(scores)
    id_micro = micro_average_subset(scores, IDENTIFIER_TYPES)

    lines += [
        "",
        "## Aggregates",
        "",
        f"- **Micro overall** — P/R/F1: {_fmt(micro.precision_relaxed)} / {_fmt(micro.recall_relaxed)} / {_fmt(micro.f1_relaxed)} (relaxed); "
        f"{_fmt(micro.precision_strict)} / {_fmt(micro.recall_strict)} / {_fmt(micro.f1_strict)} (strict)",
        f"- **Identifiers** — P/R/F1: {_fmt(id_micro.precision_relaxed)} / {_fmt(id_micro.recall_relaxed)} / {_fmt(id_micro.f1_relaxed)} (relaxed); "
        f"{_fmt(id_micro.precision_strict)} / {_fmt(id_micro.recall_strict)} / {_fmt(id_micro.f1_strict)} (strict)",
        "",
        "_These metrics are illustrative on a small synthetic corpus authored alongside the recognizers; they do not constitute a validation claim._",
        "",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    root = Path(".")
    corpus = load_corpus(root)
    config = DeidConfig()

    per_note_scores: list[dict[EntityType, TypeScores]] = []
    for note in corpus:
        result = deidentify(note.text, config)
        per_note_scores.append(score_note(note.spans, result.spans))

    aggregated = aggregate(per_note_scores)
    report = build_report(aggregated)
    print(report)

    report_path = root / "eval" / "report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")

    id_micro = micro_average_subset(aggregated, IDENTIFIER_TYPES)
    print(f"Identifier relaxed recall: {_fmt(id_micro.recall_relaxed)}")
    if id_micro.recall_relaxed < 0.95:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

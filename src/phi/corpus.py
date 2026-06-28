"""Corpus loader: yields (note_id, text, gold_spans) triples from labels.json.

Contract: CONTRACTS.md §3.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import NamedTuple

from phi.models import EntityType, PHISpan


class GoldNote(NamedTuple):
    id: str
    text: str
    spans: list[PHISpan]


def load_corpus(root: Path = Path(".")) -> list[GoldNote]:
    """Load all labelled notes and assert offset/text consistency."""
    root = Path(root)
    labels_path = root / "data" / "labels.json"
    data = json.loads(labels_path.read_text(encoding="utf-8"))

    notes: list[GoldNote] = []
    for note_data in data["notes"]:
        note_id = note_data["id"]
        file_path = root / note_data["file"]
        text = file_path.read_text(encoding="utf-8")

        spans: list[PHISpan] = []
        for sp in note_data["spans"]:
            start, end = sp["start"], sp["end"]
            slice_text = text[start:end]
            if slice_text != sp["text"]:
                raise ValueError(
                    f"offset drift in {note_id}: "
                    f"labels say {sp['text']!r} but text[{start}:{end}] = {slice_text!r}"
                )
            spans.append(
                PHISpan(
                    start=start,
                    end=end,
                    type=EntityType(sp["type"]),
                    text=sp["text"],
                    source="gold",
                )
            )
        notes.append(GoldNote(id=note_id, text=text, spans=spans))
    return notes

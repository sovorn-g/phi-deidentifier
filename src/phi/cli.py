"""Command-line interface for de-identifying a single note.

Usage:
    uv run python -m phi.cli fixtures/rich.txt --strategy mask
"""

from __future__ import annotations

import argparse
from pathlib import Path

from phi.deidentify import deidentify
from phi.models import DeidConfig


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="De-identify a clinical note.")
    parser.add_argument("file", type=Path, help="Path to a text file containing the note.")
    parser.add_argument(
        "--strategy",
        choices=["mask", "hash", "surrogate"],
        default="mask",
        help="Redaction strategy (default: mask).",
    )
    parser.add_argument("--no-ner", action="store_true", help="Disable the NER layer.")
    parser.add_argument("--llm", action="store_true", help="Enable the optional LLM second pass.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    text = args.file.read_text(encoding="utf-8")
    config = DeidConfig(
        strategy=args.strategy,  # type: ignore[arg-type]
        use_ner=not args.no_ner,
        use_llm=args.llm,
    )
    result = deidentify(text, config)
    print(result.redacted_text)
    if result.audit:
        print("\n--- Audit ---")
        for entry in result.audit:
            print(f"{entry.type.value}: {entry.count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

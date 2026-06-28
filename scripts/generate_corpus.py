"""Generate the synthetic labelled corpus for phi-deidentifier.

Produces:
  - data/notes/note_001.txt ... note_030.txt
  - data/labels.json
  - fixtures/rich.txt, fixtures/au.txt, fixtures/sparse.txt

All offsets are character-level, half-open [start, end).
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from pathlib import Path

import phonenumbers
from faker import Faker

# ---------------------------------------------------------------------------
# ID generators with valid checksums
# ---------------------------------------------------------------------------

def nhi_old_check(text: str) -> bool:
    """Validate old-format NZ NHI LLLNNNC."""
    alpha = "ABCDEFGHJKLMNPQRSTUVWXYZ"
    if len(text) != 7:
        return False
    letters, digits, check = text[:3], text[3:6], int(text[6])
    vals = [alpha.index(c) + 1 for c in letters] + [int(d) for d in digits]
    weights = [7, 6, 5, 4, 3, 2]
    checksum = sum(v * w for v, w in zip(vals, weights, strict=False)) % 11
    if checksum == 0:
        return False
    expected = 11 - checksum
    if expected == 10:
        return False
    return check == expected


def generate_nhi_old(rng: random.Random) -> str:
    alpha = "ABCDEFGHJKLMNPQRSTUVWXYZ"
    letters = [rng.choice(alpha) for _ in range(3)]
    digits = [str(rng.randint(0, 9)) for _ in range(3)]
    vals = [alpha.index(c) + 1 for c in letters] + [int(d) for d in digits]
    weights = [7, 6, 5, 4, 3, 2]
    checksum = sum(v * w for v, w in zip(vals, weights, strict=False)) % 11
    if checksum == 0:
        # tweak last digit to avoid invalid checksum 0
        vals[-1] = (vals[-1] + 1) % 10
        digits[-1] = str(vals[-1])
        checksum = sum(v * w for v, w in zip(vals, weights, strict=False)) % 11
    expected = 11 - checksum
    if expected == 10:
        # tweak to avoid check digit 10
        vals[-1] = (vals[-1] + 1) % 10
        digits[-1] = str(vals[-1])
        checksum = sum(v * w for v, w in zip(vals, weights, strict=False)) % 11
        expected = 11 - checksum
    return "".join(letters) + "".join(digits) + str(expected)


def generate_medicare(rng: random.Random) -> str:
    """Generate a valid 10-digit AU Medicare number (base + check + IRN)."""
    first = str(rng.randint(2, 6))
    rest = [str(rng.randint(0, 9)) for _ in range(7)]
    base_digits = [int(first)] + [int(d) for d in rest]
    weights = [1, 3, 7, 9, 1, 3, 7, 9]
    check = sum(d * w for d, w in zip(base_digits, weights, strict=False)) % 10
    irn = rng.randint(1, 5)
    return f"{first}{''.join(rest)}{check}{irn}"


def luhn_check_digit(digits: list[int]) -> int:
    total = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 0:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return (10 - (total % 10)) % 10


def generate_ihi(rng: random.Random) -> str:
    """Generate a valid 16-digit AU IHI (prefix 800360 + 9 digits + Luhn)."""
    prefix = [8, 0, 0, 3, 6, 0]
    body = [rng.randint(0, 9) for _ in range(9)]
    digits = prefix + body
    check = luhn_check_digit(digits)
    return "".join(map(str, digits)) + str(check)


def _valid_phone(candidate: str, regions: list[str]) -> bool:
    for region in regions:
        try:
            parsed = phonenumbers.parse(candidate, region)
            if phonenumbers.is_valid_number(parsed):
                return True
        except phonenumbers.NumberParseException:
            continue
    return False


def generate_phone(rng: random.Random, region: str) -> str:
    """Generate a phone number that ``phonenumbers`` considers valid."""
    if region == "nz":
        candidates = [f"021 {rng.randint(100, 999)} {rng.randint(1000, 9999)}"]
    elif region == "au":
        candidates = [
            f"04{rng.randint(10, 99)} {rng.randint(100, 999)} {rng.randint(100, 999)}",
            f"+61 4{rng.randint(10, 99)} {rng.randint(100, 999)} {rng.randint(100, 999)}",
        ]
    else:
        raise ValueError(region)

    for _ in range(50):
        candidate = rng.choice(candidates)
        if _valid_phone(candidate, [region.upper()]):
            return candidate
    # Fallback: use a known-valid shape if random choices keep failing.
    return "021 000 0000" if region == "nz" else "0412 345 678"


# ---------------------------------------------------------------------------
# Note builder
# ---------------------------------------------------------------------------

@dataclass
class Segment:
    text: str
    label: str | None = None


@dataclass
class Note:
    id: str
    segments: list[Segment] = field(default_factory=list)

    def render(self) -> tuple[str, list[dict]]:
        text_parts = []
        spans = []
        offset = 0
        for seg in self.segments:
            text_parts.append(seg.text)
            if seg.label:
                spans.append(
                    {
                        "start": offset,
                        "end": offset + len(seg.text),
                        "type": seg.label,
                        "text": seg.text,
                    }
                )
            offset += len(seg.text)
        return "".join(text_parts), spans


def lit(s: str) -> Segment:
    return Segment(text=s, label=None)


def phi(text: str, label: str) -> Segment:
    return Segment(text=text, label=label)


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------

def make_rich_note(faker: Faker, rng: random.Random) -> Note:
    """NZ-style note with a broad mix of PHI."""
    nhi = generate_nhi_old(rng)
    phone = generate_phone(rng, "nz")
    date = faker.date_of_birth(minimum_age=25, maximum_age=85).strftime("%d/%m/%Y")
    patient = faker.name()
    daughter = faker.name()
    address = f"{rng.randint(1, 999)} {faker.street_name()}, {faker.city()}"
    postcode = f"{rng.randint(1000, 9999)}"
    mrn = f"{rng.randint(100000, 999999)}"

    note = Note(id="note_001")
    note.segments = [
        lit("Patient: "),
        phi(patient, "PERSON"),
        lit("\nNHI: "),
        phi(nhi, "NHI"),
        lit("\nDOB: "),
        phi(date, "DATE"),
        lit("\nPhone: "),
        phi(phone, "PHONE"),
        lit("\nAddress: "),
        phi(address, "LOCATION"),
        lit(", "),
        phi(postcode, "POSTCODE"),
        lit("\nMRN: "),
        phi(mrn, "MRN"),
        lit("\n\n"),
        lit("Presented with chest pain. Daughter "),
        phi(daughter, "PERSON"),
        lit(" accompanied patient. Plan for follow-up in 2 weeks."),
    ]
    return note


def make_au_note(faker: Faker, rng: random.Random) -> Note:
    """AU-style note with Medicare, IHI, and age > 89."""
    patient = faker.name()
    medicare = generate_medicare(rng)
    ihi = generate_ihi(rng)
    phone = f"04{rng.randint(10, 99)} {rng.randint(100, 999)} {rng.randint(100, 999)}"
    suburb = faker.city()
    postcode = f"{rng.randint(2000, 2999)}"
    age = rng.randint(90, 99)
    date = faker.date_of_birth(minimum_age=age, maximum_age=age).strftime("%d/%m/%Y")

    note = Note(id="note_002")
    note.segments = [
        lit("Name: "),
        phi(patient, "PERSON"),
        lit("\nMedicare: "),
        phi(medicare, "MEDICARE"),
        lit("\nIHI: "),
        phi(ihi, "IHI"),
        lit("\nPhone: "),
        phi(phone, "PHONE"),
        lit("\nAddress: 12 Station St, "),
        phi(suburb, "LOCATION"),
        lit(" "),
        phi(postcode, "POSTCODE"),
        lit(f"\n{age}-year-old patient reviewed in clinic. DOB "),
        phi(date, "DATE"),
        lit(". Stable."),
    ]
    return note


def make_sparse_note(faker: Faker, rng: random.Random) -> Note:
    """Minimal PHI plus a checksum look-alike that must NOT validate."""
    patient = faker.name()
    # ABC1234 is pattern-valid but checksum-invalid (expects 5)
    bad_nhi = "ABC1234"
    # Mention it in prose as a "possible NHI" so precision trap is explicit
    note = Note(id="note_003")
    note.segments = [
        lit("Patient "),
        phi(patient, "PERSON"),
        lit(" has no known NHI on file. Previous entry "),
        lit(bad_nhi),
        lit(" failed validation."),
    ]
    return note


def make_generic_note(idx: int, faker: Faker, rng: random.Random) -> Note:
    """Generate a varied synthetic note with a handful of PHI spans."""
    templates = [
        ("nz", 0.6),
        ("au", 0.4),
    ]
    region = rng.choices([t[0] for t in templates], weights=[t[1] for t in templates])[0]

    note = Note(id=f"note_{idx:03d}")
    segments: list[Segment] = []

    patient = faker.name()
    segments += [lit("Patient: "), phi(patient, "PERSON"), lit("\n")]

    if region == "nz":
        nhi = generate_nhi_old(rng)
        segments += [lit("NHI: "), phi(nhi, "NHI"), lit("\n")]
        phone = generate_phone(rng, "nz")
        segments += [lit("Contact: "), phi(phone, "PHONE"), lit("\n")]
    elif region == "au":
        medicare = generate_medicare(rng)
        ihi = generate_ihi(rng)
        phone = generate_phone(rng, "au")
        segments += [
            lit("Medicare: "),
            phi(medicare, "MEDICARE"),
            lit("\nIHI: "),
            phi(ihi, "IHI"),
            lit("\nContact: "),
            phi(phone, "PHONE"),
            lit("\n"),
        ]
    else:
        raise RuntimeError("unreachable")

    dob = faker.date_of_birth(minimum_age=18, maximum_age=95).strftime("%d/%m/%Y")
    segments += [lit("DOB: "), phi(dob, "DATE"), lit("\n")]

    if rng.random() < 0.6:
        email = faker.email()
        segments += [lit("Email: "), phi(email, "EMAIL"), lit("\n")]

    if rng.random() < 0.4:
        mrn = f"{rng.randint(100000, 999999)}"
        segments += [lit("MRN: "), phi(mrn, "MRN"), lit("\n")]

    if rng.random() < 0.5:
        city = faker.city()
        postcode = f"{rng.randint(1000, 9999)}"
        address = f"{rng.randint(1, 999)} {faker.street_name()}"
        segments += [
            lit("Address: "),
            phi(address, "LOCATION"),
            lit(", "),
            phi(city, "LOCATION"),
            lit(" "),
            phi(postcode, "POSTCODE"),
            lit("\n"),
        ]

    # clinical prose
    sentences = [
        "Reviewed in clinic today.",
        "No acute concerns.",
        "Continue current medications.",
        "Plan for routine follow-up.",
        "Patient advised to call if symptoms worsen.",
    ]
    rng.shuffle(sentences)
    segments += [lit(" ".join(sentences))]

    note.segments = segments
    return note


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    root = Path(__file__).resolve().parent.parent
    rng = random.Random(42)
    faker = Faker("en_NZ")
    faker.seed_instance(42)

    notes_dir = root / "data" / "notes"
    notes_dir.mkdir(parents=True, exist_ok=True)
    fixtures_dir = root / "fixtures"
    fixtures_dir.mkdir(parents=True, exist_ok=True)

    all_notes: list[Note] = []

    # Fixtures first
    rich = make_rich_note(faker, rng)
    au = make_au_note(faker, rng)
    sparse = make_sparse_note(faker, rng)
    all_notes.extend([rich, au, sparse])

    fixture_names = {"note_001": "rich.txt", "note_002": "au.txt", "note_003": "sparse.txt"}
    for note in [rich, au, sparse]:
        text, spans = note.render()
        (fixtures_dir / fixture_names[note.id]).write_text(text, encoding="utf-8")

    # Additional notes
    for i in range(4, 31):
        all_notes.append(make_generic_note(i, faker, rng))

    labels = {"version": "1", "notes": []}
    for note in all_notes:
        text, spans = note.render()
        # assert offsets
        for sp in spans:
            assert text[sp["start"] : sp["end"]] == sp["text"], f"offset mismatch in {note.id}"
        (notes_dir / f"{note.id}.txt").write_text(text, encoding="utf-8")
        labels["notes"].append(
            {
                "id": note.id,
                "file": f"data/notes/{note.id}.txt",
                "spans": spans,
            }
        )

    (root / "data" / "labels.json").write_text(
        json.dumps(labels, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    print(f"Generated {len(all_notes)} notes + labels.json")


if __name__ == "__main__":
    main()

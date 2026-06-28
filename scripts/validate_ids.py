"""Quick validation of generated checksum IDs."""

import json


def nhi_old_valid(text: str) -> bool:
    alpha = "ABCDEFGHJKLMNPQRSTUVWXYZ"
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


def medicare_valid(text: str) -> bool:
    digits = [int(c) for c in text]
    weights = [1, 3, 7, 9, 1, 3, 7, 9]
    return digits[8] == sum(d * w for d, w in zip(digits[:8], weights, strict=False)) % 10


def luhn_valid(text: str) -> bool:
    digits = [int(c) for c in text]
    total = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def main() -> None:
    labels = json.loads(open("data/labels.json").read())
    for note in labels["notes"]:
        for sp in note["spans"]:
            text = sp["text"]
            t = sp["type"]
            if t == "NHI":
                assert nhi_old_valid(text), f"bad NHI {text} in {note['id']}"
            elif t == "MEDICARE":
                assert medicare_valid(text), f"bad Medicare {text} in {note['id']}"
            elif t == "IHI":
                assert luhn_valid(text), f"bad IHI {text} in {note['id']}"
    print("All generated checksum IDs validate.")


if __name__ == "__main__":
    main()

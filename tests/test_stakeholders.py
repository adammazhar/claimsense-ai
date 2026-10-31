"""Both RACI tables have exactly one A per row, and the deliverable RACI covers what the checklist asks."""

from __future__ import annotations

import re
from pathlib import Path

DOC = (Path(__file__).resolve().parent.parent / "docs" / "engagement" / "stakeholders.md").read_text(encoding="utf-8")


def table_after(heading: str) -> tuple[list[str], list[list[str]]]:
    rows: list[str] = []
    for line in DOC.split(heading, 1)[1].splitlines():
        if line.startswith("|"):
            rows.append(line)
        elif rows:
            break  # end of the first table under this heading
    cells = [[c.strip() for c in row.strip("|").split("|")] for row in rows]
    return cells[0], [r for r in cells[2:]]  # header, body (skip the --- row)


def accountable(row: list[str]) -> int:
    return sum(1 for cell in row[1:] if re.search(r"\bA\b", cell))


def test_one_accountable_per_row_in_both_tables() -> None:
    for heading in ("## RACI by deliverable", "## RACI by decision"):
        _, body = table_after(heading)
        assert body, heading
        for row in body:
            assert accountable(row) == 1, f"{heading}: '{row[0]}' has {accountable(row)} A"


def test_deliverable_raci_covers_the_week_1_to_5_deliverables() -> None:
    header, body = table_after("## RACI by deliverable")
    rows = {r[0]: dict(zip(header, r)) for r in body}
    for deliverable in ("Engagement charter", "Architecture diagram", "Auth model and RBAC",
                        "Agent pipeline build", "Eval gate threshold", "Go-live decision"):
        assert deliverable in rows, deliverable
    assert "A" in rows["Auth model and RBAC"]["Security"]
    assert {r["Week"] for r in rows.values()} >= {"1", "2", "3", "5"}


def test_every_stakeholder_has_a_type() -> None:
    _, body = table_after("## Power map")
    for row in body:
        assert re.search(r"\*\*(user|blocker|enabler)\*\*", row[1]), row[0]

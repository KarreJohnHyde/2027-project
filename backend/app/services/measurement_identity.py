"""Source occurrences versus distinct measurements.

Laboratory packets often reprint the same result on several pages, and the same report
may be uploaded twice. Each printing is a source occurrence; it is not a new observation.
An occurrence duplicates an earlier one when the analyte, documented value, unit and
result operator agree and either both carry the same documented date or, undated, both
come from the same uploaded file. Undated values from different files are never merged:
nothing establishes that they are the same specimen.

Nothing is deleted or rewritten: every occurrence keeps its own source span, page and
file, and readers decide whether to count the canonical (first) occurrence only.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable, Optional

from app.models.entities import MedicalMeasurement


def occurrence_key(row: MedicalMeasurement) -> tuple[Any, ...]:
    dated = row.documented_date or None
    return (
        row.name,
        round(float(row.value), 9),
        row.unit,
        row.result_operator or "=",
        ("date", dated) if dated else ("file", row.source_file_id),
    )


def duplicate_map(rows: Iterable[MedicalMeasurement]) -> dict[int, int]:
    """Measurement id -> id of the earliest occurrence it repeats (canonical rows are absent)."""
    first: dict[tuple[Any, ...], int] = {}
    duplicates: dict[int, int] = {}
    for row in sorted(rows, key=lambda item: item.id):
        key = occurrence_key(row)
        if key in first:
            duplicates[row.id] = first[key]
        else:
            first[key] = row.id
    return duplicates


def occurrences(rows: Iterable[MedicalMeasurement]) -> dict[int, list[dict[str, Optional[int]]]]:
    """Canonical measurement id -> every source occurrence (file and page), itself first."""
    ordered = sorted(rows, key=lambda item: item.id)
    duplicates = duplicate_map(ordered)
    grouped: dict[int, list[dict[str, Optional[int]]]] = defaultdict(list)
    for row in ordered:
        grouped[duplicates.get(row.id, row.id)].append({
            "measurement_id": row.id, "source_file_id": row.source_file_id, "source_page": row.source_page,
        })
    return dict(grouped)

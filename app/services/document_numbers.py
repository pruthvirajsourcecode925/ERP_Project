from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session


def generate_sequential_document_number(
    db: Session,
    *,
    field,
    prefix: str,
    year: int | None = None,
    width: int = 4,
) -> str:
    current_year = year or datetime.now(timezone.utc).year
    prefix_token = f"{prefix}-{current_year}-"
    existing_values = list(
        db.scalars(
            select(field).where(field.like(f"{prefix_token}%"))
        )
    )

    max_sequence = 0
    existing_set = set(existing_values)
    for value in existing_values:
        if not value or not str(value).startswith(prefix_token):
            continue

        suffix = str(value)[len(prefix_token):]
        if suffix.isdigit():
            max_sequence = max(max_sequence, int(suffix))

    next_sequence = max_sequence + 1
    while True:
        candidate = f"{prefix_token}{next_sequence:0{width}d}"
        if candidate not in existing_set:
            return candidate
        next_sequence += 1
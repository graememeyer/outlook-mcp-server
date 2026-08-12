"""
Date parsing and Graph ``$filter`` construction for message queries.

Graph wants an ISO-8601 UTC literal in filters (``receivedDateTime ge
2026-01-01T00:00:00Z``). Callers are allowed to be a lot looser than that: a
plain date, a full timestamp, or a relative shorthand like ``90d`` / ``6m``.
"""

import re
from datetime import datetime, timedelta, timezone
from typing import List, Optional

# Folders where the meaningful timestamp is when *we* sent the message, not
# when it arrived. receivedDateTime is populated on sent items too, but it
# tracks delivery rather than authorship and is occasionally null on items
# moved between mailboxes.
_SENT_LIKE_FOLDERS = {"sentitems", "drafts"}

_RELATIVE_RE = re.compile(r"^(\d+)\s*([dwmy])$", re.IGNORECASE)

_RELATIVE_DAYS = {"d": 1, "w": 7, "m": 30, "y": 365}


class DateParseError(ValueError):
    """Raised when a caller-supplied date string can't be interpreted."""


def date_field_for_folder(folder_id: str) -> str:
    """Return the Graph date property that makes sense for a folder."""
    return (
        "sentDateTime"
        if (folder_id or "").strip().lower() in _SENT_LIKE_FOLDERS
        else "receivedDateTime"
    )


def parse_datetime(value: str, *, end_of_day: bool = False) -> datetime:
    """Parse a caller-supplied date into a timezone-aware UTC datetime.

    Accepts ``YYYY-MM-DD``, any ISO-8601 timestamp (with ``Z`` or an offset),
    and relative shorthand such as ``30d``, ``6m``, ``1y`` meaning "that long
    ago". ``end_of_day`` pushes a bare date to 23:59:59 so that a caller
    passing the same day as both bounds gets that whole day.
    """
    if not value:
        raise DateParseError("Empty date value")

    raw = value.strip()

    relative = _RELATIVE_RE.match(raw)
    if relative:
        amount = int(relative.group(1))
        unit = relative.group(2).lower()
        return datetime.now(timezone.utc) - timedelta(days=amount * _RELATIVE_DAYS[unit])

    iso = raw.replace("Z", "+00:00") if raw.endswith("Z") else raw
    try:
        parsed = datetime.fromisoformat(iso)
    except ValueError as exc:
        raise DateParseError(
            f"Could not parse date {value!r}. Use YYYY-MM-DD, an ISO-8601 "
            f"timestamp, or relative shorthand like '90d'."
        ) from exc

    # A bare date parses to midnight; only then does end_of_day apply.
    is_bare_date = len(raw) == 10 and parsed.time() == datetime.min.time()
    if end_of_day and is_bare_date:
        parsed = parsed.replace(hour=23, minute=59, second=59)

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def to_graph_literal(dt: datetime) -> str:
    """Render a datetime as the UTC literal Graph expects in a ``$filter``."""
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_date_filter(
    date_field: str,
    received_after: Optional[str] = None,
    received_before: Optional[str] = None,
) -> List[str]:
    """Build the ``$filter`` clauses for an optional date window.

    Returns a list of clause strings (possibly empty) for the caller to AND
    together with any other filters it has.
    """
    clauses: List[str] = []
    if received_after:
        clauses.append(
            f"{date_field} ge {to_graph_literal(parse_datetime(received_after))}"
        )
    if received_before:
        clauses.append(
            f"{date_field} le "
            f"{to_graph_literal(parse_datetime(received_before, end_of_day=True))}"
        )
    return clauses


def combine_filters(*clauses) -> Optional[str]:
    """AND together any non-empty filter clauses, flattening nested lists."""
    flat: List[str] = []
    for clause in clauses:
        if not clause:
            continue
        if isinstance(clause, (list, tuple)):
            flat.extend(c for c in clause if c)
        else:
            flat.append(clause)
    return " and ".join(flat) if flat else None


__all__ = [
    "DateParseError",
    "build_date_filter",
    "combine_filters",
    "date_field_for_folder",
    "parse_datetime",
    "to_graph_literal",
]

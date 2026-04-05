"""Minimal cron expression parser for recurring jobs.

Supports standard 5-field cron: minute hour day_of_month month day_of_week
Supports: numbers, wildcards (*), ranges (1-5), steps (*/15), lists (1,3,5)
"""

from datetime import datetime, timedelta


def _parse_field(field: str, min_val: int, max_val: int) -> set[int]:
    values = set()
    for part in field.split(","):
        if "/" in part:
            base, step = part.split("/", 1)
            step = int(step)
            if base == "*":
                start = min_val
            elif "-" in base:
                start = int(base.split("-")[0])
            else:
                start = int(base)
            values.update(range(start, max_val + 1, step))
        elif "-" in part:
            lo, hi = part.split("-", 1)
            values.update(range(int(lo), int(hi) + 1))
        elif part == "*":
            values.update(range(min_val, max_val + 1))
        else:
            values.add(int(part))
    return values


def _parse_cron(
    expression: str,
) -> tuple[set[int], set[int], set[int], set[int], set[int]]:
    parts = expression.strip().split()
    if len(parts) != 5:
        raise ValueError(f"Expected 5 cron fields, got {len(parts)}: {expression!r}")

    minutes = _parse_field(parts[0], 0, 59)
    hours = _parse_field(parts[1], 0, 23)
    days = _parse_field(parts[2], 1, 31)
    months = _parse_field(parts[3], 1, 12)
    weekdays = _parse_field(parts[4], 0, 6)  # 0=Monday in Python (Sun=6)

    return minutes, hours, days, months, weekdays


def next_cron_time(expression: str, after: datetime) -> datetime:
    """Return the next datetime matching the cron expression after `after`."""
    minutes, hours, days, months, weekdays = _parse_cron(expression)

    # Start from the next minute
    candidate = after.replace(second=0, microsecond=0) + timedelta(minutes=1)

    # Safety limit to prevent infinite loops
    for _ in range(366 * 24 * 60):
        if (
            candidate.month in months
            and candidate.day in days
            and candidate.weekday() in weekdays
            and candidate.hour in hours
            and candidate.minute in minutes
        ):
            return candidate
        candidate += timedelta(minutes=1)

    raise ValueError(
        f"Could not find next run time for cron expression: {expression!r}"
    )

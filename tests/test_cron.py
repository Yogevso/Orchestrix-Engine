"""Unit tests for the cron expression parser."""

import pytest
from datetime import datetime, timezone

from orchestrix.cron import next_cron_time


def test_every_minute():
    after = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    result = next_cron_time("* * * * *", after)
    assert result.minute == 1


def test_specific_minute():
    after = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    result = next_cron_time("30 * * * *", after)
    assert result.minute == 30
    assert result.hour == 0


def test_every_5_minutes():
    after = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    result = next_cron_time("*/5 * * * *", after)
    assert result.minute == 5


def test_specific_hour():
    after = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    result = next_cron_time("0 9 * * *", after)
    assert result.hour == 9
    assert result.minute == 0


def test_invalid_cron_raises():
    with pytest.raises(ValueError):
        next_cron_time("bad", datetime.now(timezone.utc))

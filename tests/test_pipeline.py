from datetime import UTC, datetime

from gridpulse.pipeline import as_utc, daily_window


def test_daily_window_covers_lookback_and_today():
    now = datetime(2025, 3, 10, 14, 30, tzinfo=UTC)
    start, end = daily_window(3, now)
    assert end == datetime(2025, 3, 11, tzinfo=UTC)
    assert start == datetime(2025, 3, 7, tzinfo=UTC)


def test_as_utc_handles_naive_and_aware():
    assert as_utc(datetime(2025, 1, 1)).tzinfo == UTC
    assert as_utc(datetime(2025, 1, 1, tzinfo=UTC)) == datetime(2025, 1, 1, tzinfo=UTC)

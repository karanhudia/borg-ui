from datetime import datetime, timezone

from app.utils.archive_job_metadata import _parse_archive_time


class TestParseArchiveTime:
    def test_offset_string_converts_to_naive_utc(self):
        parsed = _parse_archive_time({"start": "2026-04-27T03:00:06-04:00"})

        assert parsed == datetime(2026, 4, 27, 7, 0, 6)

    def test_naive_string_is_read_as_utc(self):
        # Machine-parsed listings render under TZ=UTC, so a naive value that
        # reaches enrichment un-normalized is UTC wall clock.
        parsed = _parse_archive_time({"time": "2026-07-01T03:00:00"})

        assert parsed == datetime(2026, 7, 1, 3, 0, 0)

    def test_unix_epoch_is_accepted(self):
        # The previous direct fromisoformat dropped numeric epochs.
        parsed = _parse_archive_time({"time": 1767225600})

        assert parsed == datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc).replace(
            tzinfo=None
        )

    def test_epoch_zero_start_is_not_skipped(self):
        # 0 is falsy but a valid epoch - it must win over the "time" fallback.
        parsed = _parse_archive_time({"start": 0, "time": "2026-07-01T03:00:00"})

        assert parsed == datetime(1970, 1, 1, 0, 0, 0)

    def test_datetime_instances_are_coerced_to_naive_utc(self):
        aware = datetime(2026, 4, 27, 3, 0, 6, tzinfo=timezone.utc)

        assert _parse_archive_time({"start": aware}) == datetime(2026, 4, 27, 3, 0, 6)

    def test_junk_and_missing_values_return_none(self):
        assert _parse_archive_time({"time": "not-a-timestamp"}) is None
        assert _parse_archive_time({}) is None
        assert _parse_archive_time({"time": None}) is None

    def test_boolean_values_are_rejected(self):
        # bool is an int subclass - True must not parse as epoch 1.
        assert _parse_archive_time({"start": True}) is None
        assert _parse_archive_time({"start": False}) is None

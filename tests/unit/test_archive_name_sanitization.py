from datetime import datetime, timezone
from unittest.mock import patch

from app.utils.archive_names import sanitize_archive_component, build_archive_name

_FROZEN_UTC = datetime(2026, 1, 2, 3, 4, 5, 678000, tzinfo=timezone.utc)


# ==========================================
# sanitize_archive_component Tests
# ==========================================


class TestSanitizeArchiveComponent:
    def test_space_replaced_with_hyphen(self):
        """Single space becomes a hyphen"""
        assert sanitize_archive_component("my job") == "my-job"

    def test_forward_slash_replaced_with_hyphen(self):
        """Forward slash becomes a hyphen"""
        assert sanitize_archive_component("my/job") == "my-job"

    def test_backslash_replaced_with_hyphen(self):
        """Backslash becomes a hyphen"""
        assert sanitize_archive_component("my\\job") == "my-job"

    def test_consecutive_delimiters_collapse(self):
        """Consecutive whitespace/slashes collapse to a single hyphen"""
        assert sanitize_archive_component("a  b//c") == "a-b-c"

    def test_already_clean_name_unchanged(self):
        """Names without unsafe chars are returned as-is"""
        assert sanitize_archive_component("clean-name") == "clean-name"

    def test_mixed_delimiters_collapse(self):
        """Mix of spaces and slashes in a run collapse to one hyphen"""
        assert sanitize_archive_component("a/ b") == "a-b"

    def test_empty_string(self):
        """Empty string stays empty"""
        assert sanitize_archive_component("") == ""


# ==========================================
# build_archive_name Tests
# ==========================================


class TestBuildArchiveName:
    def test_default_no_template_no_repo(self):
        """Without template and without repo_name: job-timestamp"""
        result = build_archive_name(
            job_name="my job",
            repo_name=None,
            template=None,
            timestamp="2025-01-01T12:00:00",
        )
        assert result == "my-job-2025-01-01T12:00:00"

    def test_default_no_template_with_repo(self):
        """Without template and with repo_name: job-repo-timestamp"""
        result = build_archive_name(
            job_name="my job",
            repo_name="my/repo",
            template=None,
            timestamp="2025-01-01T12:00:00",
        )
        assert result == "my-job-my-repo-2025-01-01T12:00:00"

    def test_template_with_job_repo_now(self):
        """Template with {job_name}, {repo_name}, {now} resolved and sanitized"""
        result = build_archive_name(
            job_name="my job",
            repo_name="repo",
            template="{job_name}-{repo_name}-{now}",
            timestamp="2025-01-01T12:00:00",
        )
        assert result == "my-job-repo-2025-01-01T12:00:00"

    def test_template_with_plan_name_alias(self):
        """Backup plan templates can use {plan_name} as a job-name alias."""
        result = build_archive_name(
            job_name="nightly plan",
            repo_name="repo",
            template="{plan_name}-{repo_name}-{now}",
            timestamp="2025-01-01T12:00:00",
        )
        assert result == "nightly-plan-repo-2025-01-01T12:00:00"

    def test_template_without_repo_placeholder(self):
        """Template without {repo_name} placeholder — no substitution attempted"""
        result = build_archive_name(
            job_name="clean",
            repo_name="repo",
            template="{job_name}-backup",
            timestamp="2025-01-01T12:00:00",
        )
        assert result == "clean-backup"

    def test_template_sanitizes_job_name(self):
        """Job name with spaces sanitized before template substitution"""
        result = build_archive_name(
            job_name="my job",
            repo_name=None,
            template="{job_name}-custom",
            timestamp="2025-01-01T12:00:00",
        )
        assert result == "my-job-custom"

    def test_template_sanitizes_repo_name(self):
        """Repo name with slashes sanitized before template substitution"""
        result = build_archive_name(
            job_name="backup",
            repo_name="org/repo",
            template="{job_name}-{repo_name}-{now}",
            timestamp="2025-01-01T12:00:00",
        )
        assert result == "backup-org-repo-2025-01-01T12:00:00"

    def test_template_with_date_time_unix(self):
        """Template with {date}, {time}, {timestamp} placeholders"""
        result = build_archive_name(
            job_name="backup",
            repo_name="repo",
            template="{job_name}-{date}-{time}-{timestamp}",
            timestamp="2025-01-01T12:00:00",
            date="2025-01-01",
            time_str="12:00:00",
            unix_timestamp="1735732800",
        )
        assert result == "backup-2025-01-01-12:00:00-1735732800"

    def test_clean_name_unchanged(self):
        """Already clean names pass through without modification"""
        result = build_archive_name(
            job_name="clean",
            repo_name="repo",
            template=None,
            timestamp="2025-01-01T12:00:00",
        )
        assert result == "clean-repo-2025-01-01T12:00:00"

    def test_template_final_sanitization(self):
        """Any remaining unsafe chars in custom template text are sanitized"""
        result = build_archive_name(
            job_name="backup",
            repo_name=None,
            template="my backup/{job_name}",
            timestamp="2025-01-01T12:00:00",
        )
        assert result == "my-backup-backup"

    def test_stable_series_default_no_template_with_repo(self):
        """Stable series names omit the timestamp while keeping job/repo context."""
        result = build_archive_name(
            job_name="my job",
            repo_name="my/repo",
            template=None,
            timestamp="2025-01-01T12:00:00",
            stable_series=True,
        )
        assert result == "my-job-my-repo"

    def test_stable_series_template_removes_time_placeholders(self):
        """Stable Borg 2 series names strip time placeholders from templates."""
        result = build_archive_name(
            job_name="nightly plan",
            repo_name="primary repo",
            template="{plan_name}-{repo_name}-{now}",
            timestamp="2025-01-01T12:00:00",
            date="2025-01-01",
            time_str="12:00:00",
            unix_timestamp="1735732800",
            stable_series=True,
        )
        assert result == "nightly-plan-primary-repo"

    def test_stable_series_template_removes_formatted_borg_time_placeholders(self):
        """Stable Borg 2 series names strip Borg runtime time placeholders too."""
        result = build_archive_name(
            job_name="root backup",
            repo_name=None,
            template="{job_name}-{now:%Y-%m-%d}",
            timestamp="2025-01-01T12:00:00",
            stable_series=True,
        )
        assert result == "root-backup"

    def test_stable_series_template_falls_back_when_only_time_placeholders(self):
        """A time-only template falls back to the stable default name."""
        result = build_archive_name(
            job_name="nightly plan",
            repo_name="primary repo",
            template="{now}",
            timestamp="2025-01-01T12:00:00",
            stable_series=True,
        )
        assert result == "nightly-plan-primary-repo"


class TestUtcnowPlaceholder:
    def test_utcnow_expands_to_the_exact_utc_instant(self):
        # Frozen clock: assert the exact value, not just its shape - a
        # local-clock implementation would produce a different string.
        with patch("app.utils.archive_names.datetime") as mock_dt:
            mock_dt.now.return_value = _FROZEN_UTC
            result = build_archive_name(
                job_name="my job",
                repo_name=None,
                template="{job_name}-{utcnow}",
                timestamp="2025-01-01T12:00:00",
            )
        # A regression to datetime.now() without timezone.utc must not pass.
        mock_dt.now.assert_called_once_with(timezone.utc)
        assert result == "my-job-2026-01-02T03:04:05.678"

    def test_utcnow_and_now_can_coexist(self):
        with patch("app.utils.archive_names.datetime") as mock_dt:
            mock_dt.now.return_value = _FROZEN_UTC
            result = build_archive_name(
                job_name="job",
                repo_name=None,
                template="{now}-vs-{utcnow}",
                timestamp="2025-01-01T12:00:00",
            )
        mock_dt.now.assert_called_once_with(timezone.utc)
        assert result == "2025-01-01T12:00:00-vs-2026-01-02T03:04:05.678"

    def test_formatted_utcnow_passes_through_for_borg(self):
        # {utcnow:%Y-%m-%d} is borg's own placeholder syntax - left for borg
        # to expand, exactly like formatted {now:...} today.
        result = build_archive_name(
            job_name="job",
            repo_name=None,
            template="{job_name}-{utcnow:%Y-%m-%d}",
            timestamp="2025-01-01T12:00:00",
        )
        assert result == "job-{utcnow:%Y-%m-%d}"

    def test_stable_series_strips_utcnow(self):
        result = build_archive_name(
            job_name="job",
            repo_name=None,
            template="{job_name}-{utcnow}",
            timestamp="2025-01-01T12:00:00",
            stable_series=True,
        )
        assert result == "job"

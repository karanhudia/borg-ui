from app.utils.archive_names import sanitize_archive_component, build_archive_name


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

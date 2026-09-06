"""Tests for SSH host-key pinning (trust on first use)."""

import subprocess
from types import SimpleNamespace

import pytest

from app.utils import ssh_host_keys


ED25519 = (
    "example.com ssh-ed25519 "
    "AAAAC3NzaC1lZDI1NTE5AAAAIBERERERERERERERERERERERERERERERERERERERERER"
)
RSA = (
    "example.com ssh-rsa "
    "AAAAB3NzaC1yc2EiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIi"
)


@pytest.fixture
def connection():
    """A connection that predates host-key verification, so it may pin silently."""
    return SimpleNamespace(
        id=7,
        host="example.com",
        port=2222,
        known_host_key=None,
        host_key_trust_on_first_use=True,
    )


@pytest.fixture(autouse=True)
def no_scan_cooldown_leak():
    ssh_host_keys._FAILED_SCANS.clear()
    yield
    ssh_host_keys._FAILED_SCANS.clear()


@pytest.fixture(autouse=True)
def known_hosts_home(tmp_path, monkeypatch):
    monkeypatch.setattr(ssh_host_keys.settings, "ssh_home_dir", str(tmp_path))
    monkeypatch.setattr(ssh_host_keys.settings, "ssh_keys_dir", str(tmp_path))
    return tmp_path


class _Db:
    def __init__(self):
        self.commits = 0

    def commit(self):
        self.commits += 1


def _fake_run(stdout="", stderr="", returncode=0):
    def run(*args, **kwargs):
        return subprocess.CompletedProcess(
            args=args[0], returncode=returncode, stdout=stdout, stderr=stderr
        )

    return run


class TestScanHostKey:
    def test_returns_the_offered_keys(self, monkeypatch):
        monkeypatch.setattr(
            subprocess, "run", _fake_run(stdout=f"# comment\n{ED25519}\n{RSA}\n")
        )

        assert ssh_host_keys.scan_host_key("example.com", 2222) == f"{ED25519}\n{RSA}"

    def test_passes_the_port_to_ssh_keyscan(self, monkeypatch):
        captured = {}

        def run(cmd, **kwargs):
            captured["cmd"] = cmd
            return subprocess.CompletedProcess(cmd, 0, ED25519, "")

        monkeypatch.setattr(subprocess, "run", run)
        ssh_host_keys.scan_host_key("example.com", 2222)

        assert "-p" in captured["cmd"]
        assert captured["cmd"][captured["cmd"].index("-p") + 1] == "2222"

    def test_raises_when_no_key_is_offered(self, monkeypatch):
        monkeypatch.setattr(
            subprocess, "run", _fake_run(stdout="", stderr="connection refused")
        )

        with pytest.raises(ssh_host_keys.HostKeyScanError, match="connection refused"):
            ssh_host_keys.scan_host_key("example.com")

    def test_raises_without_a_host(self):
        with pytest.raises(ssh_host_keys.HostKeyScanError):
            ssh_host_keys.scan_host_key("")

    def test_raises_when_ssh_keyscan_is_missing(self, monkeypatch):
        def run(*args, **kwargs):
            raise FileNotFoundError()

        monkeypatch.setattr(subprocess, "run", run)

        with pytest.raises(ssh_host_keys.HostKeyScanError, match="not installed"):
            ssh_host_keys.scan_host_key("example.com")


class TestScanOrderIsStable:
    """ssh-keyscan queries the key types concurrently and prints whichever
    answers first, so its output order changes between runs against the same
    unchanged host. Everything downstream has to be immune to that."""

    ECDSA = (
        "example.com ecdsa-sha2-nistp256 "
        "AAAAE2VjZHNhLXNoYTItbmlzdHAyNTYAAAAIbmlzdHAyNTYAAABBBBERERERERERERE="
    )

    def _scan_returning(self, monkeypatch, stdout):
        monkeypatch.setattr(subprocess, "run", _fake_run(stdout=stdout))
        return ssh_host_keys.scan_host_key("example.com")

    def test_two_scans_of_one_host_agree_whatever_the_order(self, monkeypatch):
        first = self._scan_returning(monkeypatch, f"{RSA}\n{self.ECDSA}\n{ED25519}\n")
        second = self._scan_returning(monkeypatch, f"{ED25519}\n{RSA}\n{self.ECDSA}\n")

        assert first == second

    def test_the_strongest_key_comes_first(self, monkeypatch):
        scanned = self._scan_returning(monkeypatch, f"{RSA}\n{ED25519}\n")

        assert scanned.splitlines()[0] == ED25519

    def test_the_fingerprint_does_not_depend_on_scan_order(self):
        one = ssh_host_keys.key_fingerprint(f"{RSA}\n{ED25519}")
        other = ssh_host_keys.key_fingerprint(f"{ED25519}\n{RSA}")

        assert one == other == ssh_host_keys.key_fingerprint(ED25519)


class TestHostKeysMatch:
    def test_matches_when_every_pinned_key_is_still_offered(self):
        assert ssh_host_keys.host_keys_match(ED25519, f"{ED25519}\n{RSA}")

    def test_does_not_match_a_different_key(self):
        assert not ssh_host_keys.host_keys_match(ED25519, RSA)

    def test_does_not_match_when_nothing_is_pinned(self):
        assert not ssh_host_keys.host_keys_match(None, ED25519)
        assert not ssh_host_keys.host_keys_match("", ED25519)


class TestKnownHostsFile:
    def test_writes_the_pinned_key_with_owner_only_permissions(self, connection):
        connection.known_host_key = ED25519

        path = ssh_host_keys.write_known_hosts_file(connection)

        assert path is not None
        from pathlib import Path

        written = Path(path)
        assert written.read_text() == ED25519 + "\n"
        assert written.stat().st_mode & 0o777 == 0o600

    def test_returns_none_when_nothing_is_pinned(self, connection):
        assert ssh_host_keys.write_known_hosts_file(connection) is None

    def test_leaves_no_temporary_files_behind(self, connection):
        connection.known_host_key = ED25519
        ssh_host_keys.write_known_hosts_file(connection)
        ssh_host_keys.write_known_hosts_file(connection)

        leftovers = list(ssh_host_keys.known_hosts_dir().glob(".known_hosts.*"))
        assert leftovers == []

    def test_forget_removes_the_file(self, connection):
        connection.known_host_key = ED25519
        ssh_host_keys.write_known_hosts_file(connection)

        ssh_host_keys.forget_known_hosts_file(connection)

        assert not ssh_host_keys.known_hosts_path(connection).exists()


class TestHostKeySshOpts:
    def test_verifies_strictly_against_a_pinned_key(self, connection):
        connection.known_host_key = ED25519

        opts = ssh_host_keys.host_key_ssh_opts(connection)

        assert "StrictHostKeyChecking=yes" in opts
        assert (
            f"UserKnownHostsFile={ssh_host_keys.known_hosts_path(connection)}" in opts
        )
        assert "StrictHostKeyChecking=no" not in opts
        assert "UserKnownHostsFile=/dev/null" not in opts

    def test_pins_the_key_of_a_connection_that_has_none(self, connection, monkeypatch):
        monkeypatch.setattr(
            ssh_host_keys, "scan_host_key", lambda host, port: f"{ED25519}\n{RSA}"
        )
        db = _Db()

        opts = ssh_host_keys.host_key_ssh_opts(connection, db)

        assert connection.known_host_key == f"{ED25519}\n{RSA}"
        assert db.commits == 1
        assert "StrictHostKeyChecking=yes" in opts

    def test_never_disables_checking_when_the_host_cannot_be_scanned(
        self, connection, monkeypatch
    ):
        def fail(host, port):
            raise ssh_host_keys.HostKeyScanError("unreachable")

        monkeypatch.setattr(ssh_host_keys, "scan_host_key", fail)

        opts = ssh_host_keys.host_key_ssh_opts(connection, _Db())

        assert "StrictHostKeyChecking=accept-new" in opts
        assert "StrictHostKeyChecking=no" not in opts
        assert "UserKnownHostsFile=/dev/null" not in opts

    def test_does_not_rescan_an_unreachable_host_on_every_command(
        self, connection, monkeypatch
    ):
        scans = {"count": 0}

        def fail(host, port):
            scans["count"] += 1
            raise ssh_host_keys.HostKeyScanError("unreachable")

        monkeypatch.setattr(ssh_host_keys, "scan_host_key", fail)

        ssh_host_keys.host_key_ssh_opts(connection, _Db())
        ssh_host_keys.host_key_ssh_opts(connection, _Db())

        assert scans["count"] == 1

    def test_rescans_once_the_cooldown_has_passed(self, connection, monkeypatch):
        scans = {"count": 0}

        def fail(host, port):
            scans["count"] += 1
            raise ssh_host_keys.HostKeyScanError("unreachable")

        monkeypatch.setattr(ssh_host_keys, "scan_host_key", fail)
        monkeypatch.setattr(ssh_host_keys, "SCAN_RETRY_COOLDOWN_SECONDS", 0)

        ssh_host_keys.host_key_ssh_opts(connection, _Db())
        ssh_host_keys.host_key_ssh_opts(connection, _Db())

        assert scans["count"] == 2

    def test_falls_back_to_a_shared_file_without_a_connection(self):
        opts = ssh_host_keys.host_key_ssh_opts(None)

        assert "StrictHostKeyChecking=accept-new" in opts
        assert "UserKnownHostsFile=/dev/null" not in opts

    def test_does_not_rescan_a_connection_that_is_already_pinned(
        self, connection, monkeypatch
    ):
        connection.known_host_key = ED25519

        def fail(host, port):  # pragma: no cover - must not run
            raise AssertionError("scanned an already pinned connection")

        monkeypatch.setattr(ssh_host_keys, "scan_host_key", fail)

        ssh_host_keys.host_key_ssh_opts(connection, _Db())


class TestFirstUseTrust:
    def test_a_connection_predating_verification_pins_silently(
        self, connection, monkeypatch
    ):
        connection.host_key_trust_on_first_use = True
        monkeypatch.setattr(ssh_host_keys, "scan_host_key", lambda host, port: ED25519)

        opts = ssh_host_keys.host_key_ssh_opts(connection, _Db())

        assert connection.known_host_key == ED25519
        assert "StrictHostKeyChecking=yes" in opts

    def test_a_new_connection_waits_for_the_user_to_confirm(
        self, connection, monkeypatch
    ):
        connection.host_key_trust_on_first_use = False

        def fail(host, port):  # pragma: no cover - must not run
            raise AssertionError("scanned a connection the user has not confirmed")

        monkeypatch.setattr(ssh_host_keys, "scan_host_key", fail)

        opts = ssh_host_keys.host_key_ssh_opts(connection, _Db())

        assert connection.known_host_key is None
        # Still recorded on first use by OpenSSH itself, so a later change is
        # refused, but nothing is pinned to the row without confirmation.
        assert "StrictHostKeyChecking=accept-new" in opts
        assert (
            f"UserKnownHostsFile={ssh_host_keys.known_hosts_path(connection)}" in opts
        )

    def test_a_connection_without_the_column_is_not_pinned_silently(self, monkeypatch):
        bare = SimpleNamespace(id=9, host="example.com", port=22, known_host_key=None)

        def fail(host, port):  # pragma: no cover - must not run
            raise AssertionError("scanned a connection with no trust flag")

        monkeypatch.setattr(ssh_host_keys, "scan_host_key", fail)

        ssh_host_keys.host_key_ssh_opts(bare, _Db())

        assert bare.known_host_key is None


class TestFailClosed:
    def test_a_pinned_connection_never_degrades_when_the_file_cannot_be_written(
        self, connection, monkeypatch
    ):
        connection.known_host_key = ED25519
        monkeypatch.setattr(ssh_host_keys, "write_known_hosts_file", lambda conn: None)

        opts = ssh_host_keys.host_key_ssh_opts(connection)

        assert "StrictHostKeyChecking=yes" in opts
        assert "StrictHostKeyChecking=accept-new" not in opts

    def test_a_failed_commit_is_reported_to_the_caller(self, connection):
        class _Failing:
            def commit(self):
                raise RuntimeError("database is locked")

            def rollback(self):
                self.rolled_back = True

        session = _Failing()

        with pytest.raises(RuntimeError, match="database is locked"):
            ssh_host_keys.pin_host_key(connection, session, ED25519)

        assert session.rolled_back is True

    def test_a_failed_commit_does_not_fail_the_ssh_command(
        self, connection, monkeypatch
    ):
        class _Failing:
            def commit(self):
                raise RuntimeError("database is locked")

            def rollback(self):
                pass

        connection.host_key_trust_on_first_use = True
        monkeypatch.setattr(ssh_host_keys, "scan_host_key", lambda host, port: ED25519)

        opts = ssh_host_keys.host_key_ssh_opts(connection, _Failing())

        assert "StrictHostKeyChecking" in " ".join(opts)


class TestLookupFailuresFailClosed:
    """A lookup that failed says nothing about whether a pin exists.

    Falling back to accept-new on a database error would let one downgrade
    verification for a host that is in fact pinned.
    """

    def test_a_failed_host_lookup_is_not_silently_downgraded(self, monkeypatch):
        class _Session:
            def query(self, *args, **kwargs):
                raise RuntimeError("database is gone")

            def close(self):
                self.closed = True

        session = _Session()
        monkeypatch.setattr(
            "app.database.database.SessionLocal", lambda: session, raising=False
        )

        with pytest.raises(RuntimeError, match="database is gone"):
            ssh_host_keys.host_key_ssh_opts_for_host("example.com", 22, "borg")

        assert session.closed is True

    def test_a_failed_path_lookup_is_not_silently_downgraded(self, monkeypatch):
        class _Session:
            def close(self):
                self.closed = True

        session = _Session()
        monkeypatch.setattr(
            "app.database.database.SessionLocal", lambda: session, raising=False
        )

        def fail(path, db):
            raise RuntimeError("database is gone")

        monkeypatch.setattr(
            "app.utils.ssh_utils.find_ssh_connection_for_path", fail, raising=False
        )

        with pytest.raises(RuntimeError, match="database is gone"):
            ssh_host_keys.host_key_ssh_opts_for_path("ssh://borg@example.com/repo")

    def test_a_host_with_no_stored_connection_still_records_on_first_use(
        self, monkeypatch
    ):
        """Finding nothing is not the same as failing, and must keep working."""

        class _Query:
            def filter(self, *args, **kwargs):
                return self

            def all(self):
                return []

        class _Session:
            def query(self, *args, **kwargs):
                return _Query()

            def close(self):
                pass

        monkeypatch.setattr(
            "app.database.database.SessionLocal", lambda: _Session(), raising=False
        )

        opts = ssh_host_keys.host_key_ssh_opts_for_host("example.com", 22, "borg")

        assert "StrictHostKeyChecking=accept-new" in opts
        assert "StrictHostKeyChecking=no" not in opts


class TestOptsForConnectionId:
    def test_verifies_against_the_pin_of_a_connection_it_only_has_the_id_of(
        self, monkeypatch
    ):
        pinned = SimpleNamespace(
            id=11, host="example.com", port=22, known_host_key=ED25519
        )

        class _Query:
            def filter(self, *args, **kwargs):
                return self

            def first(self):
                return pinned

        class _Session:
            def query(self, *args, **kwargs):
                return _Query()

            def close(self):
                pass

        monkeypatch.setattr(
            "app.database.database.SessionLocal", lambda: _Session(), raising=False
        )

        opts = ssh_host_keys.host_key_ssh_opts_for_connection_id(11)

        assert "StrictHostKeyChecking=yes" in opts

    def test_without_an_id_there_is_nothing_to_verify_against(self):
        opts = ssh_host_keys.host_key_ssh_opts_for_connection_id(None)

        assert "StrictHostKeyChecking=accept-new" in opts


class TestStatus:
    def test_unknown_without_a_pin(self, connection):
        assert (
            ssh_host_keys.describe_host_key_status(connection, ED25519)
            == ssh_host_keys.HOST_KEY_STATUS_UNKNOWN
        )

    def test_trusted_when_the_key_still_matches(self, connection):
        connection.known_host_key = ED25519
        assert (
            ssh_host_keys.describe_host_key_status(connection, f"{ED25519}\n{RSA}")
            == ssh_host_keys.HOST_KEY_STATUS_TRUSTED
        )

    def test_changed_when_the_key_differs(self, connection):
        connection.known_host_key = ED25519
        assert (
            ssh_host_keys.describe_host_key_status(connection, RSA)
            == ssh_host_keys.HOST_KEY_STATUS_CHANGED
        )

    def test_unreachable_without_an_observation(self, connection):
        connection.known_host_key = ED25519
        assert (
            ssh_host_keys.describe_host_key_status(connection, None)
            == ssh_host_keys.HOST_KEY_STATUS_UNREACHABLE
        )


class TestFingerprint:
    def test_matches_the_openssh_sha256_format(self):
        import base64
        import hashlib

        blob = base64.b64decode(ED25519.split()[2])
        expected = base64.b64encode(hashlib.sha256(blob).digest()).decode().rstrip("=")

        assert ssh_host_keys.key_fingerprint(ED25519) == f"SHA256:{expected}"

    def test_uses_the_first_key_of_a_multi_key_blob(self):
        assert ssh_host_keys.key_fingerprint(
            f"{ED25519}\n{RSA}"
        ) == ssh_host_keys.key_fingerprint(ED25519)

    def test_returns_none_for_an_empty_key(self):
        assert ssh_host_keys.key_fingerprint(None) is None
        assert ssh_host_keys.key_fingerprint("  ") is None

    def test_returns_none_for_an_unparseable_key(self):
        assert (
            ssh_host_keys.key_fingerprint("example.com ssh-ed25519 not-base64!!")
            is None
        )


class TestVerificationFailureDetection:
    @pytest.mark.parametrize(
        "output",
        [
            "Host key verification failed.",
            "@@@ WARNING: REMOTE HOST IDENTIFICATION HAS CHANGED! @@@",
        ],
    )
    def test_detects_a_rejected_host_key(self, output):
        assert ssh_host_keys.host_key_verification_failed(output)

    def test_ignores_other_failures(self):
        assert not ssh_host_keys.host_key_verification_failed("Permission denied")
        assert not ssh_host_keys.host_key_verification_failed(None)

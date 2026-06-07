from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
EXPECTED_CACHE_DIR = "/home/borg/.cache/borg"


def test_app_image_exports_documented_borg_cache_dir() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert f"ENV BORG_CACHE_DIR={EXPECTED_CACHE_DIR}" in dockerfile


def test_entrypoint_ensures_borg_cache_volume_is_writable() -> None:
    entrypoint = (ROOT / "entrypoint.sh").read_text(encoding="utf-8")

    assert f"BORG_CACHE_DIR=${{BORG_CACHE_DIR:-{EXPECTED_CACHE_DIR}}}" in entrypoint
    assert "export BORG_CACHE_DIR" in entrypoint
    assert 'mkdir -p "$BORG_CACHE_DIR"' in entrypoint
    assert 'chown -R borg:borg "$BORG_CACHE_DIR"' in entrypoint


def test_runtime_base_precreates_documented_borg_cache_dir() -> None:
    dockerfile = (ROOT / "Dockerfile.runtime-base").read_text(encoding="utf-8")

    assert f"/home/borg/.ssh {EXPECTED_CACHE_DIR} /etc/cron.d" in dockerfile
    assert "/home/borg/.cache /etc/cron.d" in dockerfile
    assert f"chmod 700 /home/borg/.ssh {EXPECTED_CACHE_DIR}" in dockerfile


def test_entrypoint_persists_borg_ssh_home() -> None:
    """Require hook SSH client state to live on Borg UI's persistent data volume."""
    entrypoint = (ROOT / "entrypoint.sh").read_text(encoding="utf-8")

    assert "SSH_HOME_DIR=/home/borg/.ssh" in entrypoint
    assert "PERSISTENT_SSH_DIR=/data/ssh_keys" in entrypoint
    assert 'mkdir -p "$PERSISTENT_SSH_DIR"' in entrypoint
    assert 'cp -a "$SSH_HOME_DIR"/. "$PERSISTENT_SSH_DIR"/' in entrypoint
    assert 'rm -rf "$SSH_HOME_DIR"' in entrypoint
    assert 'ln -sfn "$PERSISTENT_SSH_DIR" "$SSH_HOME_DIR"' in entrypoint
    assert 'chown -R borg:borg "$PERSISTENT_SSH_DIR"' in entrypoint
    assert 'chmod 700 "$PERSISTENT_SSH_DIR"' in entrypoint

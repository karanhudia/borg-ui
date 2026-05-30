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

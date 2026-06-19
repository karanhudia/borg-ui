from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_rootless_podman_permissions_are_documented() -> None:
    installation = (ROOT / "docs" / "installation.md").read_text(encoding="utf-8")
    troubleshooting = (ROOT / "docs" / "troubleshooting.md").read_text(encoding="utf-8")
    configuration = (ROOT / "docs" / "configuration.md").read_text(encoding="utf-8")
    combined_docs = "\n".join([installation, troubleshooting, configuration])

    assert "Rootless Podman" in installation
    assert "PUID=0" in combined_docs
    assert "PGID=0" in combined_docs
    assert "/local" in combined_docs
    assert "source bind mounts" in combined_docs
    assert "does not chown" in combined_docs
    assert ":Z" in combined_docs or ":z" in combined_docs


def test_filesystem_snapshot_runtime_requirements_are_documented() -> None:
    usage_guide = (ROOT / "docs" / "usage-guide.md").read_text(encoding="utf-8")

    assert "Filesystem snapshot sources" in usage_guide
    assert "Synology DSM" in usage_guide
    assert "btrfs subvolume show" in usage_guide
    assert "btrfs subvolume snapshot -r" in usage_guide
    assert "btrfs subvolume delete" in usage_guide
    assert "inside the Borg UI runtime" in usage_guide

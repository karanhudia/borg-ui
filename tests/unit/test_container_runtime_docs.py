from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_rootless_podman_permissions_are_documented() -> None:
    installation = (ROOT / "docs" / "installation.md").read_text()
    troubleshooting = (ROOT / "docs" / "troubleshooting.md").read_text()
    configuration = (ROOT / "docs" / "configuration.md").read_text()
    combined_docs = "\n".join([installation, troubleshooting, configuration])

    assert "Rootless Podman" in installation
    assert "PUID=0" in combined_docs
    assert "PGID=0" in combined_docs
    assert "/local" in combined_docs
    assert "source bind mounts" in combined_docs
    assert "does not chown" in combined_docs
    assert ":Z" in combined_docs or ":z" in combined_docs

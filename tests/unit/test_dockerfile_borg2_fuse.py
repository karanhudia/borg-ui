from pathlib import Path


def test_borg2_venv_installs_pyfuse3():
    dockerfile = Path(__file__).resolve().parents[2] / "Dockerfile.runtime-base"
    content = dockerfile.read_text()

    assert "/opt/borg2-venv/bin/pip install --no-cache-dir pyfuse3" in content
    assert "ln -sf /opt/borg2-venv/bin/borg /usr/local/bin/borg2" in content

"""The version is written down once, in VERSION, and everything else reads it.

These replace the release check's regexes over app/config.py and app/main.py.
A hardcoded copy drifts the moment someone bumps VERSION and forgets it -- which
is how app_version came to say 2.2.3 while VERSION said 2.2.6 -- and the drift
is invisible until a release is attempted. Any copy reintroduced here fails
these tests instead.
"""

from pathlib import Path

import pytest

from app.config import Settings, _packaged_version, get_runtime_app_version

VERSION_FILE = Path(__file__).resolve().parents[2] / "VERSION"


def _unreadable_version_file(monkeypatch):
    # Fail only for the VERSION file, and delegate every other read to the real
    # method. A blanket Path.read_text that always raises would take down
    # anything pytest reads while the patch is live -- a source file to format a
    # traceback, for one -- turning an unrelated failure into a crash here.
    original_read_text = Path.read_text

    def boom(self, *args, **kwargs):
        if self.name == "VERSION":
            raise OSError("VERSION is not readable")
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", boom)


@pytest.fixture
def declared_version() -> str:
    return VERSION_FILE.read_text().strip()


@pytest.mark.unit
def test_version_file_exists_and_is_not_empty():
    assert VERSION_FILE.is_file()
    assert VERSION_FILE.read_text().strip()


@pytest.mark.unit
def test_runtime_version_comes_from_the_file(declared_version):
    assert get_runtime_app_version() == declared_version


@pytest.mark.unit
def test_settings_declare_no_version_of_their_own():
    """Settings used to carry an app_version field, which BaseSettings quietly
    refilled from APP_VERSION -- the image sets that to "dev", so the field
    disagreed with the version the app actually reported. There is nothing left
    for the environment to shadow."""
    assert "app_version" not in Settings.model_fields


@pytest.mark.unit
def test_the_api_documents_the_version_from_the_file(declared_version):
    """FastAPI's version is what /api/docs and the OpenAPI schema advertise."""
    from app.main import app

    assert app.version == declared_version


@pytest.mark.unit
def test_the_version_file_wins_over_the_environment(monkeypatch, declared_version):
    """The image sets APP_VERSION=dev by default (Dockerfile ARG), so an image
    built without --build-arg would otherwise report itself as "dev"."""
    monkeypatch.setenv("APP_VERSION", "dev")

    assert get_runtime_app_version() == declared_version


@pytest.mark.unit
def test_an_unreadable_version_file_degrades_instead_of_raising(monkeypatch):
    """Now that VERSION is the only source, this branch is what stands between a
    missing file and an application that cannot start: main.py asks for the
    version while being imported."""
    _unreadable_version_file(monkeypatch)

    assert _packaged_version() == ""


@pytest.mark.unit
def test_without_a_readable_file_the_environment_is_used(monkeypatch):
    _unreadable_version_file(monkeypatch)
    monkeypatch.setenv("APP_VERSION", "1.2.3")

    assert get_runtime_app_version() == "1.2.3"


@pytest.mark.unit
def test_with_neither_a_file_nor_an_environment_variable(monkeypatch):
    _unreadable_version_file(monkeypatch)
    monkeypatch.delenv("APP_VERSION", raising=False)

    assert get_runtime_app_version() == "0.0.0"

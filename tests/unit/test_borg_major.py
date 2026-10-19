"""#1315: the server reads a repository's Borg major in one place, and that
place refuses anything but 1 or 2 instead of taking it for Borg 1."""

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.core.borg_major import borg_major, is_borg2


@pytest.mark.parametrize("value,major", [(None, 1), (1, 1), (2, 2), ("2", 2)])
def test_borg_major_reads_one_and_two(value, major):
    repo = SimpleNamespace(borg_version=value)
    assert borg_major(repo) == major
    assert is_borg2(repo) is (major == 2)


def test_borg_major_defaults_to_one_without_the_field():
    assert borg_major(SimpleNamespace()) == 1
    assert borg_major(None) == 1


@pytest.mark.parametrize("value", [0, False, "", 3, -1, "3", "x", 2.5, True])
def test_borg_major_refuses_an_unknown_major(value):
    with pytest.raises(ValueError, match="Unsupported Borg major"):
        borg_major(SimpleNamespace(borg_version=value))
    with pytest.raises(ValueError, match="Unsupported Borg major"):
        is_borg2(SimpleNamespace(borg_version=value))


def test_borg_router_refuses_an_unknown_major():
    from app.core.borg_router import BorgRouter

    with pytest.raises(ValueError, match="Unsupported Borg major"):
        BorgRouter(SimpleNamespace(id=1, borg_version=3))
    assert BorgRouter(SimpleNamespace(id=1, borg_version=2)).is_v2 is True


@pytest.mark.parametrize("model_name", ["RepositoryCreate", "RepositoryImport"])
def test_repository_request_models_refuse_an_unknown_major(model_name):
    from app.api import repositories

    model = getattr(repositories, model_name)
    with pytest.raises(ValidationError):
        model(name="r", path="/tmp/r", borg_version=3)
    assert model(name="r", path="/tmp/r", borg_version=2).borg_version == 2

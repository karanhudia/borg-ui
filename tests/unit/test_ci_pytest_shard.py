import importlib.util
from pathlib import Path

import pytest


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2] / "scripts" / "ci" / "select_pytest_shard.py"
)


def load_shard_module():
    spec = importlib.util.spec_from_file_location("select_pytest_shard", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_count_tests_by_file_groups_pytest_nodes_and_ignores_noise():
    module = load_shard_module()

    counts = module.count_tests_by_file(
        [
            "============================= test session starts ==============================",
            "tests/unit/test_alpha.py::test_one",
            "tests/unit/test_alpha.py::TestAlpha::test_two[param]",
            "app/config.py:8",
            "  /path/to/app/config.py:8: PydanticDeprecatedSince20: warning",
            "tests/unit/nested/test_beta.py::test_three",
            "3 tests collected in 0.50s",
        ]
    )

    assert counts == {
        "tests/unit/test_alpha.py": 2,
        "tests/unit/nested/test_beta.py": 1,
    }


def test_select_shard_balances_files_by_collected_test_count():
    module = load_shard_module()
    counts = {
        "tests/unit/test_large.py": 9,
        "tests/unit/test_medium.py": 5,
        "tests/unit/test_small.py": 4,
        "tests/unit/test_tiny.py": 1,
    }

    shard_one = module.select_shard(counts, shard_index=1, shard_total=2)
    shard_two = module.select_shard(counts, shard_index=2, shard_total=2)

    assert shard_one == ["tests/unit/test_large.py", "tests/unit/test_tiny.py"]
    assert shard_two == ["tests/unit/test_medium.py", "tests/unit/test_small.py"]
    assert set(shard_one).isdisjoint(shard_two)
    assert set(shard_one + shard_two) == set(counts)


@pytest.mark.parametrize(
    ("shard_index", "shard_total"),
    [
        (0, 2),
        (3, 2),
        (1, 0),
    ],
)
def test_select_shard_rejects_invalid_shard_arguments(shard_index, shard_total):
    module = load_shard_module()

    with pytest.raises(ValueError):
        module.select_shard(
            {"tests/unit/test_alpha.py": 1},
            shard_index=shard_index,
            shard_total=shard_total,
        )


def test_select_shard_rejects_empty_test_counts():
    module = load_shard_module()

    with pytest.raises(ValueError, match="No pytest test nodes"):
        module.select_shard({}, shard_index=1, shard_total=2)

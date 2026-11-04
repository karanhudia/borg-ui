import importlib.util
from pathlib import Path
import subprocess
import sys

import pytest


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2] / "scripts" / "ci" / "select_pytest_shard.py"
)


def load_shard_module():
    """Load the shard selector script as an importable test module."""
    spec = importlib.util.spec_from_file_location("select_pytest_shard", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_count_tests_by_file_groups_pytest_nodes_and_ignores_noise():
    """Count only real pytest node IDs and ignore collection noise."""
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
    """Assign files to shards by collected test count without duplication."""
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
    """Reject shard indexes and totals outside the supported range."""
    module = load_shard_module()

    with pytest.raises(ValueError):
        module.select_shard(
            {"tests/unit/test_alpha.py": 1},
            shard_index=shard_index,
            shard_total=shard_total,
        )


def test_select_shard_rejects_empty_test_counts():
    """Reject empty collection input so CI never runs an accidental empty shard."""
    module = load_shard_module()

    with pytest.raises(ValueError, match="No pytest test nodes"):
        module.select_shard({}, shard_index=1, shard_total=2)


def test_duration_weights_override_test_counts_and_calibrate_missing_files():
    module = load_shard_module()
    counts = {"tests/a.py": 10, "tests/b.py": 1, "tests/c.py": 2, "tests/d.py": 1}
    # Known files average 110/11 = 10 seconds per test; missing c weighs 20.
    durations = {"tests/a.py": 10.0, "tests/b.py": 100.0, "tests/stale.py": 9999.0}
    assert module.select_shard(
        counts, shard_index=1, shard_total=2, durations=durations
    ) == ["tests/b.py"]
    assert module.select_shard(
        counts, shard_index=2, shard_total=2, durations=durations
    ) == ["tests/a.py", "tests/c.py", "tests/d.py"]


def test_duration_shards_are_deterministic_complete_and_disjoint():
    module = load_shard_module()
    counts = {f"tests/test_{index}.py": index + 1 for index in range(17)}
    durations = {"tests/test_0.py": 500, "tests/test_5.py": 2}
    shards = [
        module.select_shard(counts, shard_index=i, shard_total=4, durations=durations)
        for i in range(1, 5)
    ]
    flattened = [path for shard in shards for path in shard]
    assert len(flattened) == len(set(flattened)) == len(counts)
    assert set(flattened) == set(counts)
    reversed_counts = dict(reversed(list(counts.items())))
    for index, shard in enumerate(shards, 1):
        assert set(shard) == set(
            module.select_shard(
                reversed_counts, shard_index=index, shard_total=4, durations=durations
            )
        )


def test_selector_cli_uses_history_and_ignores_corrupt_history(tmp_path):
    import json
    import subprocess
    import sys

    history = tmp_path / "durations.json"
    history.write_text(
        json.dumps({"tests/a.py": 1, "tests/b.py": 100, "tests/c.py": 1})
    )
    command = [
        sys.executable,
        str(SCRIPT_PATH),
        "--shard-index",
        "1",
        "--shard-total",
        "2",
        "--durations-file",
        str(history),
    ]
    nodes = "tests/a.py::one\ntests/a.py::two\ntests/b.py::one\ntests/c.py::one\n"
    result = subprocess.run(command, input=nodes, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["tests/b.py"]
    history.write_text("broken JSON")
    result = subprocess.run(command, input=nodes, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["tests/a.py"]
    assert "history" in result.stderr.lower()


def test_missing_file_weight_uses_measured_seconds_per_collected_test():
    module = load_shard_module()
    counts = {"tests/a.py": 1, "tests/b.py": 1, "tests/c.py": 8, "tests/new.py": 10}
    durations = {"tests/a.py": 100, "tests/b.py": 20, "tests/c.py": 10}
    # 130 measured seconds / 10 known tests makes the new file weigh 130 seconds.
    assert module.select_shard(
        counts, shard_index=1, shard_total=2, durations=durations
    ) == ["tests/new.py"]


def test_file_balancing_is_independent_of_release_parameter_counts_and_history():
    """A tag arriving between runners cannot move files between migration shards."""
    module = load_shard_module()
    before = {"tests/a.py": 14, "tests/b.py": 28, "tests/c.py": 6, "tests/d.py": 40}
    after = {"tests/a.py": 14, "tests/b.py": 28, "tests/c.py": 6, "tests/d.py": 44}
    expected = [["tests/a.py", "tests/c.py"], ["tests/b.py", "tests/d.py"]]
    for counts in (before, after, dict(reversed(list(after.items())))):
        for history in (None, {"tests/a.py": 9999.0, "tests/b.py": 0.01}):
            shards = [
                module.select_shard(
                    counts,
                    shard_index=index,
                    shard_total=2,
                    durations=history,
                    balance_by="files",
                )
                for index in (1, 2)
            ]
            assert [sorted(shard) for shard in shards] == expected
            flattened = [path for shard in shards for path in shard]
            assert len(flattened) == len(set(flattened)) == len(counts)
            assert set(flattened) == set(counts)


def test_file_balancing_cli_ignores_timing_history_and_counts(tmp_path):
    history = tmp_path / "history.json"
    history.write_text('{"tests/a.py": 9999, "tests/b.py": 0.01}')
    command = [
        sys.executable,
        str(SCRIPT_PATH),
        "--shard-index",
        "1",
        "--shard-total",
        "2",
        "--balance-by",
        "files",
        "--durations-file",
        str(history),
    ]
    for nodes in (
        "tests/a.py::one\ntests/b.py::one\ntests/c.py::one\n",
        "tests/a.py::one\ntests/b.py::one\ntests/b.py::two\ntests/c.py::one\n",
    ):
        result = subprocess.run(command, input=nodes, text=True, capture_output=True)
        assert result.returncode == 0, result.stderr
        assert result.stdout.splitlines() == ["tests/a.py", "tests/c.py"]


@pytest.mark.parametrize("suite,shard_total", [("unit", 6), ("migrations", 2)])
def test_real_collected_suite_is_partitioned_by_whole_files_once(suite, shard_total):
    """Changing shard count cannot omit nodes or split dialects from a file."""
    root = SCRIPT_PATH.parents[2]

    def collect(paths):
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                *paths,
                "--collect-only",
                "-q",
                "-o",
                "addopts=",
            ],
            cwd=root,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        return [
            line.strip()
            for line in result.stdout.splitlines()
            if line.startswith(f"tests/{suite}/") and "::" in line
        ]

    nodes = collect([f"tests/{suite}"])
    assert nodes
    assert len(nodes) == len(set(nodes)), "collection must have unique node IDs"
    module = load_shard_module()
    counts = module.count_tests_by_file(nodes)
    # Cover both default weights and incomplete historical timings with stale files.
    for durations in (None, {min(counts): 123.0, "tests/stale.py": 9999.0}):
        shards = [
            module.select_shard(
                counts,
                shard_index=index,
                shard_total=shard_total,
                durations=durations,
                balance_by="files" if suite == "migrations" else "tests",
            )
            for index in range(1, shard_total + 1)
        ]
        files = [path for shard in shards for path in shard]
        assert all(shards), "each configured CI runner must receive test files"
        assert len(files) == len(set(files)) == len(counts)
        assert set(files) == set(counts)
        selected_nodes = [
            node
            for shard in shards
            for node in nodes
            if node.split("::", 1)[0] in shard
        ]
        assert sorted(selected_nodes) == sorted(nodes)
        if suite == "migrations" and durations is None:
            # Recollect actual CLI file selections, proving pytest receives all
            # parameterized releases/dialects, not just a count of file names.
            recollected = [node for shard in shards for node in collect(shard)]
            assert sorted(recollected) == sorted(nodes)
            for dialect in ("sqlite", "postgresql"):
                dialect_nodes = [node for node in nodes if dialect in node]
                assert dialect_nodes, f"migration inventory lost {dialect} coverage"
                assert set(dialect_nodes).issubset(recollected)

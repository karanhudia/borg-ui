"""Whether the Borg major an endpoint is pinned to has actually landed."""

import pytest

from app.core.agent_versions import borg_pin_satisfied


def binary(major: int) -> dict:
    return {"major": major, "version": f"{major}.0.0", "path": "/usr/local/bin/borg"}


@pytest.mark.parametrize(
    "desired,reported,expected",
    [
        (None, None, True),
        (None, [binary(1)], True),
        ("1", [binary(1)], True),
        ("2", [binary(2)], True),
        ("2", [binary(1), binary(2)], True),
        ("2", [binary(1)], False),
        ("2", [], False),
        ("2", None, False),
        # The agent sends major as an int; the pin is stored as a string.
        ("2", [{"major": 2}], True),
        ("2", [{"major": "2"}], True),
        # Junk in the reported list must not raise out of a heartbeat.
        ("2", [None, "borg2", {"version": "2.0.0"}], False),
        ("2", [None, binary(2)], True),
    ],
)
def test_borg_pin_satisfied(desired, reported, expected):
    assert borg_pin_satisfied(desired=desired, reported=reported) is expected

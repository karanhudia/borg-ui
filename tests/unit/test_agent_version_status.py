import pytest

from app.core.agent_versions import (
    UPGRADE_STATUSES,
    compute_agent_upgrade_status,
    parse_agent_version,
)


@pytest.mark.parametrize(
    "value,expected",
    [
        ("0.1.3", (0, 1, 3)),
        ("1.0", (1, 0)),
        ("2", (2,)),
        ("0.1.3a1", None),
        ("", None),
        (None, None),
        ("1.-2.3", None),
        ("1..3", None),
    ],
)
def test_parse_agent_version(value, expected):
    assert parse_agent_version(value) == expected


@pytest.mark.parametrize(
    "reported,desired,available,expected",
    [
        # Tracking the server.
        ("0.1.3", None, "0.1.3", "up_to_date"),
        ("0.1.2", None, "0.1.3", "outdated"),
        ("0.2.0", None, "0.1.3", "ahead"),
        # Pinned.
        ("0.1.2", "0.1.2", "0.1.3", "pinned"),
        ("0.1.1", "0.1.2", "0.1.3", "outdated"),
        ("0.1.3", "0.1.2", "0.1.3", "ahead"),
        # Unknown inputs.
        (None, None, "0.1.3", "unknown"),
        ("0.1.3", None, None, "unknown"),
        (None, None, None, "unknown"),
        ("0.1.3a1", None, "0.1.3", "unknown"),
        ("0.1.3", None, "0.1.3a1", "unknown"),
        # Equal after padding but written differently: not the served string,
        # so it is not current. Reinstalling is harmless.
        ("0.1", None, "0.1.0", "outdated"),
    ],
)
def test_compute_agent_upgrade_status(reported, desired, available, expected):
    assert (
        compute_agent_upgrade_status(
            reported=reported, desired=desired, available=available
        )
        == expected
    )
    assert expected in UPGRADE_STATUSES


def test_exact_string_match_wins_over_parsing():
    """An unparseable version that exactly matches its target is current, not
    unknown. The endpoint is demonstrably running the wheel we serve."""
    assert (
        compute_agent_upgrade_status(
            reported="0.1.3a1", desired=None, available="0.1.3a1"
        )
        == "up_to_date"
    )


def test_pin_to_the_served_version_still_reads_as_pinned():
    """A pin that happens to match what the server serves is still a pin, so
    the operator can see the endpoint will not move when the server does."""
    assert (
        compute_agent_upgrade_status(
            reported="0.1.3", desired="0.1.3", available="0.1.3"
        )
        == "pinned"
    )

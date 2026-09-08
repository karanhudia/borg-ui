import json

import pytest

from app.services.borg2_compact_stats import is_stats_line, parse_compact_stats

# The logger Borg 2.0.0b24 emits the lines from; the parser does not depend
# on it.
COMPACT_LOGGER = "borg.archiver.compact_cmd"

# Verbatim `borg compact --stats -v` output of 2.0.0b23 / b24 on a scratch
# repository.
PLAIN = """Starting compaction / garbage collection...
Overall statistics, considering all 2 archives in this repository:
Source data size was 1 MB in 6 files.
Deduplicated size is 500 kB.
Deduplication factor is 0.50.
Repository size is 502 kB in 6 objects.
Compression factor is 1.00.
Compaction saved 0 B.
Finished compaction / garbage collection...
""".splitlines()

EXPECTED = {
    "archive_count": 2,
    "source_size": 1_000_000,
    "source_files": 6,
    "deduplicated_size": 500_000,
    "deduplication_factor": 0.5,
    "repository_size": 502_000,
    "object_count": 6,
    "compression_factor": 1.0,
    "compaction_saved": 0,
    # the label follows the repository size token alone: "502 kB" is rounded
    "size_precision": "rounded_to_printed_unit",
}

# The same repository under BORG_UNITS=raw (what every compact path here
# sets): exact byte counts.
RAW = """Overall statistics, considering all 2 archives in this repository:
Source data size was 1048576 B in 6 files.
Deduplicated size is 499712 B.
Deduplication factor is 0.48.
Repository size is 501913 B in 6 objects.
Compression factor is 1.00.
Compaction saved 0 B.
""".splitlines()

# BORG_UNITS=iec, inherited from a process environment: no decimals in the
# printed unit either.
IEC = """Source data size was 1 MiB in 6 files.
Deduplicated size is 488 KiB.
Repository size is 490 KiB in 6 objects.
Compaction saved 0 B.
""".splitlines()


def _log_json(message, name=COMPACT_LOGGER):
    return json.dumps(
        {"type": "log_message", "levelname": "INFO", "name": name, "message": message}
    )


@pytest.mark.unit
def test_parses_plain_lines():
    assert parse_compact_stats(PLAIN) == EXPECTED


@pytest.mark.unit
def test_parses_log_json_entries_and_ignores_progress():
    lines = [json.dumps({"type": "progress_percent", "current": 1, "total": 2})]
    lines += [_log_json(line) for line in PLAIN]
    assert parse_compact_stats(lines) == EXPECTED


@pytest.mark.unit
def test_accepts_any_logger_and_ignores_junk():
    """The lines are matched by wording; the logger name is not a contract
    (Borg has renamed loggers between betas)."""
    lines = [
        _log_json("Repository size is 9 GB in 1 objects.", name="borg.other"),
        "{not json",
        "",
    ]
    assert parse_compact_stats(lines) == {
        "repository_size": 9_000_000_000,
        "object_count": 1,
        "size_precision": "rounded_to_printed_unit",
    }
    assert parse_compact_stats(["{not json", ""]) is None


@pytest.mark.unit
def test_returns_none_without_a_repository_size_line():
    assert parse_compact_stats(["Source data size was 1 MB in 6 files."]) is None
    assert parse_compact_stats([]) is None


@pytest.mark.unit
@pytest.mark.parametrize(
    "text,expected",
    [
        ("Repository size is 2.39 TB in 1234 objects.", 2_390_000_000_000),
        ("Repository size is 0 B in 0 objects.", 0),
        ("Repository size is 12.5 GB in 7 objects.", 12_500_000_000),
    ],
)
def test_decimal_units_as_borg_prints_them(text, expected):
    stats = parse_compact_stats([text])
    assert stats["repository_size"] == expected
    assert "source_size" not in stats


@pytest.mark.unit
def test_raw_units_are_exact_integers():
    stats = parse_compact_stats(RAW)
    assert stats["source_size"] == 1_048_576
    assert stats["deduplicated_size"] == 499_712
    assert stats["repository_size"] == 501_913
    assert stats["compaction_saved"] == 0
    assert stats["deduplication_factor"] == 0.48
    assert stats["size_precision"] == "exact"
    # above 2**53, where a float detour would lose bytes
    big = parse_compact_stats(["Repository size is 9007199254740993 B in 1 objects."])
    assert big["repository_size"] == 9_007_199_254_740_993
    assert big["size_precision"] == "exact"


@pytest.mark.unit
def test_iec_units_are_accepted_and_marked_rounded():
    stats = parse_compact_stats(IEC)
    assert stats["source_size"] == 1_048_576
    assert stats["deduplicated_size"] == 488 * 1024
    assert stats["repository_size"] == 490 * 1024
    assert stats["size_precision"] == "rounded_to_printed_unit"
    assert parse_compact_stats(["Repository size is 2.5 TiB in 1 objects."])[
        "repository_size"
    ] == int(2.5 * 2**40)


@pytest.mark.unit
def test_deeply_nested_json_is_not_a_statistics_line():
    """Agent-supplied bytes: nesting past the interpreter's limit must not
    raise out of the completion handler."""
    assert parse_compact_stats(['{"a":' * 100_000 + "1" + "}" * 100_000]) is None
    assert parse_compact_stats(["{" * 100_000]) is None


@pytest.mark.unit
def test_figures_beyond_borgs_range_are_not_statistics():
    """A figure with 400 digits did not come from Borg; the line is skipped
    so nothing downstream has to format it."""
    huge = "9" * 400
    assert parse_compact_stats([f"Repository size is {huge} B in 1 objects."]) is None
    assert parse_compact_stats([f"Repository size is 1 B in {huge} objects."]) is None
    stats = parse_compact_stats(
        [
            f"Compaction saved {huge} B.",
            f"Deduplication factor is {huge}.",
            "Compression factor is 1.50.",
            "Repository size is 1 B in 1 objects.",
        ]
    )
    assert stats == {
        "compression_factor": 1.5,
        "repository_size": 1,
        "object_count": 1,
        "size_precision": "exact",
    }
    # a digit run `int` refuses (sys.int_info.str_digits_check_threshold)
    longer = "9" * 5000
    assert parse_compact_stats([f"Repository size is {longer} B in 1 objects."]) is None
    assert parse_compact_stats([f"Repository size is 1 B in {longer} objects."]) is None


@pytest.mark.unit
def test_size_precision_follows_the_repository_size_token():
    """Only the repository size is acted on, so its token decides the
    label: an exact repository figure next to a rounded source figure is
    exact, a rounded repository figure next to exact ones is rounded."""
    exact = parse_compact_stats(
        [
            "Source data size was 1 MB in 6 files.",
            "Repository size is 900 B in 3 objects.",
        ]
    )
    assert exact["size_precision"] == "exact"
    assert exact["source_size"] == 1_000_000
    rounded = parse_compact_stats(
        [
            "Source data size was 1000000 B in 6 files.",
            "Repository size is 0.9 kB in 3 objects.",
        ]
    )
    assert rounded["size_precision"] == "rounded_to_printed_unit"
    assert rounded["repository_size"] == 900


@pytest.mark.unit
def test_agent_parser_is_the_same_parser():
    """The agent ships its own copy of this parser (its wheel has no `app`);
    a completion report and the server's fallback must read one transcript
    the same way, so the two modules are identical below their docstrings."""
    from pathlib import Path

    from agent.borg_ui_agent import compact_stats as agent_parser
    from app.services import borg2_compact_stats as server_parser

    def body(module):
        return Path(module.__file__).read_text().split('"""', 2)[2]

    assert body(agent_parser) == body(server_parser)


@pytest.mark.unit
def test_is_stats_line_matches_by_wording_only():
    assert is_stats_line("Repository size is 502 kB in 6 objects.")
    assert is_stats_line(_log_json("Compaction saved 0 B.", name="borg.renamed"))
    assert not is_stats_line("Starting compaction / garbage collection...")
    assert not is_stats_line(_log_json("analyzing archive x", name=COMPACT_LOGGER))
    assert not is_stats_line("{" * 100)
    # a figure the parser would refuse does not make a statistics line
    assert not is_stats_line(f"Repository size is {2**63} B in 1 objects.")
    assert not is_stats_line("Deduplication factor is " + "9" * 400 + ".")


@pytest.mark.unit
def test_framed_lines_with_hostile_json_are_not_statistics():
    """The transcript is agent-supplied: a framed line with an integer
    literal past the interpreter's digit limit (a ValueError that is not a
    JSONDecodeError), or a JSON value that is not an object, is skipped."""
    huge = '{"type": "log_message", "message": "x", "n": ' + "9" * 5000 + "}"
    assert parse_compact_stats([huge, "Repository size is 1 B in 1 objects."]) == {
        "repository_size": 1,
        "object_count": 1,
        "size_precision": "exact",
    }
    for value in ("[]", '"text"', "null", "1"):
        assert parse_compact_stats([value]) is None
    assert not is_stats_line(huge)


@pytest.mark.unit
def test_lines_match_as_a_whole():
    """A statistics line with anything appended is not one Borg printed."""
    assert parse_compact_stats(["Repository size is 1 B in 1 objects. extra"]) is None
    assert not is_stats_line("Compaction saved 0 B. and more")
    assert parse_compact_stats(["Repository size is 1 B in 1 objects."]) is not None


@pytest.mark.unit
@pytest.mark.parametrize(
    "version, supported",
    [
        ("2.0.0b14", False),
        ("2.0.0b15", True),
        ("borg2 2.0.0b24", True),
        ("2.0.0rc1", True),
        ("2.0.0", True),
        ("2.1.0", True),
        ("borg 1.4.1", False),
        ("Unknown", False),
    ],
)
def test_has_compact_stats(version, supported):
    from app.services.borg2_compact_stats import has_compact_stats

    assert has_compact_stats(version) is supported


@pytest.mark.unit
def test_parse_borg_version_takes_the_first_version_token():
    from app.services.borg2_compact_stats import parse_borg_version

    assert parse_borg_version("borg2 2.0.0b24\n") == "2.0.0b24"
    assert parse_borg_version("borg 1.4.1") == "1.4.1"
    assert parse_borg_version("\nborg2 2.0.0\n") == "2.0.0"
    assert parse_borg_version("no version here") is None
    assert parse_borg_version("") is None
    # a wrapper banner before Borg's own line: Borg's token wins
    assert parse_borg_version("Python 3.11.2 -- borg2 2.0.0b24\n") == "2.0.0b24"
    assert parse_borg_version("OpenSSL 3.2.1\nborg 1.4.1") == "1.4.1"
    assert parse_borg_version("borg2 2.0.0rc1") == "2.0.0"
    # digit runs `int` would refuse are not version tokens
    assert parse_borg_version("borg2 " + "9" * 5000 + ".0.0") is None


@pytest.mark.unit
def test_is_stats_line_ignores_lines_without_a_statistics_prefix():
    from app.services.borg2_compact_stats import is_stats_line

    assert not is_stats_line(_log_json("analyzing archive foo (1/2)"))
    assert is_stats_line(_log_json("Compression factor is 1.50."))

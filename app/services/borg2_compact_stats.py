"""Repository statistics from `borg compact --stats` (Borg 2).

Borg 2 reports repository-wide statistics only here, on INFO level; there
is no JSON form (borgbackup/borg#10329). The parser accepts the plain lines
or the `--log-json` `log_message` entries that wrap them.

Sizes are printed through Borg's `format_file_size`, which follows
`BORG_UNITS`: `si` (default, `502 kB`, `2.39 TB`), `iec` (`490 KiB`) or
`raw` (`502000 B`). The human forms are rounded to the digits Borg
prints, so the parsed byte count is only as exact as those digits; every
compact path of this application sets `BORG_UNITS=raw` and gets exact
integers. The result records which it got in `size_precision`, from the
repository size token, the one figure that is acted on: `exact` for a raw
byte count, `rounded_to_printed_unit` otherwise. The deduplication and
compression factors are printed with two decimals in either mode.

A figure Borg cannot have printed (a size or count at or above 2**63, a
factor that is not a finite number, a digit run `int` refuses) makes its
line not a statistics line; the same parser reads agent-supplied
transcripts, so nothing here raises on a line's content.

The lines are matched by their whole wording, not by the logger that
emitted them (`borg.archiver.compact_cmd` today); a `--log-json` entry of
any logger is accepted.
"""

import json
import re
from decimal import ROUND_HALF_UP, Decimal
from typing import Iterable, Optional

PRECISION_EXACT = "exact"
PRECISION_ROUNDED = "rounded_to_printed_unit"
# A size or count at or above this did not come from Borg (its sizes are
# 64-bit); a transcript line carrying one is not a statistics line.
MAX_COUNT = 2**63
# More digits than that cannot stay below MAX_COUNT, and `int` refuses a
# long enough digit run outright (sys.int_info.str_digits_check_threshold).
_MAX_DIGITS = 24
# A Borg 2 compact prints its statistics as the last lines of the run; this
# many lines from the end of the output hold all of them.
TAIL_LINES = 64
# The Borg 2 beta that added `compact --stats`; an older beta rejects the
# whole command for the flag.
COMPACT_STATS_SINCE_BETA = 15


# Bounded components: `int` on an unbounded digit run can refuse it.
_VERSION_TOKEN = (
    r"(?P<major>\d{1,6})\.(?P<minor>\d{1,6})\.(?P<patch>\d{1,6})(?:b(?P<beta>\d{1,6}))?"
)
_VERSION = re.compile(r"\b" + _VERSION_TOKEN)
_BORG_VERSION = re.compile(r"\bborg\S*\s+" + _VERSION_TOKEN)


def parse_borg_version(output: str) -> Optional[str]:
    """The version token in `borg --version` output ("borg2 2.0.0b24"):
    the one after the program name where there is one (a wrapper may print
    its own banner first), else the first version-shaped token, else None;
    the caller then knows nothing about the binary rather than something
    wrong."""
    match = _BORG_VERSION.search(output) or _VERSION.search(output)
    if not match:
        return None
    return match.group(0)[match.start("major") - match.start(0) :]


def has_compact_stats(version: str) -> bool:
    """Whether Borg `version` (a token from `parse_borg_version`) accepts
    `compact --stats`: any 2.x that is not a beta before b15."""
    match = _VERSION.search(version)
    if not match or int(match.group("major")) != 2:
        return False
    beta = match.group("beta")
    return beta is None or int(beta) >= COMPACT_STATS_SINCE_BETA


_UNITS = {
    "B": 1,
    "kB": 10**3,
    "MB": 10**6,
    "GB": 10**9,
    "TB": 10**12,
    "PB": 10**15,
    "EB": 10**18,
    "KiB": 2**10,
    "MiB": 2**20,
    "GiB": 2**30,
    "TiB": 2**40,
    "PiB": 2**50,
    "EiB": 2**60,
}
_SIZE = r"(?P<size>\d+(?:\.\d+)?) (?P<unit>[kMGTPE]?B|[KMGTPE]iB)"
_PATTERNS = {
    "archive_count": re.compile(
        r"^Overall statistics, considering all (?P<n>\d+) archives in this repository:$"
    ),
    "source": re.compile(rf"^Source data size was {_SIZE} in (?P<n>\d+) files\.$"),
    "deduplicated_size": re.compile(rf"^Deduplicated size is {_SIZE}\.$"),
    "deduplication_factor": re.compile(
        r"^Deduplication factor is (?P<f>\d+(?:\.\d+)?)\.$"
    ),
    "repository": re.compile(rf"^Repository size is {_SIZE} in (?P<n>\d+) objects\.$"),
    "compression_factor": re.compile(r"^Compression factor is (?P<f>\d+(?:\.\d+)?)\.$"),
    "compaction_saved": re.compile(rf"^Compaction saved {_SIZE}\.$"),
}


def _bytes(match: re.Match) -> Optional[int]:
    """Integer bytes without a float in between: `int` keeps raw counts
    exact above 2**53, Decimal scales the human forms as printed. None
    for a figure Borg cannot have printed."""
    size, unit = match.group("size"), match.group("unit")
    if len(size) > _MAX_DIGITS:
        return None
    if unit == "B" and "." not in size:
        value = int(size)
    else:
        scaled = Decimal(size) * _UNITS[unit]
        value = int(scaled.to_integral_value(rounding=ROUND_HALF_UP))
    return value if value < MAX_COUNT else None


def _count(match: re.Match) -> Optional[int]:
    text = match.group("n")
    if len(text) > _MAX_DIGITS:
        return None
    value = int(text)
    return value if value < MAX_COUNT else None


def _factor(match: re.Match) -> Optional[float]:
    text = match.group("f")
    # The pattern admits digits and one point only, so the digit cap is
    # also what keeps the float finite.
    return float(text) if len(text) <= _MAX_DIGITS else None


def _message(line: str) -> Optional[str]:
    """The statistics line inside a `--log-json` entry, or the line itself."""
    text = line.strip()
    if not text:
        return None
    if text[0] != "{":
        return text
    try:
        entry = json.loads(text)
    except (ValueError, RecursionError):
        # Agent-supplied bytes: nesting past the interpreter's limit, or an
        # integer literal past its digit limit (a ValueError that is not a
        # JSONDecodeError), is not a statistics line either.
        return None
    if not isinstance(entry, dict) or entry.get("type") != "log_message":
        return None
    message = entry.get("message")
    return message.strip() if isinstance(message, str) else None


_STATS_LINE_PREFIXES = (
    "Overall statistics",
    "Source data size",
    "Deduplicated size",
    "Deduplication factor",
    "Repository size",
    "Compression factor",
    "Compaction saved",
)


def is_stats_line(line: str) -> bool:
    """Whether `line` is one of the statistics lines, by its wording alone
    (a caller that wants them visible must not key on the logger name the
    parser itself ignores)."""
    message = _message(line)
    if message is None or not message.startswith(_STATS_LINE_PREFIXES):
        # a cheap first cut: --info prints a line per analysed archive
        return False
    for pattern in _PATTERNS.values():
        if m := pattern.match(message):
            return _figures_in_range(m)
    return False


def _figures_in_range(match: re.Match) -> bool:
    """Whether every figure the line carries is one Borg could have
    printed, the test the parser applies before it takes a line."""
    groups = match.groupdict()
    if "size" in groups and _bytes(match) is None:
        return False
    if "n" in groups and _count(match) is None:
        return False
    if "f" in groups and _factor(match) is None:
        return False
    return True


def parse_compact_stats(lines: Iterable[str]) -> Optional[dict]:
    """Return the statistics dict, or None when no "Repository size" line
    was seen (Borg 1, a compact without --stats, a failed run). A line
    whose figure is out of Borg's range is skipped."""
    stats: dict = {}
    exact = True

    for line in lines:
        message = _message(line)
        if message is None:
            continue
        if m := _PATTERNS["archive_count"].match(message):
            if (count := _count(m)) is not None:
                stats["archive_count"] = count
        elif m := _PATTERNS["source"].match(message):
            value, count = _bytes(m), _count(m)
            if value is not None and count is not None:
                stats["source_size"] = value
                stats["source_files"] = count
        elif m := _PATTERNS["deduplicated_size"].match(message):
            if (value := _bytes(m)) is not None:
                stats["deduplicated_size"] = value
        elif m := _PATTERNS["deduplication_factor"].match(message):
            if (factor := _factor(m)) is not None:
                stats["deduplication_factor"] = factor
        elif m := _PATTERNS["repository"].match(message):
            value, count = _bytes(m), _count(m)
            if value is not None and count is not None:
                stats["repository_size"] = value
                stats["object_count"] = count
                exact = m.group("unit") == "B" and "." not in m.group("size")
        elif m := _PATTERNS["compression_factor"].match(message):
            if (factor := _factor(m)) is not None:
                stats["compression_factor"] = factor
        elif m := _PATTERNS["compaction_saved"].match(message):
            if (value := _bytes(m)) is not None:
                stats["compaction_saved"] = value
    if "repository_size" not in stats:
        return None
    stats["size_precision"] = PRECISION_EXACT if exact else PRECISION_ROUNDED
    return stats

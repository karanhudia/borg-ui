"""
Test compression string building and parsing for repository creation UI.

These tests verify that compression options selected in the UI
are correctly converted to Borg compression specification strings.
"""

import pytest


class TestCompressionStringBuilding:
    """Test building Borg compression strings from UI selections."""

    def test_basic_algorithms_without_level(self):
        """Test basic compression algorithms without custom levels."""
        test_cases = [
            # (algorithm, level, auto_detect, obfuscate) -> expected_string
            ("none", "", False, ""),  # "none"
            ("lz4", "", False, ""),   # "lz4"
            ("zstd", "", False, ""),  # "zstd"
            ("zlib", "", False, ""),  # "zlib"
            ("lzma", "", False, ""),  # "lzma"
        ]

        for algo, level, auto, obf in test_cases:
            result = build_compression_string(algo, level, auto, obf)
            assert result == algo, f"Expected '{algo}', got '{result}'"

    def test_algorithms_with_levels(self):
        """Test compression algorithms with custom levels."""
        test_cases = [
            ("zstd", "3", False, ""),    # "zstd,3"
            ("zstd", "10", False, ""),   # "zstd,10"
            ("zstd", "22", False, ""),   # "zstd,22"
            ("zlib", "6", False, ""),    # "zlib,6"
            ("zlib", "9", False, ""),    # "zlib,9"
            ("lzma", "6", False, ""),    # "lzma,6"
            ("lzma", "9", False, ""),    # "lzma,9"
        ]

        for algo, level, auto, obf in test_cases:
            result = build_compression_string(algo, level, auto, obf)
            expected = f"{algo},{level}"
            assert result == expected, f"Expected '{expected}', got '{result}'"

    def test_auto_detect_compression(self):
        """Test auto-detect compression feature."""
        test_cases = [
            ("lz4", "", True, ""),       # "auto,lz4"
            ("zstd", "", True, ""),      # "auto,zstd"
            ("zstd", "10", True, ""),    # "auto,zstd,10"
            ("lzma", "6", True, ""),     # "auto,lzma,6"
        ]

        for algo, level, auto, obf in test_cases:
            result = build_compression_string(algo, level, auto, obf)
            if level:
                expected = f"auto,{algo},{level}"
            else:
                expected = f"auto,{algo}"
            assert result == expected, f"Expected '{expected}', got '{result}'"

    def test_obfuscate_without_compression(self):
        """Test obfuscation with no compression."""
        result = build_compression_string("none", "", False, "110")
        assert result == "obfuscate,110,none"

    def test_obfuscate_with_compression(self):
        """Test obfuscation with compression algorithms."""
        test_cases = [
            ("zstd", "", False, "110"),    # "obfuscate,110,zstd"
            ("zstd", "3", False, "250"),   # "obfuscate,250,zstd,3"
            ("lzma", "6", False, "110"),   # "obfuscate,110,lzma,6"
        ]

        for algo, level, auto, obf in test_cases:
            result = build_compression_string(algo, level, auto, obf)
            if level:
                expected = f"obfuscate,{obf},{algo},{level}"
            else:
                expected = f"obfuscate,{obf},{algo}"
            assert result == expected, f"Expected '{expected}', got '{result}'"

    def test_obfuscate_with_auto_detect(self):
        """Test obfuscation combined with auto-detect."""
        test_cases = [
            ("zstd", "", True, "110"),     # "obfuscate,110,auto,zstd"
            ("zstd", "10", True, "250"),   # "obfuscate,250,auto,zstd,10"
            ("lzma", "6", True, "110"),    # "obfuscate,110,auto,lzma,6"
        ]

        for algo, level, auto, obf in test_cases:
            result = build_compression_string(algo, level, auto, obf)
            if level:
                expected = f"obfuscate,{obf},auto,{algo},{level}"
            else:
                expected = f"obfuscate,{obf},auto,{algo}"
            assert result == expected, f"Expected '{expected}', got '{result}'"


class TestCompressionStringParsing:
    """Test parsing Borg compression strings back to UI fields."""

    def test_parse_basic_algorithms(self):
        """Test parsing basic compression algorithms."""
        test_cases = [
            ("none", {"algorithm": "none", "level": "", "autoDetect": False, "obfuscate": ""}),
            ("lz4", {"algorithm": "lz4", "level": "", "autoDetect": False, "obfuscate": ""}),
            ("zstd", {"algorithm": "zstd", "level": "", "autoDetect": False, "obfuscate": ""}),
            ("zlib", {"algorithm": "zlib", "level": "", "autoDetect": False, "obfuscate": ""}),
            ("lzma", {"algorithm": "lzma", "level": "", "autoDetect": False, "obfuscate": ""}),
        ]

        for compression_str, expected in test_cases:
            result = parse_compression_string(compression_str)
            assert result == expected, f"Failed to parse '{compression_str}'"

    def test_parse_algorithms_with_levels(self):
        """Test parsing compression algorithms with levels."""
        test_cases = [
            ("zstd,3", {"algorithm": "zstd", "level": "3", "autoDetect": False, "obfuscate": ""}),
            ("zstd,10", {"algorithm": "zstd", "level": "10", "autoDetect": False, "obfuscate": ""}),
            ("zlib,6", {"algorithm": "zlib", "level": "6", "autoDetect": False, "obfuscate": ""}),
            ("lzma,6", {"algorithm": "lzma", "level": "6", "autoDetect": False, "obfuscate": ""}),
        ]

        for compression_str, expected in test_cases:
            result = parse_compression_string(compression_str)
            assert result == expected, f"Failed to parse '{compression_str}'"

    def test_parse_auto_detect(self):
        """Test parsing auto-detect compression."""
        test_cases = [
            ("auto,lz4", {"algorithm": "lz4", "level": "", "autoDetect": True, "obfuscate": ""}),
            ("auto,zstd", {"algorithm": "zstd", "level": "", "autoDetect": True, "obfuscate": ""}),
            ("auto,zstd,10", {"algorithm": "zstd", "level": "10", "autoDetect": True, "obfuscate": ""}),
            ("auto,lzma,6", {"algorithm": "lzma", "level": "6", "autoDetect": True, "obfuscate": ""}),
        ]

        for compression_str, expected in test_cases:
            result = parse_compression_string(compression_str)
            assert result == expected, f"Failed to parse '{compression_str}'"

    def test_parse_obfuscate(self):
        """Test parsing obfuscation settings."""
        test_cases = [
            ("obfuscate,110,none", {"algorithm": "none", "level": "", "autoDetect": False, "obfuscate": "110"}),
            ("obfuscate,110,zstd", {"algorithm": "zstd", "level": "", "autoDetect": False, "obfuscate": "110"}),
            ("obfuscate,250,zstd,3", {"algorithm": "zstd", "level": "3", "autoDetect": False, "obfuscate": "250"}),
        ]

        for compression_str, expected in test_cases:
            result = parse_compression_string(compression_str)
            assert result == expected, f"Failed to parse '{compression_str}'"

    def test_parse_obfuscate_with_auto_detect(self):
        """Test parsing obfuscation combined with auto-detect."""
        test_cases = [
            ("obfuscate,110,auto,zstd", {"algorithm": "zstd", "level": "", "autoDetect": True, "obfuscate": "110"}),
            ("obfuscate,250,auto,zstd,10", {"algorithm": "zstd", "level": "10", "autoDetect": True, "obfuscate": "250"}),
        ]

        for compression_str, expected in test_cases:
            result = parse_compression_string(compression_str)
            assert result == expected, f"Failed to parse '{compression_str}'"


class TestRoundTripConversion:
    """Test that building and parsing are inverse operations."""

    def test_round_trip_basic(self):
        """Test round-trip conversion for basic cases."""
        test_cases = [
            ("lz4", "", False, ""),
            ("zstd", "10", False, ""),
            ("auto", "lzma", True, "6"),
        ]

        for algo, level, auto, obf in test_cases:
            # Build string from UI values
            compression_str = build_compression_string(algo, level, auto, obf)
            # Parse it back
            parsed = parse_compression_string(compression_str)
            # Rebuild from parsed values
            rebuilt = build_compression_string(
                parsed["algorithm"],
                parsed["level"],
                parsed["autoDetect"],
                parsed["obfuscate"]
            )
            # Should match original
            assert compression_str == rebuilt, f"Round-trip failed: {compression_str} != {rebuilt}"


# Helper functions matching the TypeScript implementation
def build_compression_string(algorithm: str, level: str, auto_detect: bool, obfuscate: str) -> str:
    """Build Borg compression string from UI selections."""
    parts = []

    # Add obfuscate prefix if specified
    if obfuscate:
        parts.append("obfuscate")
        parts.append(obfuscate)

    # Add auto prefix if enabled
    if auto_detect:
        parts.append("auto")

    # Add algorithm (unless it's 'none')
    if algorithm != "none":
        parts.append(algorithm)
        # Add level if specified
        if level:
            parts.append(level)
    else:
        parts.append("none")

    return ",".join(parts)


def parse_compression_string(compression: str) -> dict:
    """Parse Borg compression string back to UI fields."""
    parts = compression.split(",")
    algorithm = "lz4"
    level = ""
    auto_detect = False
    obfuscate = ""

    i = 0

    # Check for obfuscate
    if i < len(parts) and parts[i] == "obfuscate":
        i += 1
        if i < len(parts):
            obfuscate = parts[i]
            i += 1

    # Check for auto
    if i < len(parts) and parts[i] == "auto":
        auto_detect = True
        i += 1

    # Get algorithm
    if i < len(parts):
        algorithm = parts[i]
        i += 1

    # Get level
    if i < len(parts):
        level = parts[i]

    return {
        "algorithm": algorithm,
        "level": level,
        "autoDetect": auto_detect,
        "obfuscate": obfuscate
    }

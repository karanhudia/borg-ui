#!/usr/bin/env python3
"""Write app/mcp/backend_strings.json from the English locale's `backend` tree.

MCP tools turn backend error keys into English sentences; the runtime image
does not ship the frontend sources, so the strings travel with the backend.
`--check` fails when the committed file is stale (run by the unit tests).
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "frontend" / "src" / "locales" / "en.json"
TARGET = ROOT / "app" / "mcp" / "backend_strings.json"


def render() -> str:
    backend = json.loads(SOURCE.read_text())["backend"]
    return json.dumps(backend, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--output", type=Path, default=TARGET)
    args = parser.parse_args()
    expected = render()
    if args.check:
        current = args.output.read_text() if args.output.exists() else ""
        if current != expected:
            print(f"{args.output} is stale: run scripts/extract_backend_strings.py")
            return 1
        return 0
    args.output.write_text(expected)
    return 0


if __name__ == "__main__":
    sys.exit(main())

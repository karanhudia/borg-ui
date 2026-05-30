"""Export Borg UI configuration from a local runtime shell.

This module is intended for pre-backup scripts that run inside the Borg UI
container or another trusted environment with access to the configured database.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path
from typing import BinaryIO, Callable, Sequence, TextIO

from sqlalchemy.orm import Session

from app.database.database import SessionLocal
from app.services.borgmatic_service import (
    BorgmaticExportService,
    build_borgmatic_export_artifact,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Export Borg UI repository configuration in the same format as the web UI export."
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Output path for the export artifact, or '-' to write bytes to stdout.",
    )
    parser.add_argument(
        "--repository-id",
        action="append",
        type=int,
        dest="repository_ids",
        help="Repository ID to export. Repeat to export multiple repositories. Defaults to all repositories.",
    )
    parser.add_argument(
        "--no-schedules",
        action="store_true",
        help="Exclude schedule-derived retention settings from the export.",
    )
    return parser


def _write_output_file(output_path: Path, content: bytes) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_file = tempfile.NamedTemporaryFile(
        "wb",
        delete=False,
        dir=output_path.parent,
        prefix=f".{output_path.name}.",
        suffix=".tmp",
    )
    temp_path = Path(temp_file.name)
    try:
        with temp_file:
            temp_file.write(content)
            temp_file.flush()
        temp_path.replace(output_path)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise


def main(
    argv: Sequence[str] | None = None,
    *,
    session_factory: Callable[[], Session] = SessionLocal,
    stdout: BinaryIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    output_stream = stdout or sys.stdout.buffer
    error_stream = stderr or sys.stderr

    db = session_factory()
    try:
        export_service = BorgmaticExportService(db)
        configs = export_service.export_all_repositories(
            repository_ids=args.repository_ids,
            include_schedules=not args.no_schedules,
        )
        artifact = build_borgmatic_export_artifact(configs)

        if args.output == "-":
            output_stream.write(artifact.content)
            output_stream.flush()
        else:
            _write_output_file(Path(args.output), artifact.content)

        return 0
    except ValueError as exc:
        print(str(exc), file=error_stream)
        return 1
    except OSError as exc:
        print(f"Failed to write export: {exc}", file=error_stream)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())

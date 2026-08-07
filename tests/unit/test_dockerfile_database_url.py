"""The image must not hardcode DATABASE_URL.

The app derives sqlite:///$DATA_DIR/borg.db when DATABASE_URL is unset, and a
DATABASE_URL always wins over DB_HOST. So a default baked into the image would
make the Postgres switch (borgUI.postgres in the chart) silently do nothing --
the pod would keep running on SQLite while every DB_* variable was set. This
happened once; the test keeps it from happening again.
"""

from pathlib import Path


def test_dockerfile_does_not_hardcode_database_url():
    dockerfile = Path(__file__).resolve().parents[2] / "Dockerfile"
    content = dockerfile.read_text()

    assert "ENV DATABASE_URL" not in content, (
        "A DATABASE_URL env default in the image overrides DB_HOST and disables "
        "the Postgres switch; the app derives the SQLite URL from DATA_DIR instead."
    )
    # DATA_DIR must stay -- that is what the derived SQLite path is built from.
    assert "ENV DATA_DIR=/data" in content

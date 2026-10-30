"""Refuse unsafe persisted operands before sending backup jobs to agents."""

import json

import pytest

from app.database.models import Repository
from app.services.repository_executor import build_agent_backup_payload


@pytest.fixture
def repository():
    return Repository(
        id=42,
        name="Agent repository",
        path="/agent/repo",
        borg_version=1,
        compression="lz4",
        source_directories=json.dumps(["/data", "relative source"]),
        custom_flags="--one-file-system",
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    "source_options",
    [
        {"source_directories": ["--review-sentinel"]},
        {
            "source_locations": [
                {"source_type": "local", "paths": ["--review-sentinel"]}
            ]
        },
        {},
    ],
)
def test_agent_backup_dispatch_rejects_option_shaped_sources(
    repository, source_options
):
    repository.source_directories = json.dumps(["--review-sentinel"])
    with pytest.raises(ValueError):
        build_agent_backup_payload(repository, "daily", **source_options)


@pytest.mark.unit
def test_agent_backup_dispatch_rejects_option_shaped_archive(repository):
    with pytest.raises(ValueError):
        build_agent_backup_payload(repository, "--review-sentinel")


@pytest.mark.unit
@pytest.mark.parametrize("major", [1, 2])
def test_agent_backup_dispatch_preserves_normal_operands_and_flags(repository, major):
    repository.borg_version = major
    payload = build_agent_backup_payload(repository, "daily")

    assert payload["backup"]["archive_name"] == "daily"
    assert payload["backup"]["source_paths"] == ["/data", "relative source"]
    assert payload["backup"]["custom_flags"] == "--one-file-system"

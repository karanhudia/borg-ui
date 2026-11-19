"""Repository and space tools (plan Task 9)."""

import pytest


@pytest.mark.unit
def test_list_repositories(admin_mcp, seeded):
    result = admin_mcp.call("list_repositories")
    assert result["text"].splitlines()[0] == "2 repositories:"
    assert (
        "*Laptop*: Borg 1, on this server, 18.1 GB, 0 archives, last backup 9 days ago"
        in result["text"]
    )
    assert [r["name"] for r in result["data"]["repositories"]] == ["Laptop", "Photos"]
    assert "hunter2" not in str(result)
    assert "pre_backup_script" not in str(result["data"])


@pytest.mark.unit
def test_get_repository(admin_mcp, seeded):
    result = admin_mcp.call("get_repository", repository="photos")
    text = result["text"]
    assert text.startswith("*Photos* is a Borg 1 repository on this server.")
    assert "Checks are not scheduled." in text
    assert "Live statistics are not available right now" in text  # no real repo on disk
    assert result["data"]["repository"]["name"] == "Photos"
    assert "hunter2" not in str(result)


@pytest.mark.unit
def test_get_repository_ambiguous(admin_mcp, seeded, test_db):
    from app.database.models import Repository

    test_db.add(
        Repository(name="Photos old", path="/srv/backups/photos-old", borg_version=1)
    )
    test_db.commit()
    result = admin_mcp.call("get_repository", repository="photo")
    assert result["is_error"]
    assert result["text"] == (
        'I found 2 repositories matching "photo": *Photos* and *Photos old*. Which one?'
    )


@pytest.mark.unit
def test_get_repository_not_found(admin_mcp, seeded):
    result = admin_mcp.call("get_repository", repository="Fotos")
    assert result["is_error"]
    assert result["text"].startswith('I could not find a repository called "Fotos".')


@pytest.mark.unit
def test_get_repository_space(admin_mcp, seeded):
    result = admin_mcp.call("get_repository_space", repository="Photos")
    assert "*Photos* takes 412.6 GB on disk." in result["text"]
    assert "Archives that added the most:" in result["text"]
    assert len(result["data"]["points"]) == 2


@pytest.mark.unit
def test_compare_retention_before_any_comparison(admin_mcp, seeded):
    result = admin_mcp.call("compare_retention", repository="Photos")
    assert result["text"].startswith(
        "Current policy for *Photos*: 7d 4w 6m 1y (Borg UI's default)."
    )
    assert "No comparison has been computed yet." in result["text"]

"""Names to objects: never guess between similar names (plan Task 6)."""

import pytest

from app.mcp.resolve import Ambiguous, NotFound, pick, ssh_label

ITEMS = [
    {"id": 1, "name": "Photos"},
    {"id": 2, "name": "Photos old"},
    {"id": 3, "name": "Documents"},
]


@pytest.mark.unit
@pytest.mark.parametrize("ref", ["Documents", "documents", "doc", 3, "3"])
def test_resolves_unique_matches(ref):
    assert pick("repository", ref, ITEMS)["id"] == 3


@pytest.mark.unit
def test_exact_name_wins_over_prefix():
    assert pick("repository", "Photos", ITEMS)["id"] == 1
    assert pick("repository", "photos", ITEMS)["id"] == 1


@pytest.mark.unit
def test_pick_prefers_prefix_over_substring():
    items = [{"id": 1, "name": "Photos"}, {"id": 2, "name": "Old Photos"}]
    assert pick("repository", "photos", items)["id"] == 1
    assert pick("repository", "phot", items)["id"] == 1


@pytest.mark.unit
def test_pick_substring_only_is_not_found():
    with pytest.raises(NotFound):
        pick("repository", "hotos", ITEMS)
    with pytest.raises(NotFound):
        pick("repository", "cume", ITEMS)


@pytest.mark.unit
def test_ambiguous_names_ask():
    with pytest.raises(Ambiguous) as caught:
        pick("repository", "photo", ITEMS)
    assert caught.value.text == (
        'I found 2 repositories matching "photo": *Photos* and *Photos old*. Which one?'
    )


@pytest.mark.unit
def test_unknown_names_suggest():
    with pytest.raises(NotFound) as caught:
        pick("repository", "Fotos", ITEMS)
    assert caught.value.text.startswith('I could not find a repository called "Fotos".')
    assert "*Photos*" in caught.value.text
    with pytest.raises(NotFound):
        pick("repository", "9999", ITEMS)


@pytest.mark.unit
def test_many_candidates_are_cut():
    items = [{"id": i, "name": f"Server {i}"} for i in range(1, 13)]
    with pytest.raises(Ambiguous) as caught:
        pick("repository", "server", items)
    assert caught.value.text.endswith("and 4 more. Which one?")


@pytest.mark.unit
def test_ssh_labels():
    assert ssh_label({"username": "borg", "host": "nas", "port": 22}) == "borg@nas"
    assert (
        ssh_label({"username": "borg", "host": "nas", "port": 2222}) == "borg@nas:2222"
    )

"""Guard: the repository form and the server agree on the URLs only Borg 2
can open.

The form selects Borg 2 for such a URL (``BORG2_ONLY_URL_PREFIXES`` in
``frontend/src/utils/borgUtils.ts``); the server refuses it for a Borg 1
repository with its own copy of the list. Two runtimes, no shared module, so
a drift between the copies would let the form offer what the server refuses.
"""

import re
from pathlib import Path

from app.api.repositories import BORG2_ONLY_URL_PREFIXES

REPO_ROOT = Path(__file__).resolve().parents[2]
BORG_UTILS_TS = REPO_ROOT / "frontend" / "src" / "utils" / "borgUtils.ts"


def _frontend_prefixes() -> list[str]:
    source = BORG_UTILS_TS.read_text()
    match = re.search(
        r"export const BORG2_ONLY_URL_PREFIXES = \[(.*?)\]", source, re.DOTALL
    )
    assert match, "BORG2_ONLY_URL_PREFIXES not found in borgUtils.ts"
    return re.findall(r"'([^']*)'", match.group(1))


def test_frontend_list_equals_server_list():
    assert _frontend_prefixes() == list(BORG2_ONLY_URL_PREFIXES)

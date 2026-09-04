import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.models import (
    DEFAULT_HISTORY_INDEX_EXCLUDES,
    Base,
    Repository,
    SystemSettings,
)


@pytest.mark.unit
def test_default_history_excludes_match_spec_6_7():
    assert DEFAULT_HISTORY_INDEX_EXCLUDES == (
        "**/.cache/**",
        "**/Library/Caches/**",
        "**/node_modules/**",
        "**/__pycache__/**",
        "**/.git/objects/**",
    )


@pytest.mark.unit
def test_new_repository_is_seeded_with_default_excludes():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    repo = Repository(name="r", path="/tmp/r", encryption="none", compression="lz4")
    db.add(repo)
    db.add(SystemSettings())
    db.commit()
    db.refresh(repo)
    assert repo.history_index_excludes == list(DEFAULT_HISTORY_INDEX_EXCLUDES)
    assert db.query(SystemSettings).first().history_bootstrap_at is None

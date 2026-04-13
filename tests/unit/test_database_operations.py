"""
Unit tests for database CRUD operations
"""

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database.models import Repository, User
from app.core.security import get_password_hash, verify_password


@pytest.mark.unit
class TestRepositoryCRUD:
    """Test repository database operations"""

    def test_create_repository(self, db_session: Session):
        """Test creating a repository"""
        repo = Repository(
            name="Test Repo",
            path="/tmp/test-repo",
            encryption="repokey",
            compression="lz4",
            repository_type="local",
        )
        db_session.add(repo)
        db_session.commit()
        db_session.refresh(repo)

        assert repo.id is not None
        assert repo.name == "Test Repo"
        assert repo.path == "/tmp/test-repo"

    def test_read_repository(self, db_session: Session, sample_repository):
        """Test reading a repository"""
        repo = db_session.query(Repository).filter_by(id=sample_repository.id).first()

        assert repo is not None
        assert repo.name == sample_repository.name
        assert repo.path == sample_repository.path

    def test_update_repository(self, db_session: Session, sample_repository):
        """Test updating a repository"""
        sample_repository.name = "Updated Name"
        sample_repository.compression = "zstd"
        db_session.commit()
        db_session.refresh(sample_repository)

        assert sample_repository.name == "Updated Name"
        assert sample_repository.compression == "zstd"

    def test_delete_repository(self, db_session: Session, sample_repository):
        """Test deleting a repository"""
        repo_id = sample_repository.id
        db_session.delete(sample_repository)
        db_session.commit()

        deleted = db_session.query(Repository).filter_by(id=repo_id).first()
        assert deleted is None

    def test_list_repositories(self, db_session: Session, multiple_repositories):
        """Test listing all repositories"""
        repos = db_session.query(Repository).all()

        assert len(repos) == 3
        assert all(isinstance(repo, Repository) for repo in repos)

    def test_filter_repositories_by_encryption(
        self, db_session: Session, multiple_repositories
    ):
        """Test filtering repositories by encryption type"""
        encrypted_repos = (
            db_session.query(Repository).filter_by(encryption="repokey").all()
        )

        assert len(encrypted_repos) > 0
        assert all(repo.encryption == "repokey" for repo in encrypted_repos)


@pytest.mark.unit
class TestUserCRUD:
    """Test user database operations"""

    def test_create_user(self, db_session: Session):
        """Test creating a user"""
        password_hash = get_password_hash("testpassword")
        user = User(username="newuser", password_hash=password_hash, is_active=True)
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)

        assert user.id is not None
        assert user.username == "newuser"
        assert verify_password("testpassword", user.password_hash)

    def test_read_user(self, db_session: Session, sample_user):
        """Test reading a user"""
        user = db_session.query(User).filter_by(id=sample_user.id).first()

        assert user is not None
        assert user.username == sample_user.username
        assert user.is_active == sample_user.is_active

    def test_update_user(self, db_session: Session, sample_user):
        """Test updating a user"""
        sample_user.is_active = False
        db_session.commit()
        db_session.refresh(sample_user)

        assert sample_user.is_active is False

    def test_delete_user(self, db_session: Session, sample_user):
        """Test deleting a user"""
        user_id = sample_user.id
        db_session.delete(sample_user)
        db_session.commit()

        deleted = db_session.query(User).filter_by(id=user_id).first()
        assert deleted is None

    def test_find_user_by_username(self, db_session: Session, sample_user):
        """Test finding a user by username"""
        user = db_session.query(User).filter_by(username=sample_user.username).first()

        assert user is not None
        assert user.id == sample_user.id

    def test_unique_username_constraint(self, db_session: Session, sample_user):
        """Test that usernames must be unique"""
        duplicate_user = User(
            username=sample_user.username,  # Same username
            password_hash="different_hash",
            is_active=True,
        )
        db_session.add(duplicate_user)

        with pytest.raises(Exception):  # Will raise IntegrityError
            db_session.commit()


@pytest.mark.unit
class TestMigration048:
    """Tests for migration 048: fix ssh_connections FK cascade (issue #308)

    The migration runner has no tracking — every migration runs on every
    startup.  Migration 048 must therefore be fully idempotent and must work
    regardless of how many columns ssh_connections currently has.
    """

    def _make_engine(self, ddl: str):
        """Return an in-memory SQLite engine with ssh_keys + ssh_connections."""
        from sqlalchemy import create_engine
        from sqlalchemy.pool import StaticPool

        engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        with engine.connect() as conn:
            conn.execute(
                text("CREATE TABLE ssh_keys (id INTEGER PRIMARY KEY, name TEXT)")
            )
            conn.execute(text(ddl))
            conn.commit()
        return engine

    def test_fixes_cascade_to_set_null(self):
        """CASCADE FK is replaced with SET NULL after upgrade runs."""
        import importlib

        m048 = importlib.import_module(
            "app.database.migrations.048_fix_ssh_connection_cascade"
        )

        engine = self._make_engine("""
            CREATE TABLE ssh_connections (
                id INTEGER PRIMARY KEY,
                ssh_key_id INTEGER,
                host TEXT NOT NULL,
                username TEXT NOT NULL,
                port INTEGER DEFAULT 22 NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                FOREIGN KEY (ssh_key_id) REFERENCES ssh_keys(id) ON DELETE CASCADE
            )
        """)

        with engine.connect() as conn:
            m048.upgrade(conn)
            conn.commit()
            fk_rows = conn.execute(
                text("PRAGMA foreign_key_list(ssh_connections)")
            ).fetchall()

        on_delete_actions = [row[6] for row in fk_rows]
        assert "CASCADE" not in on_delete_actions
        assert "SET NULL" in on_delete_actions

    def test_idempotent_when_already_set_null(self):
        """Running upgrade again after it already ran must not raise."""
        import importlib

        m048 = importlib.import_module(
            "app.database.migrations.048_fix_ssh_connection_cascade"
        )

        engine = self._make_engine("""
            CREATE TABLE ssh_connections (
                id INTEGER PRIMARY KEY,
                ssh_key_id INTEGER,
                host TEXT NOT NULL,
                username TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                FOREIGN KEY (ssh_key_id) REFERENCES ssh_keys(id) ON DELETE SET NULL
            )
        """)

        with engine.connect() as conn:
            m048.upgrade(conn)  # should be a no-op
            conn.commit()
            fk_rows = conn.execute(
                text("PRAGMA foreign_key_list(ssh_connections)")
            ).fetchall()

        on_delete_actions = [row[6] for row in fk_rows]
        assert "CASCADE" not in on_delete_actions

    def test_handles_extra_columns(self):
        """Upgrade works when the table has extra columns added by later migrations."""
        import importlib

        m048 = importlib.import_module(
            "app.database.migrations.048_fix_ssh_connection_cascade"
        )

        # Simulate the real-world case: table already has use_sftp_mode and
        # ssh_path_prefix (added by migrations 059 and 066) plus CASCADE still present.
        engine = self._make_engine("""
            CREATE TABLE ssh_connections (
                id INTEGER PRIMARY KEY,
                ssh_key_id INTEGER,
                host TEXT NOT NULL,
                username TEXT NOT NULL,
                port INTEGER DEFAULT 22 NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                FOREIGN KEY (ssh_key_id) REFERENCES ssh_keys(id) ON DELETE CASCADE
            )
        """)
        with engine.connect() as conn:
            conn.execute(
                text(
                    "ALTER TABLE ssh_connections ADD COLUMN use_sftp_mode BOOLEAN NOT NULL DEFAULT 1"
                )
            )
            conn.execute(
                text("ALTER TABLE ssh_connections ADD COLUMN ssh_path_prefix TEXT")
            )
            conn.execute(
                text(
                    "INSERT INTO ssh_connections (host, username) VALUES ('host1', 'user1')"
                )
            )
            conn.commit()

        with engine.connect() as conn:
            m048.upgrade(conn)
            conn.commit()

            fk_rows = conn.execute(
                text("PRAGMA foreign_key_list(ssh_connections)")
            ).fetchall()
            rows = conn.execute(text("SELECT * FROM ssh_connections")).fetchall()
            col_names = [
                d[1]
                for d in conn.execute(
                    text("PRAGMA table_info(ssh_connections)")
                ).fetchall()
            ]

        on_delete_actions = [row[6] for row in fk_rows]
        assert "CASCADE" not in on_delete_actions
        assert "SET NULL" in on_delete_actions
        # Data and extra columns preserved
        assert len(rows) == 1
        assert "use_sftp_mode" in col_names
        assert "ssh_path_prefix" in col_names


@pytest.mark.unit
class TestMigration065:
    """Tests for migration 065: cleanup schedule junction duplicates/orphans."""

    def _make_engine(self):
        from sqlalchemy import create_engine
        from sqlalchemy.pool import StaticPool

        engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        with engine.connect() as conn:
            conn.execute(text("PRAGMA foreign_keys=OFF"))
            conn.execute(
                text("CREATE TABLE scheduled_jobs (id INTEGER PRIMARY KEY, name TEXT)")
            )
            conn.execute(
                text("CREATE TABLE repositories (id INTEGER PRIMARY KEY, name TEXT)")
            )
            conn.execute(
                text("""
                CREATE TABLE scheduled_job_repositories (
                    id INTEGER PRIMARY KEY,
                    scheduled_job_id INTEGER NOT NULL,
                    repository_id INTEGER NOT NULL,
                    execution_order INTEGER NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            )
            conn.execute(
                text("INSERT INTO scheduled_jobs (id, name) VALUES (1, 'job-1')")
            )
            conn.execute(
                text("INSERT INTO repositories (id, name) VALUES (1, 'repo-1')")
            )
            conn.commit()
        return engine

    def test_upgrade_removes_orphaned_schedule_and_repository_rows(self):
        import importlib

        m065 = importlib.import_module(
            "app.database.migrations.065_cleanup_schedule_duplicates"
        )
        engine = self._make_engine()

        with engine.connect() as conn:
            conn.execute(
                text("""
                INSERT INTO scheduled_job_repositories (id, scheduled_job_id, repository_id, execution_order)
                VALUES
                    (1, 1, 1, 0),
                    (2, 999, 1, 1),
                    (3, 1, 999, 2)
            """)
            )
            conn.commit()

            m065.upgrade(conn)
            conn.commit()

            rows = conn.execute(
                text("""
                SELECT id, scheduled_job_id, repository_id
                FROM scheduled_job_repositories
                ORDER BY id
            """)
            ).fetchall()
            fk_rows = conn.execute(
                text("PRAGMA foreign_key_list(scheduled_job_repositories)")
            ).fetchall()

        assert rows == [(1, 1, 1)]
        on_delete_actions = [row[6] for row in fk_rows]
        assert "CASCADE" in on_delete_actions

    def test_upgrade_is_restart_safe_when_temp_table_exists(self):
        import importlib

        m065 = importlib.import_module(
            "app.database.migrations.065_cleanup_schedule_duplicates"
        )
        engine = self._make_engine()

        with engine.connect() as conn:
            conn.execute(
                text("""
                INSERT INTO scheduled_job_repositories (id, scheduled_job_id, repository_id, execution_order)
                VALUES (1, 1, 1, 0)
            """)
            )
            conn.execute(
                text("""
                CREATE TABLE scheduled_job_repositories_new (
                    id INTEGER PRIMARY KEY,
                    scheduled_job_id INTEGER NOT NULL,
                    repository_id INTEGER NOT NULL,
                    execution_order INTEGER NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            )
            conn.commit()

            m065.upgrade(conn)
            conn.commit()

            temp_table = conn.execute(
                text("""
                SELECT name FROM sqlite_master
                WHERE type='table' AND name='scheduled_job_repositories_new'
            """)
            ).fetchall()
            rows = conn.execute(
                text("SELECT COUNT(*) FROM scheduled_job_repositories")
            ).scalar_one()

        assert temp_table == []
        assert rows == 1


@pytest.mark.unit
class TestMigration081:
    """Tests for migration 081: role + API tokens bootstrap."""

    def _make_engine(self, users_ddl: str):
        from sqlalchemy import create_engine
        from sqlalchemy.pool import StaticPool

        engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        with engine.connect() as conn:
            conn.execute(text(users_ddl))
            conn.commit()
        return engine

    def test_upgrade_skips_is_admin_backfill_when_column_missing(self):
        import importlib

        m081 = importlib.import_module(
            "app.database.migrations.081_add_role_and_api_tokens"
        )
        engine = self._make_engine("""
            CREATE TABLE users (
                id INTEGER PRIMARY KEY,
                username TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                is_active BOOLEAN DEFAULT 1 NOT NULL
            )
        """)

        with engine.connect() as conn:
            conn.execute(
                text("""
                INSERT INTO users (id, username, password_hash, is_active)
                VALUES (1, 'admin', 'hash', 1)
            """)
            )
            conn.commit()

            m081.upgrade(conn)

            columns = [
                row[1]
                for row in conn.execute(text("PRAGMA table_info(users)")).fetchall()
            ]
            role = conn.execute(
                text("SELECT role FROM users WHERE id = 1")
            ).scalar_one()
            token_tables = conn.execute(
                text("""
                SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'api_tokens'
            """)
            ).fetchall()

        assert "role" in columns
        assert role == "viewer"
        assert token_tables == [("api_tokens",)]

    def test_upgrade_migrates_legacy_is_admin_values(self):
        import importlib

        m081 = importlib.import_module(
            "app.database.migrations.081_add_role_and_api_tokens"
        )
        engine = self._make_engine("""
            CREATE TABLE users (
                id INTEGER PRIMARY KEY,
                username TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                is_active BOOLEAN DEFAULT 1 NOT NULL,
                is_admin BOOLEAN
            )
        """)

        with engine.connect() as conn:
            conn.execute(
                text("""
                INSERT INTO users (id, username, password_hash, is_active, is_admin)
                VALUES
                    (1, 'admin', 'hash', 1, 1),
                    (2, 'viewer', 'hash', 1, 0)
            """)
            )
            conn.commit()

            m081.upgrade(conn)

            roles = conn.execute(
                text("SELECT username, role FROM users ORDER BY id")
            ).fetchall()

        assert roles == [("admin", "admin"), ("viewer", "viewer")]

"""
Tests for borgmatic export/import service.
"""

import pytest
import yaml
from app.services.borgmatic_service import BorgmaticExportService, BorgmaticImportService
from app.database.models import Repository, ScheduledJob, SSHKey


class TestBorgmaticExportService:
    """Tests for exporting Borg UI configurations to borgmatic format."""

    def test_export_local_repository(self, db_session, sample_repository):
        """Test exporting a local repository."""
        export_service = BorgmaticExportService(db_session)

        config = export_service.export_repository(sample_repository, include_schedule=False, include_borg_ui_metadata=False)

        # New flat format (v1.8.0+)
        assert 'repositories' in config
        assert config['repositories'] == [sample_repository.path]
        assert config['compression'] == sample_repository.compression

    def test_export_with_source_directories(self, db_session, sample_repository):
        """Test exporting repository with source directories."""
        import json
        sample_repository.source_directories = json.dumps(['/home/user', '/etc'])
        db_session.commit()

        export_service = BorgmaticExportService(db_session)
        config = export_service.export_repository(sample_repository, include_schedule=False, include_borg_ui_metadata=False)

        # New flat format
        assert config['source_directories'] == ['/home/user', '/etc']

    def test_export_with_exclude_patterns(self, db_session, sample_repository):
        """Test exporting repository with exclude patterns."""
        import json
        sample_repository.exclude_patterns = json.dumps(['*.pyc', '*.tmp'])
        db_session.commit()

        export_service = BorgmaticExportService(db_session)
        config = export_service.export_repository(sample_repository, include_schedule=False, include_borg_ui_metadata=False)

        # New flat format
        assert config['exclude_patterns'] == ['*.pyc', '*.tmp']

    def test_export_with_hooks(self, db_session, sample_repository):
        """Test exporting repository with pre/post backup hooks."""
        sample_repository.pre_backup_script = 'echo "Starting backup"'
        sample_repository.post_backup_script = 'echo "Backup completed"'
        db_session.commit()

        export_service = BorgmaticExportService(db_session)
        config = export_service.export_repository(sample_repository, include_schedule=False, include_borg_ui_metadata=False)

        # New flat format with hooks as list
        assert 'hooks' in config
        assert isinstance(config['hooks'], list)
        assert len(config['hooks']) == 2
        assert config['hooks'][0]['name'] == 'before_backup'
        assert config['hooks'][0]['command'] == 'echo "Starting backup"'
        assert config['hooks'][1]['name'] == 'after_backup'
        assert config['hooks'][1]['command'] == 'echo "Backup completed"'

    def test_export_with_borg_ui_metadata(self, db_session, sample_repository):
        """Test exporting repository with Borg UI metadata for round-trip."""
        export_service = BorgmaticExportService(db_session)
        config = export_service.export_repository(sample_repository, include_schedule=False, include_borg_ui_metadata=True)

        assert 'borg_ui_metadata' in config
        assert config['borg_ui_metadata']['repository']['name'] == sample_repository.name
        assert config['borg_ui_metadata']['repository']['encryption'] == sample_repository.encryption

    def test_export_with_schedule(self, db_session, sample_repository, sample_scheduled_job):
        """Test exporting repository with backup schedule."""
        export_service = BorgmaticExportService(db_session)
        config = export_service.export_repository(sample_repository, include_schedule=True, include_borg_ui_metadata=True)

        # New flat format - retention keys at top level
        assert 'keep_daily' in config
        assert config['keep_daily'] == sample_scheduled_job.prune_keep_daily
        assert 'borg_ui_metadata' in config
        assert 'schedule' in config['borg_ui_metadata']
        assert config['borg_ui_metadata']['schedule']['cron_expression'] == sample_scheduled_job.cron_expression

    def test_export_to_yaml(self, db_session, sample_repository):
        """Test exporting to YAML string."""
        export_service = BorgmaticExportService(db_session)
        yaml_content = export_service.export_to_yaml(include_schedules=False, include_borg_ui_metadata=False)

        assert yaml_content
        data = yaml.safe_load(yaml_content)
        # New flat format (v1.8.0+)
        assert 'repositories' in data
        assert len(data['repositories']) > 0
        assert 'compression' in data

    def test_export_ssh_repository(self, db_session):
        """Test exporting SSH repository."""
        # Create SSH repository with full SSH URL as path
        ssh_url = 'ssh://backupuser@backup.example.com:22/backup/repo.borg'
        repo = Repository(
            name='ssh-repo',
            path=ssh_url,
            repository_type='ssh',
            host='backup.example.com',
            port=22,
            username='backupuser',
            encryption='repokey',
            compression='lz4'
        )
        db_session.add(repo)
        db_session.commit()

        export_service = BorgmaticExportService(db_session)
        config = export_service.export_repository(repo, include_schedule=False, include_borg_ui_metadata=False)

        # New flat format - path is returned as-is (already full SSH URL)
        assert config['repositories'] == [ssh_url]


class TestBorgmaticImportService:
    """Tests for importing borgmatic configurations into Borg UI."""

    def test_import_basic_borgmatic_config(self, db_session):
        """Test importing a basic borgmatic configuration."""
        yaml_content = """
location:
  source_directories:
    - /home/user
    - /etc
  repositories:
    - /backup/repo.borg
  exclude_patterns:
    - "*.pyc"
    - "*.tmp"

storage:
  compression: lz4

retention:
  keep_daily: 7
  keep_weekly: 4
"""

        import_service = BorgmaticImportService(db_session)
        result = import_service.import_from_yaml(yaml_content, merge_strategy='skip_duplicates', dry_run=False)

        assert result['success']
        assert result['repositories_created'] == 1

        # Verify repository was created
        repo = db_session.query(Repository).filter(Repository.name == 'repo').first()
        assert repo is not None
        assert repo.path == '/backup/repo.borg'
        assert repo.compression == 'lz4'

    def test_import_with_hooks(self, db_session):
        """Test importing configuration with hooks."""
        yaml_content = """
location:
  repositories:
    - /backup/repo2.borg

hooks:
  before_backup:
    - echo "Starting"
  after_backup:
    - echo "Done"
"""

        import_service = BorgmaticImportService(db_session)
        result = import_service.import_from_yaml(yaml_content, merge_strategy='skip_duplicates', dry_run=False)

        assert result['success']
        repo = db_session.query(Repository).filter(Repository.name == 'repo2').first()
        assert repo.pre_backup_script == 'echo "Starting"'
        assert repo.post_backup_script == 'echo "Done"'

    def test_import_skip_duplicates(self, db_session, sample_repository):
        """Test skip_duplicates merge strategy."""
        yaml_content = f"""
location:
  repositories:
    - {sample_repository.path}
"""

        import_service = BorgmaticImportService(db_session)
        result = import_service.import_from_yaml(yaml_content, merge_strategy='skip_duplicates', dry_run=False)

        assert result['success']
        assert result['repositories_created'] == 0
        assert len(result['warnings']) > 0
        assert 'duplicate' in result['warnings'][0].lower()

    def test_import_dry_run(self, db_session):
        """Test dry run mode doesn't create anything."""
        yaml_content = """
location:
  repositories:
    - /backup/dryrun.borg
"""

        initial_count = db_session.query(Repository).count()

        import_service = BorgmaticImportService(db_session)
        result = import_service.import_from_yaml(yaml_content, merge_strategy='skip_duplicates', dry_run=True)

        assert result['success']
        assert result['repositories_created'] == 1

        # Verify no repository was actually created
        final_count = db_session.query(Repository).count()
        assert final_count == initial_count

    def test_import_ssh_repository(self, db_session):
        """Test importing SSH repository."""
        yaml_content = """
location:
  repositories:
    - user@backup.example.com:/backup/ssh-repo.borg

storage:
  compression: zstd
"""

        import_service = BorgmaticImportService(db_session)
        result = import_service.import_from_yaml(yaml_content, merge_strategy='skip_duplicates', dry_run=False)

        assert result['success']
        assert result['repositories_created'] == 1

        repo = db_session.query(Repository).filter(Repository.name == 'ssh-repo').first()
        assert repo is not None
        assert repo.repository_type == 'ssh'
        assert repo.host == 'backup.example.com'
        assert repo.username == 'user'
        assert repo.path == '/backup/ssh-repo.borg'

    def test_import_borg_ui_export(self, db_session):
        """Test importing Borg UI export format (round-trip) - new format."""
        yaml_content = """
location:
  source_directories:
    - /home/user
  repositories:
    - /backup/repo.borg

storage:
  compression: lz4

borg_ui_metadata:
  export_version: "1.0"
  export_date: "2025-12-05T10:00:00Z"
  repositories:
    - repository:
        name: test-repo
        encryption: repokey
        mode: full
        custom_flags: "--stats"
"""

        import_service = BorgmaticImportService(db_session)
        result = import_service.import_from_yaml(yaml_content, merge_strategy='skip_duplicates', dry_run=False)

        assert result['success']
        assert result['repositories_created'] == 1

        repo = db_session.query(Repository).filter(Repository.name == 'test-repo').first()
        assert repo is not None
        assert repo.custom_flags == '--stats'
        assert repo.mode == 'full'

    def test_import_invalid_yaml(self, db_session):
        """Test importing invalid YAML."""
        yaml_content = "invalid: yaml: content:"

        import_service = BorgmaticImportService(db_session)
        result = import_service.import_from_yaml(yaml_content, merge_strategy='skip_duplicates', dry_run=False)

        assert not result['success']
        assert 'error' in result

    def test_import_rename_strategy(self, db_session, sample_repository):
        """Test rename merge strategy."""
        # Use a different path to avoid path uniqueness constraint
        yaml_content = f"""
location:
  repositories:
    - /backup/another-repo.borg

borg_ui_metadata:
  repositories:
    - repository:
        name: {sample_repository.name}
        encryption: repokey
        mode: full
"""

        import_service = BorgmaticImportService(db_session)
        result = import_service.import_from_yaml(yaml_content, merge_strategy='rename', dry_run=False)

        assert result['success']
        assert result['repositories_created'] == 1

        # Verify renamed repository exists
        repos = db_session.query(Repository).filter(Repository.name.like(f'{sample_repository.name}%')).all()
        assert len(repos) == 2  # Original + renamed


# Fixtures
@pytest.fixture
def sample_repository(db_session):
    """Create a sample repository for testing."""
    repo = Repository(
        name='test-repo',
        path='/backup/test-repo.borg',
        encryption='repokey',
        compression='lz4',
        repository_type='local'
    )
    db_session.add(repo)
    db_session.commit()
    return repo


@pytest.fixture
def sample_scheduled_job(db_session, sample_repository):
    """Create a sample scheduled job for testing."""
    job = ScheduledJob(
        name='test-job',
        cron_expression='0 2 * * *',
        repository=sample_repository.path,
        enabled=True,
        prune_keep_daily=7,
        prune_keep_weekly=4,
        prune_keep_monthly=6,
        prune_keep_yearly=1,
        run_prune_after=True,
        run_compact_after=False
    )
    db_session.add(job)
    db_session.commit()
    return job

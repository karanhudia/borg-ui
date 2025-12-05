"""
Service for exporting and importing borgmatic configurations.

This service handles:
1. Exporting Borg UI configurations to borgmatic YAML format
2. Importing borgmatic YAML configs into Borg UI
3. Round-trip import/export for multi-server deployments
"""

import json
import yaml
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy.orm import Session

from app.database.models import Repository, ScheduledJob, SSHKey, SSHConnection


class BorgmaticExportService:
    """Handles exporting Borg UI configurations to borgmatic format."""

    def __init__(self, db: Session):
        self.db = db

    def export_repository(
        self,
        repository: Repository,
        include_schedule: bool = True,
        include_borg_ui_metadata: bool = True
    ) -> Dict[str, Any]:
        """
        Export a single repository to borgmatic format.

        Args:
            repository: Repository model instance
            include_schedule: Include backup schedule if exists
            include_borg_ui_metadata: Include Borg UI specific metadata for round-trip

        Returns:
            Dictionary representing borgmatic configuration
        """
        config = {}

        # Location section
        config['location'] = self._build_location_section(repository)

        # Storage section
        config['storage'] = self._build_storage_section(repository)

        # Retention section (from scheduled job if exists)
        if include_schedule:
            scheduled_job = self._get_scheduled_job_for_repository(repository)
            if scheduled_job:
                config['retention'] = self._build_retention_section(scheduled_job)

        # Consistency section (from repository check settings)
        if repository.check_interval_days:
            config['consistency'] = self._build_consistency_section(repository)

        # Hooks section
        hooks = self._build_hooks_section(repository)
        if hooks:
            config['hooks'] = hooks

        # Borg UI metadata (for round-trip import/export)
        if include_borg_ui_metadata:
            config['borg_ui_metadata'] = self._build_metadata_section(
                repository,
                self._get_scheduled_job_for_repository(repository) if include_schedule else None
            )

        return config

    def export_all_repositories(
        self,
        repository_ids: Optional[List[int]] = None,
        include_schedules: bool = True,
        include_borg_ui_metadata: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Export multiple repositories to borgmatic format.

        Args:
            repository_ids: List of repository IDs to export (None = all)
            include_schedules: Include backup schedules
            include_borg_ui_metadata: Include Borg UI metadata

        Returns:
            List of borgmatic configurations
        """
        query = self.db.query(Repository)
        if repository_ids:
            query = query.filter(Repository.id.in_(repository_ids))

        repositories = query.all()
        configs = []

        for repo in repositories:
            config = self.export_repository(
                repo,
                include_schedule=include_schedules,
                include_borg_ui_metadata=include_borg_ui_metadata
            )
            configs.append(config)

        return configs

    def export_to_yaml(
        self,
        repository_ids: Optional[List[int]] = None,
        include_schedules: bool = True,
        include_borg_ui_metadata: bool = True,
        multi_file: bool = False
    ) -> str:
        """
        Export configurations to YAML string.

        Args:
            repository_ids: Repository IDs to export
            include_schedules: Include schedules
            include_borg_ui_metadata: Include metadata
            multi_file: If True, return dict with filename: yaml_content

        Returns:
            YAML string or dict of YAML strings (if multi_file=True)
        """
        configs = self.export_all_repositories(
            repository_ids,
            include_schedules,
            include_borg_ui_metadata
        )

        if not configs:
            return ""

        # Add export metadata header
        export_data = {
            'borg_ui_export': {
                'version': '1.0',
                'app_version': '1.26.0',  # TODO: Get from actual version file
                'export_date': datetime.now(timezone.utc).isoformat(),
                'total_repositories': len(configs)
            },
            'configurations': configs
        }

        return yaml.dump(export_data, default_flow_style=False, sort_keys=False)

    def _build_location_section(self, repository: Repository) -> Dict[str, Any]:
        """Build borgmatic location section."""
        location = {}

        # Source directories
        if repository.source_directories:
            try:
                source_dirs = json.loads(repository.source_directories)
                location['source_directories'] = source_dirs
            except (json.JSONDecodeError, TypeError):
                pass

        # Repository path
        repo_path = self._build_repository_path(repository)
        if repo_path:
            location['repositories'] = [repo_path]

        # Exclude patterns
        if repository.exclude_patterns:
            try:
                exclude_patterns = json.loads(repository.exclude_patterns)
                location['exclude_patterns'] = exclude_patterns
            except (json.JSONDecodeError, TypeError):
                pass

        return location

    def _build_storage_section(self, repository: Repository) -> Dict[str, Any]:
        """Build borgmatic storage section."""
        storage = {}

        # Compression
        if repository.compression:
            storage['compression'] = repository.compression

        # SSH command (if SSH repository)
        if repository.repository_type == 'ssh' and repository.ssh_key_id:
            ssh_key = self.db.query(SSHKey).filter(SSHKey.id == repository.ssh_key_id).first()
            if ssh_key:
                storage['ssh_command'] = f'ssh -i /path/to/{ssh_key.name}_key'

        # Note about passphrase (don't export actual passphrase)
        storage['_passphrase_note'] = 'Set BORG_PASSPHRASE environment variable or use encryption_passcommand'

        return storage

    def _build_retention_section(self, scheduled_job: ScheduledJob) -> Dict[str, Any]:
        """Build borgmatic retention section from scheduled job."""
        retention = {}

        if scheduled_job.prune_keep_hourly > 0:
            retention['keep_hourly'] = scheduled_job.prune_keep_hourly
        if scheduled_job.prune_keep_daily > 0:
            retention['keep_daily'] = scheduled_job.prune_keep_daily
        if scheduled_job.prune_keep_weekly > 0:
            retention['keep_weekly'] = scheduled_job.prune_keep_weekly
        if scheduled_job.prune_keep_monthly > 0:
            retention['keep_monthly'] = scheduled_job.prune_keep_monthly
        if scheduled_job.prune_keep_yearly > 0:
            retention['keep_yearly'] = scheduled_job.prune_keep_yearly

        return retention

    def _build_consistency_section(self, repository: Repository) -> Dict[str, Any]:
        """Build borgmatic consistency section."""
        return {
            'checks': ['repository', 'archives'],
            'check_last': 3,
            '_check_interval_note': f'Scheduled every {repository.check_interval_days} days in Borg UI'
        }

    def _build_hooks_section(self, repository: Repository) -> Optional[Dict[str, Any]]:
        """Build borgmatic hooks section."""
        hooks = {}

        if repository.pre_backup_script:
            hooks['before_backup'] = [repository.pre_backup_script]

        if repository.post_backup_script:
            hooks['after_backup'] = [repository.post_backup_script]

        return hooks if hooks else None

    def _build_metadata_section(
        self,
        repository: Repository,
        scheduled_job: Optional[ScheduledJob]
    ) -> Dict[str, Any]:
        """Build Borg UI metadata section for round-trip import."""
        metadata = {
            'repository': {
                'id': repository.id,
                'name': repository.name,
                'encryption': repository.encryption,
                'repository_type': repository.repository_type,
                'mode': repository.mode,
                'hook_timeout': repository.hook_timeout,
                'continue_on_hook_failure': repository.continue_on_hook_failure,
            }
        }

        if repository.custom_flags:
            metadata['repository']['custom_flags'] = repository.custom_flags

        if repository.check_interval_days:
            metadata['checks'] = {
                'enabled': True,
                'interval_days': repository.check_interval_days,
                'max_duration': repository.check_max_duration,
                'notify_on_success': repository.notify_on_check_success,
                'notify_on_failure': repository.notify_on_check_failure,
            }

        if scheduled_job:
            metadata['schedule'] = {
                'id': scheduled_job.id,
                'name': scheduled_job.name,
                'cron_expression': scheduled_job.cron_expression,
                'enabled': scheduled_job.enabled,
                'archive_name_template': scheduled_job.archive_name_template,
                'run_prune_after': scheduled_job.run_prune_after,
                'run_compact_after': scheduled_job.run_compact_after,
            }

        if repository.repository_type == 'ssh':
            metadata['ssh'] = {
                'host': repository.host,
                'port': repository.port,
                'username': repository.username,
                'remote_path': repository.remote_path,
            }

        return metadata

    def _build_repository_path(self, repository: Repository) -> str:
        """Build borgmatic-style repository path."""
        if repository.repository_type == 'local':
            return repository.path
        elif repository.repository_type == 'ssh':
            # Format: user@host:path
            return f"{repository.username}@{repository.host}:{repository.path}"
        else:
            return repository.path

    def _get_scheduled_job_for_repository(self, repository: Repository) -> Optional[ScheduledJob]:
        """Get scheduled job associated with repository."""
        return self.db.query(ScheduledJob).filter(
            ScheduledJob.repository == repository.path
        ).first()


class BorgmaticImportService:
    """Handles importing borgmatic configurations into Borg UI."""

    def __init__(self, db: Session):
        self.db = db

    def import_from_yaml(
        self,
        yaml_content: str,
        merge_strategy: str = 'skip_duplicates',
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        Import borgmatic configuration from YAML.

        Args:
            yaml_content: YAML configuration string
            merge_strategy: How to handle conflicts
                - 'skip_duplicates': Skip if name/path exists
                - 'replace': Replace existing with same name
                - 'rename': Auto-rename to avoid conflicts
            dry_run: If True, don't save to database

        Returns:
            Import summary with created/updated counts and warnings
        """
        try:
            data = yaml.safe_load(yaml_content)
        except yaml.YAMLError as e:
            return {
                'success': False,
                'error': f'Invalid YAML: {str(e)}'
            }

        # Check if this is a Borg UI export
        is_borg_ui_export = 'borg_ui_export' in data

        if is_borg_ui_export:
            return self._import_borg_ui_export(data, merge_strategy, dry_run)
        else:
            return self._import_borgmatic_config(data, merge_strategy, dry_run)

    def _import_borg_ui_export(
        self,
        data: Dict[str, Any],
        merge_strategy: str,
        dry_run: bool
    ) -> Dict[str, Any]:
        """Import Borg UI export format (round-trip)."""
        summary = {
            'success': True,
            'repositories_created': 0,
            'repositories_updated': 0,
            'schedules_created': 0,
            'schedules_updated': 0,
            'warnings': [],
            'errors': []
        }

        configurations = data.get('configurations', [])

        for config in configurations:
            try:
                result = self._import_single_repository(config, merge_strategy, dry_run)
                summary['repositories_created'] += result.get('repository_created', 0)
                summary['repositories_updated'] += result.get('repository_updated', 0)
                summary['schedules_created'] += result.get('schedule_created', 0)
                summary['schedules_updated'] += result.get('schedule_updated', 0)
                summary['warnings'].extend(result.get('warnings', []))
            except Exception as e:
                summary['errors'].append(f"Failed to import repository: {str(e)}")

        if not dry_run and summary['repositories_created'] + summary['repositories_updated'] > 0:
            self.db.commit()

        return summary

    def _import_borgmatic_config(
        self,
        data: Dict[str, Any],
        merge_strategy: str,
        dry_run: bool
    ) -> Dict[str, Any]:
        """Import standard borgmatic configuration."""
        # Standard borgmatic format - single repository config
        return self._import_single_repository(data, merge_strategy, dry_run)

    def _import_single_repository(
        self,
        config: Dict[str, Any],
        merge_strategy: str,
        dry_run: bool
    ) -> Dict[str, Any]:
        """Import a single repository configuration."""
        result = {
            'repository_created': 0,
            'repository_updated': 0,
            'schedule_created': 0,
            'schedule_updated': 0,
            'warnings': []
        }

        # Extract repository information
        location = config.get('location', {})
        storage = config.get('storage', {})
        retention = config.get('retention', {})
        hooks = config.get('hooks', {})
        metadata = config.get('borg_ui_metadata', {})

        # Parse repository path
        repo_paths = location.get('repositories', [])
        if not repo_paths:
            raise ValueError("No repository path found in configuration")

        repo_path_str = repo_paths[0]
        repo_name, repo_path, repo_type, ssh_info = self._parse_repository_path(
            repo_path_str,
            metadata.get('repository', {})
        )

        # Check for existing repository
        existing_repo = self.db.query(Repository).filter(
            (Repository.name == repo_name) | (Repository.path == repo_path)
        ).first()

        if existing_repo:
            if merge_strategy == 'skip_duplicates':
                result['warnings'].append(f"Skipped duplicate repository: {repo_name}")
                return result
            elif merge_strategy == 'rename':
                repo_name = self._generate_unique_name(repo_name)
            elif merge_strategy == 'replace':
                repository = existing_repo
                result['repository_updated'] = 1

        if not existing_repo or merge_strategy != 'replace':
            # Create new repository
            repository = Repository()
            result['repository_created'] = 1

        # Set repository fields
        repository.name = repo_name
        repository.path = repo_path
        repository.repository_type = repo_type
        repository.encryption = metadata.get('repository', {}).get('encryption', 'repokey')
        repository.compression = storage.get('compression', 'lz4')
        repository.mode = metadata.get('repository', {}).get('mode', 'full')

        # Source directories
        if location.get('source_directories'):
            repository.source_directories = json.dumps(location['source_directories'])

        # Exclude patterns
        if location.get('exclude_patterns'):
            repository.exclude_patterns = json.dumps(location['exclude_patterns'])

        # Hooks
        if hooks.get('before_backup'):
            repository.pre_backup_script = '\n'.join(hooks['before_backup'])
        if hooks.get('after_backup'):
            repository.post_backup_script = '\n'.join(hooks['after_backup'])

        repository.hook_timeout = metadata.get('repository', {}).get('hook_timeout', 300)
        repository.continue_on_hook_failure = metadata.get('repository', {}).get('continue_on_hook_failure', False)

        # Custom flags
        if metadata.get('repository', {}).get('custom_flags'):
            repository.custom_flags = metadata['repository']['custom_flags']

        # SSH settings
        if repo_type == 'ssh' and ssh_info:
            repository.host = ssh_info['host']
            repository.port = ssh_info.get('port', 22)
            repository.username = ssh_info['username']
            repository.remote_path = ssh_info.get('remote_path')
            result['warnings'].append(f"SSH repository created but SSH key must be configured manually: {repo_name}")

        # Check settings
        check_metadata = metadata.get('checks', {})
        if check_metadata.get('enabled'):
            repository.check_interval_days = check_metadata.get('interval_days', 7)
            repository.check_max_duration = check_metadata.get('max_duration', 3600)
            repository.notify_on_check_success = check_metadata.get('notify_on_success', False)
            repository.notify_on_check_failure = check_metadata.get('notify_on_failure', True)

        # Passphrase warning
        result['warnings'].append(f"Repository passphrase not imported - please set manually: {repo_name}")

        if not dry_run:
            if result['repository_created']:
                self.db.add(repository)
                self.db.flush()  # Get repository ID

        # Import scheduled job if retention settings exist
        if retention and result['repository_created']:
            schedule_result = self._import_schedule(
                repository,
                retention,
                metadata.get('schedule', {}),
                merge_strategy,
                dry_run
            )
            result['schedule_created'] = schedule_result.get('created', 0)
            result['schedule_updated'] = schedule_result.get('updated', 0)
            result['warnings'].extend(schedule_result.get('warnings', []))

        return result

    def _import_schedule(
        self,
        repository: Repository,
        retention: Dict[str, Any],
        schedule_metadata: Dict[str, Any],
        merge_strategy: str,
        dry_run: bool
    ) -> Dict[str, Any]:
        """Import backup schedule for repository."""
        result = {'created': 0, 'updated': 0, 'warnings': []}

        # Generate schedule name
        schedule_name = schedule_metadata.get('name') or f"{repository.name}-backup"

        # Check for existing schedule
        existing_schedule = self.db.query(ScheduledJob).filter(
            ScheduledJob.name == schedule_name
        ).first()

        if existing_schedule:
            if merge_strategy == 'skip_duplicates':
                result['warnings'].append(f"Skipped duplicate schedule: {schedule_name}")
                return result
            elif merge_strategy == 'rename':
                schedule_name = self._generate_unique_name(schedule_name, model=ScheduledJob)
            elif merge_strategy == 'replace':
                scheduled_job = existing_schedule
                result['updated'] = 1

        if not existing_schedule or merge_strategy != 'replace':
            scheduled_job = ScheduledJob()
            result['created'] = 1

        # Set schedule fields
        scheduled_job.name = schedule_name
        scheduled_job.repository = repository.path
        scheduled_job.cron_expression = schedule_metadata.get('cron_expression', '0 2 * * *')
        scheduled_job.enabled = schedule_metadata.get('enabled', True)
        scheduled_job.archive_name_template = schedule_metadata.get('archive_name_template', '{hostname}-{now}')
        scheduled_job.run_prune_after = schedule_metadata.get('run_prune_after', True)
        scheduled_job.run_compact_after = schedule_metadata.get('run_compact_after', False)

        # Retention settings
        scheduled_job.prune_keep_hourly = retention.get('keep_hourly', 0)
        scheduled_job.prune_keep_daily = retention.get('keep_daily', 7)
        scheduled_job.prune_keep_weekly = retention.get('keep_weekly', 4)
        scheduled_job.prune_keep_monthly = retention.get('keep_monthly', 6)
        scheduled_job.prune_keep_yearly = retention.get('keep_yearly', 1)

        if not dry_run and result['created']:
            self.db.add(scheduled_job)

        return result

    def _parse_repository_path(
        self,
        repo_path: str,
        metadata: Dict[str, Any]
    ) -> Tuple[str, str, str, Optional[Dict[str, Any]]]:
        """
        Parse repository path and extract information.

        Returns:
            (name, path, type, ssh_info)
        """
        # Check if SSH repository (format: user@host:path)
        if '@' in repo_path and ':' in repo_path:
            # SSH repository
            user_host, path = repo_path.split(':', 1)
            username, host = user_host.split('@', 1)

            # Extract name from path (last directory)
            name = path.rstrip('/').split('/')[-1].replace('.borg', '')

            ssh_info = {
                'host': host,
                'username': username,
                'port': metadata.get('ssh', {}).get('port', 22),
                'remote_path': metadata.get('ssh', {}).get('remote_path')
            }

            return name, path, 'ssh', ssh_info
        else:
            # Local repository
            name = repo_path.rstrip('/').split('/')[-1].replace('.borg', '')
            return name, repo_path, 'local', None

    def _generate_unique_name(
        self,
        base_name: str,
        model=Repository
    ) -> str:
        """Generate a unique name by appending a number."""
        counter = 1
        name = base_name

        while True:
            if model == Repository:
                existing = self.db.query(Repository).filter(Repository.name == name).first()
            else:
                existing = self.db.query(ScheduledJob).filter(ScheduledJob.name == name).first()

            if not existing:
                return name

            name = f"{base_name}-{counter}"
            counter += 1

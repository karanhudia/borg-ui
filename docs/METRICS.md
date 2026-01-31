# Prometheus Metrics

Borg-UI exposes Prometheus metrics at the `/metrics` endpoint for monitoring and alerting.

## Endpoint

```
GET http://your-borg-ui:8081/metrics
```

**Note:** The `/metrics` endpoint does not require authentication to allow Prometheus to scrape freely.

## Prometheus Configuration

Add this to your `prometheus.yml`:

```yaml
scrape_configs:
  - job_name: 'borg-ui'
    static_configs:
      - targets: ['borg-ui:8081']
    scrape_interval: 60s
```

## Docker Compose Example

```yaml
services:
  prometheus:
    image: prom/prometheus:latest
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus-data:/prometheus
    ports:
      - "9090:9090"
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'

  borg-ui:
    image: ghcr.io/borgui/borg-ui:latest
    # ... your borg-ui config

volumes:
  prometheus-data:
```

## Available Metrics

### Repository Metrics

- `borg_repository_info` - Repository information (labels: repository, path, type, mode)
- `borg_repository_size_bytes` - Repository total size in bytes
- `borg_repository_archive_count` - Number of archives in repository
- `borg_repository_last_backup_timestamp` - Unix timestamp of last backup
- `borg_repository_last_check_timestamp` - Unix timestamp of last check
- `borg_repository_last_compact_timestamp` - Unix timestamp of last compact

### Backup Job Metrics

- `borg_backup_jobs_total` - Total number of backup jobs (labels: repository, status)
- `borg_backup_orphaned_jobs_total` - Backup jobs for deleted/renamed repositories (labels: repository_path, status)
- `borg_backup_last_job_success` - Last backup job success (1=success, 0=failure)
- `borg_backup_last_duration_seconds` - Duration of last backup job in seconds
- `borg_backup_last_original_size_bytes` - Original size of last backup in bytes
- `borg_backup_last_deduplicated_size_bytes` - Deduplicated size of last backup in bytes

### Restore Job Metrics

- `borg_restore_jobs_total` - Total number of restore jobs (labels: status)

### Check Job Metrics

- `borg_check_jobs_total` - Total number of check jobs (labels: repository, status)
- `borg_check_last_duration_seconds` - Duration of last check job in seconds

### Compact Job Metrics

- `borg_compact_jobs_total` - Total number of compact jobs (labels: repository, status)
- `borg_compact_last_duration_seconds` - Duration of last compact job in seconds

### Prune Job Metrics

- `borg_prune_jobs_total` - Total number of prune jobs (labels: repository, status)

### System Metrics

- `borg_ui_repositories_total` - Total number of repositories
- `borg_ui_scheduled_jobs_total` - Total number of scheduled jobs
- `borg_ui_scheduled_jobs_enabled` - Number of enabled scheduled jobs
- `borg_ui_active_jobs` - Number of currently running jobs (labels: type)

## Example Queries

### Check if last backup succeeded
```promql
borg_backup_last_job_success{repository="my-repo"} == 0
```

### Time since last backup
```promql
time() - borg_repository_last_backup_timestamp{repository="my-repo"}
```

### Backup duration trend
```promql
rate(borg_backup_last_duration_seconds{repository="my-repo"}[1h])
```

### Repository size growth
```promql
delta(borg_repository_size_bytes{repository="my-repo"}[24h])
```

### Failed backups in last 24h
```promql
sum(increase(borg_backup_jobs_total{status="failed"}[24h])) by (repository)
```

## Alerting Examples

### Alert on backup failure
```yaml
groups:
  - name: borg_backup_alerts
    rules:
      - alert: BackupFailed
        expr: borg_backup_last_job_success == 0
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "Backup failed for {{ $labels.repository }}"
          description: "Last backup job failed for repository {{ $labels.repository }}"

      - alert: BackupOld
        expr: (time() - borg_repository_last_backup_timestamp) > 86400
        for: 1h
        labels:
          severity: warning
        annotations:
          summary: "No backup in 24h for {{ $labels.repository }}"
          description: "Repository {{ $labels.repository }} has not been backed up in over 24 hours"

      - alert: BackupSlow
        expr: borg_backup_last_duration_seconds > 3600
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Slow backup for {{ $labels.repository }}"
          description: "Backup took {{ $value }}s (>1h) for repository {{ $labels.repository }}"
```

## Grafana Dashboard

You can use the existing Borg Backup Status dashboard as a starting point:
https://grafana.com/grafana/dashboards/14516-borg-backup-status

Or create your own custom dashboard using the metrics above.

### Example Dashboard Panels

**Repository Size Over Time:**
```promql
borg_repository_size_bytes
```

**Backup Success Rate:**
```promql
sum(borg_backup_jobs_total{status="completed"}) by (repository) /
sum(borg_backup_jobs_total) by (repository)
```

**Active Jobs:**
```promql
borg_ui_active_jobs
```

**Backup Duration Heatmap:**
```promql
borg_backup_last_duration_seconds
```

## Troubleshooting

### Metrics endpoint returns empty
- Check that borg-ui is running
- Verify the endpoint: `curl http://borg-ui:8081/metrics`
- Check borg-ui logs for errors

### Prometheus can't scrape
- Verify network connectivity between Prometheus and borg-ui
- Check Prometheus targets page: `http://prometheus:9090/targets`
- Verify borg-ui port is accessible

### Missing metrics
- Metrics are only generated for existing data
- Run at least one backup/check/compact to see job metrics
- Repository metrics require repository to be created and synced

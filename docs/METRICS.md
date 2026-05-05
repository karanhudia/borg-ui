# Prometheus Metrics

Borg UI can expose Prometheus metrics at:

```text
/metrics
```

Metrics are disabled by default.

## Enable Metrics

Open Settings > System > Metrics Access.

Recommended settings:

- enable `/metrics`
- require a token
- keep the endpoint on a private network
- expose Grafana, not Borg UI metrics, to users

When token protection is enabled, Borg UI accepts either header:

```text
X-Borg-Metrics-Token: <token>
Authorization: Bearer <token>
```

If metrics are disabled, `/metrics` returns `404`.

## Prometheus Example

```yaml
scrape_configs:
  - job_name: borg-ui
    metrics_path: /metrics
    static_configs:
      - targets:
          - borg-web-ui:8081
    authorization:
      type: Bearer
      credentials: <your-generated-token>
```

Or:

```yaml
scrape_configs:
  - job_name: borg-ui
    metrics_path: /metrics
    static_configs:
      - targets:
          - borg-web-ui:8081
    http_headers:
      X-Borg-Metrics-Token:
        values:
          - <your-generated-token>
```

## Example Monitoring Stack

The repository includes an example stack:

- [examples/monitoring/docker-compose.yml](https://github.com/karanhudia/borg-ui/blob/main/examples/monitoring/docker-compose.yml)
- [examples/monitoring/prometheus.yml](https://github.com/karanhudia/borg-ui/blob/main/examples/monitoring/prometheus.yml)
- [examples/monitoring/grafana/provisioning/datasources/prometheus.yml](https://github.com/karanhudia/borg-ui/blob/main/examples/monitoring/grafana/provisioning/datasources/prometheus.yml)
- [examples/monitoring/grafana/provisioning/dashboards/dashboards.yml](https://github.com/karanhudia/borg-ui/blob/main/examples/monitoring/grafana/provisioning/dashboards/dashboards.yml)
- [examples/monitoring/grafana/provisioning/dashboards/json/borg-ui-overview.json](https://github.com/karanhudia/borg-ui/blob/main/examples/monitoring/grafana/provisioning/dashboards/json/borg-ui-overview.json)
- [examples/monitoring/grafana/provisioning/dashboards/json/borg-ui-jobs.json](https://github.com/karanhudia/borg-ui/blob/main/examples/monitoring/grafana/provisioning/dashboards/json/borg-ui-jobs.json)

## Metric Groups

Repository metrics:

- `borg_repository_info`
- `borg_repository_size_bytes`
- `borg_repository_archive_count`
- `borg_repository_last_backup_timestamp`
- `borg_repository_last_check_timestamp`
- `borg_repository_last_compact_timestamp`

Backup metrics:

- `borg_backup_jobs_total`
- `borg_backup_orphaned_jobs_total`
- `borg_backup_last_job_success`
- `borg_backup_last_duration_seconds`
- `borg_backup_last_original_size_bytes`
- `borg_backup_last_deduplicated_size_bytes`

Restore metrics:

- `borg_restore_jobs_total`

Maintenance metrics:

- `borg_check_jobs_total`
- `borg_compact_jobs_total`
- `borg_prune_jobs_total`

## Useful Queries

Last backup failed:

```text
borg_backup_last_job_success{repository="my-repo"} == 0
```

Time since last backup:

```text
time() - borg_repository_last_backup_timestamp{repository="my-repo"}
```

Failed backups in the last 24 hours:

```text
sum(increase(borg_backup_jobs_total{status="failed"}[24h])) by (repository)
```

## Troubleshooting

### Empty metrics

Run at least one backup, restore, check, prune, or compact job. Some metrics are created only after data exists.

### 404

Metrics are disabled.

### 401 or 403

Token protection is enabled and the request did not include a valid token.

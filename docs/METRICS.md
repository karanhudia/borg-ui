# Prometheus Metrics

Borg-UI can expose Prometheus metrics at `/metrics` for monitoring and alerting.

Metrics are disabled by default. If you enable them, the recommended setup is:

- keep `/metrics` on a private network
- require a shared metrics token
- let Prometheus or Grafana be the public-facing consumer, not borg-ui itself

## Enable Metrics

In `Settings -> System -> Metrics Access`:

- turn on `Enable /metrics endpoint`
- turn on `Require token for /metrics`
- save to let borg-ui generate a token
- copy the token from the one-time dialog and store it in Prometheus

When token protection is enabled, borg-ui accepts either of these headers:

- `X-Borg-Metrics-Token: <token>`
- `Authorization: Bearer <token>`

If metrics remain disabled, `/metrics` returns `404`.

## Endpoint

```text
GET http://your-borg-ui:8081/metrics
```

## Prometheus Configuration

Add this to your `prometheus.yml`:

```yaml
scrape_configs:
  - job_name: borg-ui
    scrape_interval: 60s
    metrics_path: /metrics
    static_configs:
      - targets:
          - borg-ui:8081
    authorization:
      type: Bearer
      credentials: <your-generated-metrics-token>
```

If you prefer a custom header instead of bearer auth:

```yaml
scrape_configs:
  - job_name: borg-ui
    static_configs:
      - targets:
          - borg-ui:8081
    http_headers:
      X-Borg-Metrics-Token:
        values:
          - <your-generated-metrics-token>
```

## Docker Compose Example

An example monitoring stack is included in this repository:

- [examples/monitoring/docker-compose.yml](/Users/karanhudia/Documents/Projects/borg-ui/examples/monitoring/docker-compose.yml)
- [examples/monitoring/prometheus.yml](/Users/karanhudia/Documents/Projects/borg-ui/examples/monitoring/prometheus.yml)
- [examples/monitoring/grafana/provisioning/datasources/prometheus.yml](/Users/karanhudia/Documents/Projects/borg-ui/examples/monitoring/grafana/provisioning/datasources/prometheus.yml)
- [examples/monitoring/grafana/provisioning/dashboards/dashboards.yml](/Users/karanhudia/Documents/Projects/borg-ui/examples/monitoring/grafana/provisioning/dashboards/dashboards.yml)
- [examples/monitoring/grafana/provisioning/dashboards/json/borg-ui-overview.json](/Users/karanhudia/Documents/Projects/borg-ui/examples/monitoring/grafana/provisioning/dashboards/json/borg-ui-overview.json)
- [examples/monitoring/grafana/provisioning/dashboards/json/borg-ui-jobs.json](/Users/karanhudia/Documents/Projects/borg-ui/examples/monitoring/grafana/provisioning/dashboards/json/borg-ui-jobs.json)

Bring it up with:

```bash
docker compose -f docker-compose.yml -f examples/monitoring/docker-compose.yml up -d
```

Before starting Prometheus, set the generated metrics token in `examples/monitoring/prometheus.yml`.

This example keeps Prometheus and Grafana on the same private Docker network as borg-ui while exposing:

- Prometheus on `http://localhost:9090`
- Grafana on `http://localhost:3000`

Default Grafana credentials in the example:

- username: `admin`
- password: `admin`

Change those before using the stack beyond local testing.

The example also provisions an official starter dashboard pack automatically:

- `Borg UI / Borg UI Overview`
- `Borg UI / Borg UI Jobs`

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
- `borg_backup_orphaned_jobs_total` - Backup jobs for deleted or renamed repositories (labels: repository_path, status)
- `borg_backup_last_job_success` - Last backup job success (`1` = success, `0` = failure)
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

### Repository size growth

```promql
delta(borg_repository_size_bytes{repository="my-repo"}[24h])
```

### Failed backups in last 24h

```promql
sum(increase(borg_backup_jobs_total{status="failed"}[24h])) by (repository)
```

## Grafana Consumption

You can start from the community Borg dashboard:

https://grafana.com/grafana/dashboards/14516-borg-backup-status

The shipped dashboards cover the main views already:

- fleet overview and backup freshness
- repository growth and last backup duration
- backup outcomes over the last 24 hours
- maintenance totals and last-backup success state

If you want to build further custom dashboards, useful panel queries include:

- repository size over time: `borg_repository_size_bytes`
- backup success rate: `sum(borg_backup_jobs_total{status="completed"}) by (repository) / sum(borg_backup_jobs_total) by (repository)`
- active jobs: `borg_ui_active_jobs`
- last backup age: `time() - borg_repository_last_backup_timestamp`

## Troubleshooting

### Metrics endpoint returns 404

- check that metrics are enabled in `Settings -> System`
- verify the request is hitting the correct borg-ui instance

### Metrics endpoint returns 401

- verify token protection is enabled
- check the exact token being sent by Prometheus
- confirm you copied the new token after generation or rotation

### Prometheus cannot scrape borg-ui

- verify network connectivity between Prometheus and borg-ui
- check Prometheus targets at `http://localhost:9090/targets`
- if auth is enabled, confirm the scrape job sends the token header

### Missing metrics

- metrics are generated from existing repository and job data
- run at least one backup, check, prune, compact, or restore to populate job metrics
- repository metrics require a repository to exist and be synced

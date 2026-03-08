# borgui.borg_ui — Ansible Collection

Ansible collection for managing [borg-ui](https://github.com/borgui/borg-ui) backup resources via its REST API.

## FQCN

`borgui.borg_ui`

## Requirements

- Ansible Core 2.14+
- Python 3.8+
- A running borg-ui instance
- borg-ui API credentials (JWT token **or** `SECRET_KEY`)

No extra Python packages required — the collection uses `urllib.request` only.

## Installation

```bash
# From the repo root:
ansible-galaxy collection install ansible/
# or build then install:
ansible-galaxy collection build ansible/
ansible-galaxy collection install borgui-borg_ui-1.0.0.tar.gz
```

## Authentication

Three methods (first non-null wins):

| Parameter | Description |
|-----------|-------------|
| `token` | Pre-existing JWT Bearer token from `/api/auth/login` |
| `secret_key` | borg-ui `SECRET_KEY` — the collection mints a JWT using HS256 |
| `secret_key_file` | Path to file containing the `SECRET_KEY` |

The `secret_key` approach is recommended for automation — store the key in a secrets manager and pass it via a variable. The `borg_ui_jwt` lookup plugin can mint a token for `ansible.builtin.uri` tasks that call the API directly.

## Plugins

### Modules

| Module | Description |
|--------|-------------|
| `borgui.borg_ui.borg_ui_repository` | Manage backup repositories |
| `borgui.borg_ui.borg_ui_schedule` | Manage scheduled backup jobs |
| `borgui.borg_ui.borg_ui_connection` | Update or delete SSH connections |
| `borgui.borg_ui.borg_ui_notification` | Manage Apprise notification channels |
| `borgui.borg_ui.borg_ui_backup` | Trigger / monitor on-demand backup runs |

### Lookup plugins

| Lookup | Description |
|--------|-------------|
| `borgui.borg_ui.borg_ui_jwt` | Mint a short-lived JWT from the borg-ui `SECRET_KEY` |

The lookup is useful when calling the borg-ui API directly with `ansible.builtin.uri` (e.g. SSH key setup via `POST /api/ssh-keys/quick-setup`):

```yaml
headers:
  Authorization: "Bearer {{ lookup('borgui.borg_ui.borg_ui_jwt', borgui_secret_key) }}"
```

The resource modules (`borg_ui_repository`, `borg_ui_schedule`, etc.) accept `secret_key` directly and mint the JWT internally — you do not need the lookup plugin for those.

## Getting Started

### Back up a fleet of servers

The recommended pattern defines all backup targets in a single YAML file and runs two playbooks — one to deploy SSH keys (once per new server), one to manage repos and schedules (idempotent, run on every change).

**1. Define your servers** in `examples/vars/borg_ui_servers.yml`:

```yaml
borg_ui_servers:
  - name: web-01
    host: 192.168.1.11
    ssh_user: ansible
    ssh_port: 22
    source_dirs:
      - /opt
      - /etc

  - name: db-primary
    host: 192.168.1.61
    ssh_user: root
    ssh_port: 22
    source_dirs:
      - /var/lib/pgsql
      - /etc/postgresql
    exclude:
      - "*.pid"
      - pg_wal

  - name: offsite-nas
    host: nas.example.com
    ssh_user: backup
    ssh_port: 2222
    source_dirs:
      - /mnt/data
```

**2. Deploy SSH keys** (once per new server — needs the server's current SSH password):

```bash
ansible-playbook examples/playbooks/ssh_setup.yml \
  -e '{"borg_ui_ssh_passwords": {
        "web-01":     "server-ssh-password",
        "db-primary": "server-ssh-password",
        "offsite-nas": "server-ssh-password"}}'
```

Already-connected servers are skipped. Safe to re-run when adding new servers.

**3. Create repos and schedule** (idempotent — re-run on every change):

```bash
ansible-playbook examples/playbooks/backup_servers.yml
```

See [`examples/README.md`](examples/README.md) for the full field reference and an alternative inventory-host pattern.

### Back up a single server (quick-start)

For a step-by-step walkthrough of the full setup from scratch, see [`docs/QUICKSTART.md`](docs/QUICKSTART.md).

### One-off tasks

```yaml
# Trigger an on-demand backup and wait for it to finish
- borgui.borg_ui.borg_ui_backup:
    base_url: https://borgui.example.com
    secret_key: "{{ borgui_secret_key }}"
    repository: web-01
    action: start
    wait: true
    wait_timeout: 3600
  register: result

# Add a Slack alert channel for backup failures
- borgui.borg_ui.borg_ui_notification:
    base_url: https://borgui.example.com
    secret_key: "{{ borgui_secret_key }}"
    name: slack-ops
    service_url: "{{ vault_slack_apprise_url }}"
    notify_on_backup_failure: true
    notify_on_check_failure: true
    state: present
```

## Per-server field reference

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `name` | string | required | Display label in borg-ui; repository identity key and schedule reference |
| `host` | string | required | Hostname or IP borg-ui SSHes to |
| `source_dirs` | list | required | Directories to back up on the remote host |
| `ssh_user` | string | `ansible` | SSH login user on the remote host |
| `ssh_port` | int | `22` | SSH port on the remote host |
| `use_sftp_mode` | bool | `false` | `true` for Hetzner Storage Boxes / shell-restricted SSH |
| `exclude` | list | `[]` | Extra glob patterns, appended to the global defaults |
| `encryption` | string | `repokey` | `repokey`, `repokey-blake2`, `keyfile`, `keyfile-blake2`, `authenticated`, `none` |
| `compression` | string | `auto,lz4` | `none`, `lz4`, `zstd`, `zstd,N`, `zlib`, `zlib,N` |
| `mode` | string | `full` | `full` (active backup) or `observe` (monitor only) |
| `repo_path` | string | `/local/<name>` | Override local storage path on the borg-ui host |
| `state` | string | `present` | `absent` to remove the server from borg-ui |

## Running Tests

```bash
cd ansible/
pip install pytest pytest-mock
pytest tests/unit/ -v
```

## Check Mode & Diff Mode

All state modules support `--check` and `--diff`:

```bash
ansible-playbook examples/playbooks/backup_servers.yml --check --diff
```

## Deletion Safety

Repository and connection modules default to `cascade: false` — deletion fails if dependent resources exist, listing what must be removed first. Use `cascade: true` to remove in the correct order automatically:

```
schedule → repository → connection
```

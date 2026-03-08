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

The `secret_key` approach is recommended for Ansible automation — store the key in Vault and pass it via a variable.

## Modules

| Module | Description |
|--------|-------------|
| `borgui.borg_ui.borg_ui_repository` | Manage backup repositories |
| `borgui.borg_ui.borg_ui_schedule` | Manage scheduled backup jobs |
| `borgui.borg_ui.borg_ui_connection` | Manage SSH connections |
| `borgui.borg_ui.borg_ui_notification` | Manage notification channels |
| `borgui.borg_ui.borg_ui_backup` | Trigger / monitor backup runs |

See [docs/MODULES.md](docs/MODULES.md) for per-module reference and [docs/EXAMPLES.md](docs/EXAMPLES.md) for full playbook examples.

## Quick Start

```yaml
- hosts: localhost
  gather_facts: false
  vars:
    borg_ui_url: https://borgui.example.com
    borg_ui_key: "{{ lookup('community.hashi_vault.hashi_vault', 'secret/borgui:secret_key') }}"

  tasks:
    - name: Ensure nightly backup repository exists
      borgui.borg_ui.borg_ui_repository:
        base_url: "{{ borg_ui_url }}"
        secret_key: "{{ borg_ui_key }}"
        name: vault-01
        path: /local/backups/vault-01
        encryption: repokey
        compression: auto,lz4
        source_directories:
          - /opt
        passphrase: "{{ borg_passphrase }}"
        state: present

    - name: Ensure nightly schedule exists
      borgui.borg_ui.borg_ui_schedule:
        base_url: "{{ borg_ui_url }}"
        secret_key: "{{ borg_ui_key }}"
        name: nightly
        cron_expression: "0 2 * * *"
        repositories:
          - vault-01
        prune_keep_daily: 7
        prune_keep_weekly: 4
        state: present
```

## Running Tests

```bash
cd ansible/
pip install pytest pytest-mock
pytest tests/unit/ -v
```

## Check Mode & Diff Mode

All state modules support `--check` and `--diff`:

```bash
ansible-playbook site.yml --check --diff
```

## Deletion Safety

Repository and connection modules default to `cascade: false` — deletion fails if dependent resources exist, listing what must be removed first. Use `cascade: true` to remove in the correct order automatically:

```
schedule → repository → connection
```

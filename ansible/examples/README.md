# borgui.borg_ui — Examples

Two patterns for managing borg-ui backup configuration with Ansible.
Choose the one that fits your workflow.

---

## Pattern A — vars list (recommended)

Define all backup targets in one YAML file. The playbook runs on localhost
and loops over the list — no Ansible inventory involvement required.

```
examples/
  vars/
    borg_ui_servers.yml     ← edit this to add/remove servers
  playbooks/
    ssh_setup.yml           ← run once per new server (deploys SSH key)
    backup_servers.yml      ← run to create/update repos and schedule
```

### Step 1 — define your servers

Edit `vars/borg_ui_servers.yml`:

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

### Step 2 — deploy SSH keys (once per new server)

```bash
ansible-playbook examples/playbooks/ssh_setup.yml \
  -e '{"borg_ui_ssh_passwords": {
        "web-01":     "current-ssh-password",
        "db-primary": "current-ssh-password",
        "offsite-nas": "current-ssh-password"}}'
```

Already-connected servers are skipped automatically. Safe to re-run when
adding new servers to the list.

### Step 3 — create repos and schedule

```bash
ansible-playbook examples/playbooks/backup_servers.yml
```

Re-run whenever you add, change, or remove a server from the list.
Idempotent — unchanged servers produce no API calls after the first run.

---

## Pattern B — Ansible inventory role

Run the `conf_borg_ui_backups` role against your existing Ansible inventory
groups. Each inventory host becomes one borg-ui repository.

```
examples/
  roles/
    conf_borg_ui_backups/
      defaults/main.yml
      tasks/main.yml
```

Example playbook:

```yaml
- name: Ensure borg-ui repositories for web servers
  hosts: web_servers
  gather_facts: false
  become: false

  vars:
    borg_ui_base_url: https://borgui.example.com
    borg_ui_secret_key: "{{ vault_borgui_secret_key }}"
    borg_ui_repo_key: "{{ vault_borgui_repo_passphrase }}"
    borg_ui_source_directories:
      - /opt
      - /etc

  roles:
    - role: borgui.borg_ui.conf_borg_ui_backups
```

Per-host overrides go in `host_vars/<hostname>.yml`:

```yaml
# host_vars/db-primary.yml
borg_ui_ssh_user: root
borg_ui_source_directories:
  - /var/lib/pgsql
  - /etc/postgresql
```

---

## Per-server field reference

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `name` | string | required | Display label in borg-ui; repository identity key |
| `host` | string | required | Hostname or IP borg-ui SSHes to |
| `source_dirs` | list | required | Directories to back up on the remote host |
| `ssh_user` | string | `ansible` | SSH login user on the remote host |
| `ssh_port` | int | `22` | SSH port on the remote host |
| `use_sftp_mode` | bool | `false` | `true` for Hetzner Storage Boxes / shell-restricted SSH |
| `exclude` | list | `[]` | Extra glob patterns (appended to global defaults) |
| `encryption` | string | `repokey` | `repokey`, `repokey-blake2`, `keyfile`, `keyfile-blake2`, `authenticated`, `none` |
| `compression` | string | `auto,lz4` | `none`, `lz4`, `zstd`, `zstd,N`, `zlib`, `zlib,N` |
| `mode` | string | `full` | `full` (active backup) or `observe` (monitor only) |
| `repo_path` | string | `/local/<name>` | Override local storage path on the borg-ui host |
| `state` | string | `present` | `absent` to remove the server from borg-ui |

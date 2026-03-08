# Quick Start — Back Up a Remote Server in 3 Steps

You have a borg-ui instance running. A remote Linux server exists and you
want to back up `/opt` from it on a nightly schedule.

**What the 3 steps do:**

| Step | What happens |
|------|-------------|
| 1 — SSH setup | borg-ui generates an SSH key pair and copies the public key to the remote server using its root/ansible password. After this, borg-ui can SSH in without a password. |
| 2 — Repository | borg-ui creates a Borg repository at `/local/<label>` on its own host and links it to the SSH connection from step 1. |
| 3 — Schedule | borg-ui creates a cron-based schedule that runs the backup and then prunes old archives. |

---

## Complete playbook

```yaml
---
# backup_web01.yml
# Sets up a full nightly backup for web-01 from scratch.
#
# Run:
#   ansible-playbook backup_web01.yml

- name: Set up nightly backup for web-01
  hosts: localhost
  gather_facts: false
  become: false

  vars:
    borgui_url: https://borgui.example.com         # your borg-ui address
    borgui_key: "{{ lookup('community.hashi_vault.hashi_vault',
                            'secret/borgui:secret_key') }}"
    borgui_repo_passphrase: "{{ lookup('community.hashi_vault.hashi_vault',
                                       'secret/borgui:repo_key') }}"

    # The server you want to back up
    target_host: web-01.example.com
    target_ssh_user: ansible
    target_ssh_password: "{{ lookup('community.hashi_vault.hashi_vault',
                                    'secret/web-01:ansible_password') }}"
    target_ssh_port: 22

    # Label for this server in borg-ui (shown in the web UI; identity key)
    # Convention: use the short hostname
    repo_label: web-01

    # Where borg stores archives on the borg-ui host
    repo_path: /local/web-01

    # What to back up on the remote server
    source_dirs:
      - /opt
      - /etc

  tasks:

    # ------------------------------------------------------------------
    # STEP 1: Deploy borg-ui's SSH key to the remote server
    #
    # This calls POST /api/ssh-keys/quick-setup which:
    #   - generates an RSA key pair inside borg-ui
    #   - uses ssh-copy-id to push the public key to the remote server
    #   - records the connection in borg-ui
    #
    # After this runs, borg-ui can SSH to the server without a password.
    # The target_ssh_password is only needed once for this initial setup.
    # ------------------------------------------------------------------

    - name: Step 1 — Deploy SSH key to web-01 and create connection in borg-ui
      ansible.builtin.uri:
        url: "{{ borgui_url }}/api/ssh-keys/quick-setup"
        method: POST
        body_format: json
        body:
          name: "web-01 key"           # label for this SSH key in borg-ui
          host: "{{ target_host }}"
          username: "{{ target_ssh_user }}"
          password: "{{ target_ssh_password }}"
          port: "{{ target_ssh_port }}"
          use_sftp_mode: false          # true if target is Hetzner/NAS appliance
        headers:
          Authorization: "Bearer {{ _borgui_token }}"
        validate_certs: false
        status_code: [200, 201]
      no_log: true     # hides the SSH password from logs
      vars:
        _borgui_token: "{{ lookup('borgui.borg_ui.borg_ui_jwt',
                                   borgui_key) | default('') }}"
      register: _setup_result
      # Note: if the key is already deployed (re-run), this will create a
      # duplicate key entry. Use skip_deployment=true on re-runs if the
      # connection already exists — see Step 1b below.

    # After quick-setup, look up the connection to get its integer ID.
    # We need this ID to link the repository to the SSH connection.
    - name: Find connection ID for {{ target_host }}
      ansible.builtin.uri:
        url: "{{ borgui_url }}/api/ssh-keys/connections"
        method: GET
        headers:
          Authorization: "Bearer {{ _borgui_token }}"
        validate_certs: false
      vars:
        _borgui_token: "{{ lookup('borgui.borg_ui.borg_ui_jwt',
                                   borgui_key) | default('') }}"
      register: _connections
      no_log: true

    - name: Set connection_id fact
      ansible.builtin.set_fact:
        _conn_id: >-
          {{ (_connections.json.connections
              | selectattr('host', 'equalto', target_host)
              | selectattr('username', 'equalto', target_ssh_user)
              | selectattr('port', 'equalto', target_ssh_port)
              | map(attribute='id')
              | list | last) }}

    - name: Assert connection was found
      ansible.builtin.assert:
        that:
          - _conn_id | int > 0
        fail_msg: >-
          Could not find a borg-ui SSH connection for
          {{ target_ssh_user }}@{{ target_host }}:{{ target_ssh_port }}.
          Check the borg-ui web UI under SSH Keys > Connections.

    # ------------------------------------------------------------------
    # STEP 2: Create the backup repository
    #
    # A repository is the Borg storage location on the borg-ui host.
    # source_connection_id links it to the SSH connection from Step 1
    # so borg-ui knows which server to pull data from.
    # ------------------------------------------------------------------

    - name: Step 2 — Create repository for web-01
      borgui.borg_ui.borg_ui_repository:
        base_url: "{{ borgui_url }}"
        secret_key: "{{ borgui_key }}"
        insecure: true

        name: "{{ repo_label }}"         # display label — not the hostname
        path: "{{ repo_path }}"          # where archives live on the borg-ui host
        source_connection_id: "{{ _conn_id | int }}"  # SSH connection from Step 1
        source_directories: "{{ source_dirs }}"       # what to back up on the remote

        encryption: repokey
        compression: "auto,lz4"
        mode: full

        exclude_patterns:
          - "*.log"
          - "*.tmp"
          - "__pycache__"
          - "node_modules"

        passphrase: "{{ borgui_repo_passphrase }}"
        state: present
      register: _repo_result

    - name: Show repository result
      ansible.builtin.debug:
        msg: >-
          Repository '{{ repo_label }}' —
          changed={{ _repo_result.changed }}

    # ------------------------------------------------------------------
    # STEP 3: Create (or update) the nightly schedule
    #
    # repositories: lists which repo labels to include. If you have
    # multiple servers, add their labels here.
    # ------------------------------------------------------------------

    - name: Step 3 — Create nightly backup schedule
      borgui.borg_ui.borg_ui_schedule:
        base_url: "{{ borgui_url }}"
        secret_key: "{{ borgui_key }}"
        insecure: true

        name: nightly-web               # display label for this schedule
        cron_expression: "0 2 * * *"    # every day at 02:00
        description: "Nightly /opt and /etc backup for web servers"
        enabled: true

        repositories:                   # list of repo labels (not hostnames)
          - web-01

        run_prune_after: true
        prune_keep_daily: 7
        prune_keep_weekly: 4
        prune_keep_monthly: 6
        prune_keep_yearly: 1

        state: present
      register: _sched_result

    - name: Done
      ansible.builtin.debug:
        msg: >-
          All done.
          Repository changed={{ _repo_result.changed }},
          Schedule changed={{ _sched_result.changed }}.
          Backup will run tonight at 02:00.
```

---

## What each concept maps to in borg-ui

```
Remote server (web-01.example.com)
    │
    │  SSH (key deployed in Step 1)
    ▼
borg-ui host
    ├── SSH Connection: web-01.example.com / ansible / port 22   ← id=12
    │
    ├── Repository: label="web-01"                                ← references conn id=12
    │   path=/local/web-01   sources=[/opt, /etc]
    │
    └── Schedule: "nightly-web"   cron="0 2 * * *"
        repositories=["web-01"]
```

## Adding a second server

To add `db-01` to the same schedule, run the playbook again (or a loop)
with `repo_label: db-01`, `target_host: db-01.example.com`, then update
the schedule's `repositories` list:

```yaml
repositories:
  - web-01
  - db-01    # newly added
```

The schedule module replaces the full list, so always include all repos
you want to keep.

## Re-running is safe

All three modules are idempotent. If the SSH connection, repository, and
schedule already exist with the right settings, nothing changes.

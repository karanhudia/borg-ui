# Playbook Examples — borgui.borg_ui

## Prerequisites

```yaml
# In your playbook vars or group_vars:
vars:
  borg_ui_url: https://borgui.example.com
  # Recommended: fetch SECRET_KEY from Vault
  borg_ui_key: "{{ lookup('community.hashi_vault.hashi_vault',
                          'secret/borgui:secret_key') }}"
  borg_passphrase: "{{ lookup('community.hashi_vault.hashi_vault',
                              'secret/borgui:repo_key') }}"
```

---

## Create a Repository

```yaml
- name: Ensure vault-01 backup repository exists
  borgui.borg_ui.borg_ui_repository:
    base_url: "{{ borg_ui_url }}"
    secret_key: "{{ borg_ui_key }}"
    name: vault-01
    path: /local/backups/vault-01
    encryption: repokey
    compression: auto,lz4
    source_directories:
      - /opt/vault
    exclude_patterns:
      - "*.log"
      - "*.tmp"
    pre_backup_script: |
      systemctl stop vault
    post_backup_script: |
      systemctl start vault
    passphrase: "{{ borg_passphrase }}"
    state: present
```

---

## Create a Schedule

```yaml
- name: Ensure nightly backup schedule exists
  borgui.borg_ui.borg_ui_schedule:
    base_url: "{{ borg_ui_url }}"
    secret_key: "{{ borg_ui_key }}"
    name: nightly-prod
    cron_expression: "0 2 * * *"
    enabled: true
    description: "Nightly production backup — runs at 02:00"
    repositories:
      - vault-01
      - gitlab-01
    run_prune_after: true
    prune_keep_daily: 7
    prune_keep_weekly: 4
    prune_keep_monthly: 6
    prune_keep_yearly: 2
    state: present
```

---

## Manage Notification Channel

```yaml
- name: Ensure Slack alerts are configured
  borgui.borg_ui.borg_ui_notification:
    base_url: "{{ borg_ui_url }}"
    secret_key: "{{ borg_ui_key }}"
    name: "Slack Ops"
    service_url: "slack://{{ slack_token }}/ops-alerts"
    enabled: true
    notify_on_backup_failure: true
    notify_on_schedule_failure: true
    notify_on_backup_success: false
    monitor_all_repositories: true
    state: present

- name: Remove a notification channel
  borgui.borg_ui.borg_ui_notification:
    base_url: "{{ borg_ui_url }}"
    secret_key: "{{ borg_ui_key }}"
    name: "Old PagerDuty"
    state: absent
```

---

## Manage SSH Connection Attributes

```yaml
# SSH connections are created in the borg-ui UI.
# Use this module to update their attributes idempotently.
- name: Ensure vault-01 SSH connection uses SFTP mode
  borgui.borg_ui.borg_ui_connection:
    base_url: "{{ borg_ui_url }}"
    secret_key: "{{ borg_ui_key }}"
    host: vault-01.example.com
    ssh_username: ansible
    port: 22
    use_sftp_mode: false
    default_path: /opt
    state: present
```

---

## Trigger a Manual Backup

```yaml
- name: Trigger manual backup of vault-01
  borgui.borg_ui.borg_ui_backup:
    base_url: "{{ borg_ui_url }}"
    secret_key: "{{ borg_ui_key }}"
    repository: vault-01
    action: start
    wait: true
    wait_timeout: 3600
  register: backup_result

- name: Show backup result
  ansible.builtin.debug:
    var: backup_result.status
```

---

## Safe Deletion (cascade)

```yaml
# Delete a repository and its dependent schedules:
- name: Remove vault-01 repository and its schedules
  borgui.borg_ui.borg_ui_repository:
    base_url: "{{ borg_ui_url }}"
    secret_key: "{{ borg_ui_key }}"
    name: vault-01
    state: absent
    cascade: true   # removes from schedules first; deletes empty schedules

# Without cascade (safe-fail if dependents exist):
- name: Try to remove vault-01 (fails if schedules reference it)
  borgui.borg_ui.borg_ui_repository:
    base_url: "{{ borg_ui_url }}"
    secret_key: "{{ borg_ui_key }}"
    name: vault-01
    state: absent
    cascade: false   # default — safe-fail
```

---

## Full Bootstrap Playbook

```yaml
---
- name: Bootstrap borg-ui backup resources
  hosts: localhost
  gather_facts: false
  vars:
    borg_ui_url: "https://borgui.example.com"
    borg_ui_key: "{{ lookup('community.hashi_vault.hashi_vault',
                            'secret/borgui:secret_key') }}"
    borg_passphrase: "{{ lookup('community.hashi_vault.hashi_vault',
                                'secret/borgui:repo_key') }}"

  tasks:
    - name: Ensure repositories exist
      borgui.borg_ui.borg_ui_repository:
        base_url: "{{ borg_ui_url }}"
        secret_key: "{{ borg_ui_key }}"
        name: "{{ item.name }}"
        path: "{{ item.path }}"
        encryption: repokey
        compression: auto,lz4
        source_directories: "{{ item.source_directories }}"
        passphrase: "{{ borg_passphrase }}"
        state: present
      loop:
        - name: vault-01
          path: /local/backups/vault-01
          source_directories: [/opt/vault]
        - name: gitlab-01
          path: /local/backups/gitlab-01
          source_directories: [/opt/gitlab]

    - name: Ensure nightly schedule exists
      borgui.borg_ui.borg_ui_schedule:
        base_url: "{{ borg_ui_url }}"
        secret_key: "{{ borg_ui_key }}"
        name: nightly
        cron_expression: "0 2 * * *"
        repositories:
          - vault-01
          - gitlab-01
        run_prune_after: true
        prune_keep_daily: 7
        prune_keep_weekly: 4
        prune_keep_monthly: 6
        prune_keep_yearly: 1
        state: present

    - name: Ensure Slack notifications configured
      borgui.borg_ui.borg_ui_notification:
        base_url: "{{ borg_ui_url }}"
        secret_key: "{{ borg_ui_key }}"
        name: "Slack Ops"
        service_url: "{{ slack_apprise_url }}"
        notify_on_backup_failure: true
        notify_on_schedule_failure: true
        state: present
```

---

## Check Mode and Diff Mode

```bash
# See planned changes without applying them:
ansible-playbook bootstrap.yml --check --diff

# Sample diff output:
# TASK [Ensure repositories exist] ***
# changed: [localhost] => (item=vault-01)
# --- before
# +++ after
# @@ -1,3 +1,3 @@
#  {
# -  "compression": "auto,lz4",
# +  "compression": "zstd,3",
#  }
```

# -*- coding: utf-8 -*-
# Copyright (c) borg-ui contributors
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Ansible module for managing borg-ui notification channels."""

from __future__ import absolute_import, division, print_function
__metaclass__ = type

DOCUMENTATION = r"""
---
module: borg_ui_notification
short_description: Manage borg-ui notification channels
version_added: "1.0.0"
description:
  - Create, update, or delete notification channels in a borg-ui instance via
    the REST API.
  - A B(notification channel) sends alerts via an Apprise-compatible service
    URL (Slack, email, PagerDuty, Telegram, etc.) when backup events occur.
  - Each channel has a unique I(name) (display label shown in the borg-ui UI)
    and a single I(service_url). Multiple channels can co-exist.
  - The I(name) is the B(identity key) — the module uses it to look up whether
    the channel already exists.
  - Supports C(--check) (dry-run) and C(--diff) mode.
options:
  base_url:
    description:
      - Base URL of the borg-ui instance, including scheme and port.
      - "Examples: C(https://nas.example.com:8081), C(http://192.168.0.23:8081)."
    type: str
    required: true
  token:
    description:
      - Pre-existing JWT Bearer token obtained from C(POST /api/auth/login).
      - Mutually exclusive with I(secret_key) and I(secret_key_file).
    type: str
    no_log: true
  secret_key:
    description:
      - borg-ui C(SECRET_KEY) value. The module mints a short-lived JWT —
        no separate login step required.
      - Mutually exclusive with I(token) and I(secret_key_file).
    type: str
    no_log: true
  secret_key_file:
    description:
      - Path to a file containing the borg-ui C(SECRET_KEY).
      - Mutually exclusive with I(token) and I(secret_key).
    type: path
  api_username:
    description:
      - borg-ui username to embed in the minted JWT. Must match an active
        user in borg-ui (default account is C(admin)).
    type: str
    default: admin
  insecure:
    description:
      - Skip TLS certificate verification. Set C(true) for self-signed certs.
    type: bool
    default: false
  state:
    description:
      - C(present) — create the channel if it does not exist, or update it
        if any managed field has changed.
      - C(absent) — delete the channel.
    type: str
    default: present
    choices: [present, absent]
  name:
    description:
      - Display label for the notification channel as shown in the borg-ui
        web UI.
      - This is the B(identity key) used to look up whether the channel
        already exists. Choose a short, descriptive label such as
        C(slack-ops-alerts) or C(email-on-call). Cannot be changed after
        creation.
    type: str
    required: true
  service_url:
    description:
      - Apprise service URL that defines the notification destination and
        credentials.
      - "Slack: C(slack://TokenA/TokenB/TokenC/)"
      - "Email: C(mailto://user:password@smtp.example.com)"
      - "PagerDuty: C(pagerduty://APIToken@IntegrationKey/)"
      - "Telegram: C(tgram://BotToken/ChatID/)"
      - See U(https://github.com/caronc/apprise/wiki) for the full list.
      - Required when I(state=present).
      - Marked C(no_log) because URLs typically contain API tokens or
        passwords.
    type: str
    no_log: true
  enabled:
    description:
      - C(true) — the channel is active and sends notifications.
      - C(false) — the channel is paused; definition kept but no
        notifications sent.
    type: bool
    default: true
  title_prefix:
    description:
      - Optional string prepended to every notification title.
      - Useful to distinguish environments, e.g. C([PROD]) or C([DR]).
    type: str
    default: ""
  include_job_name_in_title:
    description:
      - C(true) — append the backup job name to each notification title for
        easier identification in shared alert channels.
    type: bool
    default: false
  notify_on_backup_start:
    description: Send a notification when a backup job B(starts).
    type: bool
    default: false
  notify_on_backup_success:
    description: Send a notification when a backup job B(completes successfully).
    type: bool
    default: false
  notify_on_backup_failure:
    description: Send a notification when a backup job B(fails).
    type: bool
    default: true
  notify_on_restore_success:
    description: Send a notification when a restore operation B(completes successfully).
    type: bool
    default: false
  notify_on_restore_failure:
    description: Send a notification when a restore operation B(fails).
    type: bool
    default: true
  notify_on_check_success:
    description: Send a notification when a repository integrity check B(passes).
    type: bool
    default: false
  notify_on_check_failure:
    description: Send a notification when a repository integrity check B(fails).
    type: bool
    default: true
  notify_on_schedule_failure:
    description: Send a notification when a scheduled job B(fails to trigger).
    type: bool
    default: true
  monitor_all_repositories:
    description:
      - C(true) — the channel receives events from B(all) repositories.
      - C(false) — the channel only receives events from the repositories
        listed in I(repository_ids).
    type: bool
    default: true
  repository_ids:
    description:
      - List of integer repository IDs to monitor when
        I(monitor_all_repositories=false).
      - Repository IDs are visible in C(GET /api/repositories/) or in the
        return value of M(borgui.borg_ui.borg_ui_repository).
    type: list
    elements: int
author:
  - borg-ui contributors
seealso:
  - module: borgui.borg_ui.borg_ui_repository
"""

EXAMPLES = r"""
# ---------------------------------------------------------------------------
# service_url uses Apprise URL syntax — see https://github.com/caronc/apprise/wiki
# ---------------------------------------------------------------------------

- name: Slack channel — alert on failures only
  borgui.borg_ui.borg_ui_notification:
    base_url: https://borgui.example.com
    secret_key: "{{ lookup('community.hashi_vault.hashi_vault', 'secret/borgui:secret_key') }}"
    name: slack-ops-alerts          # display label; identity key for this channel
    service_url: "{{ vault_slack_apprise_url }}"   # e.g. slack://TokenA/TokenB/TokenC/
    title_prefix: "[PROD]"
    include_job_name_in_title: true
    notify_on_backup_start: false
    notify_on_backup_success: false
    notify_on_backup_failure: true
    notify_on_check_failure: true
    notify_on_schedule_failure: true
    state: present

- name: Email channel — alert on all events with job name in subject
  borgui.borg_ui.borg_ui_notification:
    base_url: https://borgui.example.com
    secret_key: "{{ borg_ui_secret_key }}"
    name: email-on-call
    service_url: "{{ vault_email_apprise_url }}"   # e.g. mailto://user:pass@smtp.example.com
    title_prefix: "[Backup]"
    include_job_name_in_title: true
    notify_on_backup_start: true
    notify_on_backup_success: true
    notify_on_backup_failure: true
    notify_on_check_failure: true
    notify_on_schedule_failure: true
    state: present

- name: Scoped channel — only watch specific repositories
  borgui.borg_ui.borg_ui_notification:
    base_url: https://borgui.example.com
    secret_key: "{{ borg_ui_secret_key }}"
    name: db-critical-alerts
    service_url: "{{ vault_pagerduty_apprise_url }}"
    monitor_all_repositories: false
    repository_ids:
      - 5    # db-primary  (integer ID from GET /api/repositories/)
      - 6    # db-replica
    notify_on_backup_failure: true
    notify_on_check_failure: true
    state: present

- name: Pause notifications during maintenance window
  borgui.borg_ui.borg_ui_notification:
    base_url: https://borgui.example.com
    secret_key: "{{ borg_ui_secret_key }}"
    name: slack-ops-alerts
    service_url: "{{ vault_slack_apprise_url }}"
    enabled: false
    state: present

- name: Remove a notification channel
  borgui.borg_ui.borg_ui_notification:
    base_url: https://borgui.example.com
    secret_key: "{{ borg_ui_secret_key }}"
    name: slack-ops-alerts
    state: absent
"""

RETURN = r"""
changed:
  description: Whether any change was made.
  type: bool
  returned: always
diff:
  description: Dictionary with before/after state for changed fields.
  type: dict
  returned: changed
  contains:
    before:
      description: Previous values of changed fields.
      type: dict
    after:
      description: New values of changed fields.
      type: dict
notification:
  description: Current state of the notification channel after the operation.
  type: dict
  returned: state=present
"""

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.borgui.borg_ui.plugins.module_utils.borg_ui_common import (
    make_client,
    diff_dicts,
    arg_spec_with_auth_and_state,
)
from ansible_collections.borgui.borg_ui.plugins.module_utils.borg_ui_client import (
    BorgUIClientError,
)

# Fields to compare when determining if an update is needed.
# Excludes read-only / server-managed fields.
_IGNORE_FIELDS = frozenset({
    "id",
    "created_at",
    "updated_at",
})

# Fields sent in the API body for create/update.
_MUTABLE_FIELDS = (
    "name",
    "service_url",
    "enabled",
    "title_prefix",
    "include_job_name_in_title",
    "notify_on_backup_start",
    "notify_on_backup_success",
    "notify_on_backup_failure",
    "notify_on_restore_success",
    "notify_on_restore_failure",
    "notify_on_check_success",
    "notify_on_check_failure",
    "notify_on_schedule_failure",
    "monitor_all_repositories",
    "repository_ids",
)


def _build_arg_spec():
    """Return the full argument spec for this module."""
    return arg_spec_with_auth_and_state(
        api_username=dict(type="str", default="admin"),
        name=dict(type="str", required=True),
        service_url=dict(type="str", no_log=True),
        enabled=dict(type="bool", default=True),
        title_prefix=dict(type="str"),
        include_job_name_in_title=dict(type="bool", default=False),
        notify_on_backup_start=dict(type="bool", default=False),
        notify_on_backup_success=dict(type="bool", default=False),
        notify_on_backup_failure=dict(type="bool", default=True),
        notify_on_restore_success=dict(type="bool", default=False),
        notify_on_restore_failure=dict(type="bool", default=True),
        notify_on_check_success=dict(type="bool", default=False),
        notify_on_check_failure=dict(type="bool", default=True),
        notify_on_schedule_failure=dict(type="bool", default=True),
        monitor_all_repositories=dict(type="bool", default=True),
        repository_ids=dict(type="list", elements="int"),
    )


def _make_client_params(params):
    """Map module params to make_client params.

    Translates api_username → username so make_client sees the expected key.
    """
    client_params = dict(params)
    client_params["username"] = client_params.pop("api_username", "admin")
    return client_params


def _find_notification_by_name(client, name):
    """Fetch all notification channels and return the one matching *name*, or None."""
    notifications = client.get("/api/notifications")
    if isinstance(notifications, list):
        items = notifications
    else:
        items = notifications.get("notifications", notifications)
        if isinstance(items, dict):
            items = [items]
    for notif in items:
        if notif.get("name") == name:
            return notif
    return None


def _build_payload(params):
    """Build the API request payload from module params."""
    payload = {}
    for field in _MUTABLE_FIELDS:
        value = params.get(field)
        if value is not None:
            payload[field] = value
        elif field == "title_prefix":
            payload[field] = None
        elif field == "repository_ids":
            payload[field] = None
    return payload


def _needs_update(existing, desired):
    """Compare existing notification state with desired state, ignoring server-managed fields.

    Returns a tuple (bool, dict_before, dict_after) where the dicts contain
    only the fields that differ.
    """
    before = {}
    after = {}
    for key, desired_val in desired.items():
        if key in _IGNORE_FIELDS:
            continue
        existing_val = existing.get(key)
        if existing_val != desired_val:
            before[key] = existing_val
            after[key] = desired_val
    return bool(after), before, after


def _handle_present(module, client):
    """Ensure the notification channel exists with the desired configuration."""
    params = module.params
    name = params["name"]

    if not params.get("service_url"):
        module.fail_json(msg="'service_url' is required when state=present")

    existing = _find_notification_by_name(client, name)
    desired = _build_payload(params)

    if existing is None:
        # Create
        if module.check_mode:
            module.exit_json(
                changed=True,
                diff={"before": {}, "after": desired},
                notification=desired,
            )

        resp = client.post("/api/notifications", data=desired)
        notification = resp if resp else desired
        module.exit_json(
            changed=True,
            diff={"before": {}, "after": desired},
            notification=notification,
        )
    else:
        # Update if needed
        changed, diff_before, diff_after = _needs_update(existing, desired)

        if not changed:
            module.exit_json(changed=False, notification=existing)

        if module.check_mode:
            module.exit_json(
                changed=True,
                diff={"before": diff_before, "after": diff_after},
                notification=existing,
            )

        resp = client.put(
            "/api/notifications/{0}".format(existing["id"]),
            data=desired,
        )
        notification = resp if resp else existing
        module.exit_json(
            changed=True,
            diff={"before": diff_before, "after": diff_after},
            notification=notification,
        )


def _handle_absent(module, client):
    """Ensure the notification channel does not exist."""
    params = module.params
    name = params["name"]

    existing = _find_notification_by_name(client, name)

    if existing is None:
        module.exit_json(changed=False, notification=None)

    if module.check_mode:
        module.exit_json(
            changed=True,
            diff={"before": existing, "after": {}},
            notification=None,
        )

    client.delete("/api/notifications/{0}".format(existing["id"]))
    module.exit_json(
        changed=True,
        diff={"before": existing, "after": {}},
        notification=None,
    )


def main():
    module = AnsibleModule(
        argument_spec=_build_arg_spec(),
        supports_check_mode=True,
        mutually_exclusive=[
            ("token", "secret_key", "secret_key_file"),
        ],
        required_one_of=[
            ("token", "secret_key", "secret_key_file"),
        ],
    )

    try:
        client = make_client(_make_client_params(module.params))
    except (ValueError, BorgUIClientError) as exc:
        module.fail_json(msg=str(exc))

    try:
        if module.params["state"] == "present":
            _handle_present(module, client)
        else:
            _handle_absent(module, client)
    except BorgUIClientError as exc:
        module.fail_json(
            msg="borg-ui API error: {0}".format(str(exc)),
            status_code=getattr(exc, "status_code", None),
            body=getattr(exc, "body", None),
        )


if __name__ == "__main__":
    main()

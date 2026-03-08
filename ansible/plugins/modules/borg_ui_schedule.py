# -*- coding: utf-8 -*-
# Copyright (c) borg-ui contributors
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Ansible module for managing borg-ui scheduled backup jobs."""

from __future__ import absolute_import, division, print_function
__metaclass__ = type

DOCUMENTATION = r"""
---
module: borg_ui_schedule
short_description: Manage borg-ui scheduled backup jobs
version_added: "1.0.0"
description:
  - Create, update, or delete scheduled backup jobs in a borg-ui instance via
    the REST API.
  - A B(schedule) defines when backups run and which repositories are included.
    Multiple repositories can share one schedule.
  - The I(name) is a display label shown in the borg-ui web UI and acts as the
    B(identity key) — the module uses it to look up whether the schedule already
    exists. It is B(not) a cron expression or a hostname.
  - Repository names in I(repositories) must match the I(name) (label) of
    existing C(borg_ui_repository) objects — B(not) hostnames or paths.
  - The module manages the B(full) repositories list. To avoid accidentally
    removing unrelated repositories from a shared schedule, always supply the
    complete desired list.
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
  username:
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
  name:
    description:
      - Display label for the schedule as shown in the borg-ui web UI.
      - This is the B(identity key) used to look up whether the schedule
        already exists. It is B(not) a cron expression, a hostname, or a
        repository reference.
      - Choose a short, descriptive label such as C(nightly-prod) or
        C(weekly-db-archive). Cannot be changed after creation.
    type: str
    required: true
  cron_expression:
    description:
      - Standard five-field cron expression defining when the job runs.
      - "Format: C(minute hour day-of-month month day-of-week)."
      - "C(0 2 * * *)     — every day at 02:00."
      - "C(30 3 * * 0)    — every Sunday at 03:30."
      - "C(0 */6 * * *)   — every 6 hours."
      - Required when I(state=present).
    type: str
  enabled:
    description:
      - C(true) — the schedule runs at the time defined by I(cron_expression).
      - C(false) — the schedule is paused (definition kept, no runs triggered).
    type: bool
    default: true
  description:
    description: Optional free-text description shown in the borg-ui web UI.
    type: str
    default: ""
  repositories:
    description:
      - Complete list of repository B(labels) (the I(name) field of each
        C(borg_ui_repository)) to include in this schedule.
      - These are B(not) hostnames, IPs, or filesystem paths — they are the
        display labels you set when creating each repository.
      - The module resolves each label to its integer repository ID via
        C(GET /api/repositories/). The module fails if any label is not found.
      - This list is B(authoritative) — repositories absent from this list are
        removed from the schedule on the next run.
    type: list
    elements: str
    default: []
  run_prune_after:
    description:
      - Run C(borg prune) on each repository after the backup completes,
        using the C(prune_keep_*) retention policy defined below.
    type: bool
    default: false
  run_compact_after:
    description:
      - Run C(borg compact) on each repository after the backup (and optional
        prune) completes. Reclaims disk space from deleted segments.
    type: bool
    default: false
  prune_keep_hourly:
    description: Number of hourly archives to keep. Set C(0) to disable.
    type: int
    default: 0
  prune_keep_daily:
    description: Number of daily archives to keep.
    type: int
    default: 7
  prune_keep_weekly:
    description: Number of weekly archives to keep.
    type: int
    default: 4
  prune_keep_monthly:
    description: Number of monthly archives to keep.
    type: int
    default: 6
  prune_keep_quarterly:
    description: Number of quarterly archives to keep. Set C(0) to disable.
    type: int
    default: 0
  prune_keep_yearly:
    description: Number of yearly archives to keep.
    type: int
    default: 1
  state:
    description:
      - C(present) — create the schedule if it does not exist, or update it
        if any managed field has changed.
      - C(absent) — delete the schedule entirely.
    type: str
    default: present
    choices: [present, absent]
author:
  - borg-ui contributors
seealso:
  - module: borgui.borg_ui.borg_ui_repository
"""

EXAMPLES = r"""
# ---------------------------------------------------------------------------
# repositories: list the repository *labels* (name field), not hostnames
# ---------------------------------------------------------------------------

- name: Nightly backup schedule — two repositories
  borgui.borg_ui.borg_ui_schedule:
    base_url: https://borgui.example.com
    secret_key: "{{ lookup('community.hashi_vault.hashi_vault', 'secret/borgui:secret_key') }}"
    name: nightly-prod           # display label; identity key for this schedule
    cron_expression: "0 2 * * *" # every day at 02:00
    description: "Nightly /opt backup for production VMs"
    repositories:                # these are repository *labels*, not hostnames
      - web-01
      - db-primary
    prune_keep_daily: 7
    prune_keep_weekly: 4
    prune_keep_monthly: 6
    prune_keep_yearly: 1
    run_prune_after: true
    state: present

- name: Weekly deep archive with compaction
  borgui.borg_ui.borg_ui_schedule:
    base_url: https://borgui.example.com
    secret_key: "{{ borg_ui_secret_key }}"
    name: weekly-archive
    cron_expression: "0 4 * * 0"  # every Sunday at 04:00
    description: "Weekly full archive with compaction"
    repositories:
      - web-01
      - db-primary
      - media-store
    run_prune_after: true
    run_compact_after: true
    prune_keep_daily: 0
    prune_keep_weekly: 8
    prune_keep_monthly: 12
    prune_keep_yearly: 5
    state: present

- name: Pause a schedule without deleting it
  borgui.borg_ui.borg_ui_schedule:
    base_url: https://borgui.example.com
    secret_key: "{{ borg_ui_secret_key }}"
    name: nightly-prod
    cron_expression: "0 2 * * *"
    enabled: false
    state: present

- name: Remove a schedule entirely
  borgui.borg_ui.borg_ui_schedule:
    base_url: https://borgui.example.com
    secret_key: "{{ borg_ui_secret_key }}"
    name: old-schedule
    state: absent
"""

RETURN = r"""
changed:
  description: Whether any change was made.
  returned: always
  type: bool
diff:
  description: Dictionary with before/after showing changed fields.
  returned: when changed
  type: dict
  contains:
    before:
      description: Previous values of changed fields.
      type: dict
    after:
      description: New values of changed fields.
      type: dict
schedule:
  description: The schedule object as returned by the API.
  returned: when state=present
  type: dict
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

# Fields that are compared for idempotency
MANAGED_FIELDS = (
    "cron_expression",
    "enabled",
    "description",
    "repository_ids",
    "run_prune_after",
    "run_compact_after",
    "prune_keep_hourly",
    "prune_keep_daily",
    "prune_keep_weekly",
    "prune_keep_monthly",
    "prune_keep_quarterly",
    "prune_keep_yearly",
)


def _resolve_repository_ids(client, names):
    """Resolve a list of repository names to their IDs.

    :param client: BorgUIClient instance.
    :param names: List of repository name strings.
    :returns: Sorted list of integer repository IDs.
    :raises BorgUIClientError: if a name cannot be resolved.
    """
    if not names:
        return []

    resp = client.get("/api/repositories/")
    repos = resp.get("repositories", [])
    name_to_id = {r["name"]: r["id"] for r in repos}

    ids = []
    missing = []
    for name in names:
        if name in name_to_id:
            ids.append(name_to_id[name])
        else:
            missing.append(name)

    if missing:
        available = sorted(name_to_id.keys())
        raise BorgUIClientError(
            "Repository names not found: {0}. Available: {1}".format(
                ", ".join(missing), ", ".join(available)
            )
        )

    return sorted(ids)


def _find_schedule_by_name(client, name):
    """Find a schedule job by name.

    :returns: The schedule dict if found, else None.
    """
    resp = client.get("/api/schedule/")
    for job in resp.get("jobs", []):
        if job.get("name") == name:
            return job
    return None


def _build_payload(params, repository_ids):
    """Build the API request payload from module params."""
    return {
        "name": params["name"],
        "cron_expression": params["cron_expression"],
        "enabled": params["enabled"],
        "description": params["description"],
        "repository_ids": repository_ids,
        "run_prune_after": params["run_prune_after"],
        "run_compact_after": params["run_compact_after"],
        "prune_keep_hourly": params["prune_keep_hourly"],
        "prune_keep_daily": params["prune_keep_daily"],
        "prune_keep_weekly": params["prune_keep_weekly"],
        "prune_keep_monthly": params["prune_keep_monthly"],
        "prune_keep_quarterly": params["prune_keep_quarterly"],
        "prune_keep_yearly": params["prune_keep_yearly"],
    }


def _normalise(field, value):
    """Normalise a field value for comparison.

    - repository_ids: sort for order-insensitive comparison
    - string fields: treat None and '' as equivalent (empty)
    """
    if field == "repository_ids":
        return sorted(value) if value else []
    if isinstance(value, str) or value is None:
        return value or ""
    return value


def _needs_update(existing, desired):
    """Compare existing schedule against desired state.

    :returns: True if any managed field differs.
    """
    for field in MANAGED_FIELDS:
        if _normalise(field, existing.get(field)) != _normalise(field, desired.get(field)):
            return True
    return False


def _extract_managed(schedule):
    """Extract only managed fields from a schedule dict for diff comparison."""
    return {field: _normalise(field, schedule.get(field)) for field in MANAGED_FIELDS}


def run_module():
    """Main module execution."""
    arg_spec = arg_spec_with_auth_and_state(
        name=dict(type="str", required=True),
        cron_expression=dict(type="str"),
        enabled=dict(type="bool", default=True),
        description=dict(type="str", default=""),
        repositories=dict(type="list", elements="str", default=[]),
        run_prune_after=dict(type="bool", default=False),
        run_compact_after=dict(type="bool", default=False),
        prune_keep_hourly=dict(type="int", default=0),
        prune_keep_daily=dict(type="int", default=7),
        prune_keep_weekly=dict(type="int", default=4),
        prune_keep_monthly=dict(type="int", default=6),
        prune_keep_quarterly=dict(type="int", default=0),
        prune_keep_yearly=dict(type="int", default=1),
    )

    module = AnsibleModule(
        argument_spec=arg_spec,
        supports_check_mode=True,
        mutually_exclusive=[
            ("token", "secret_key", "secret_key_file"),
        ],
        required_one_of=[
            ("token", "secret_key", "secret_key_file"),
        ],
        required_if=[
            ("state", "present", ("cron_expression",)),
        ],
    )

    params = module.params
    state = params["state"]
    name = params["name"]

    try:
        client = make_client(params)
    except (ValueError, BorgUIClientError) as exc:
        module.fail_json(msg=str(exc))
        return

    try:
        existing = _find_schedule_by_name(client, name)

        if state == "absent":
            if existing is None:
                module.exit_json(changed=False)
                return

            diff = diff_dicts(
                _extract_managed(existing),
                {},
            )

            if not module.check_mode:
                client.delete("/api/schedule/{0}".format(existing["id"]))

            module.exit_json(changed=True, diff=diff)
            return

        # state == present
        repository_ids = _resolve_repository_ids(
            client, params["repositories"]
        )
        desired_payload = _build_payload(params, repository_ids)

        if existing is None:
            # Create
            diff = diff_dicts({}, _extract_managed(desired_payload))

            if module.check_mode:
                module.exit_json(
                    changed=True,
                    diff=diff,
                    schedule=desired_payload,
                )
                return

            resp = client.post("/api/schedule/", data=desired_payload)
            module.exit_json(
                changed=True,
                diff=diff,
                schedule=resp.get("job", desired_payload),
            )
            return

        # Existing schedule found — check if update needed
        if not _needs_update(existing, desired_payload):
            module.exit_json(
                changed=False,
                schedule=existing,
            )
            return

        # Update
        diff = diff_dicts(
            _extract_managed(existing),
            _extract_managed(desired_payload),
        )

        if module.check_mode:
            module.exit_json(
                changed=True,
                diff=diff,
                schedule=desired_payload,
            )
            return

        resp = client.put(
            "/api/schedule/{0}".format(existing["id"]),
            data=desired_payload,
        )
        module.exit_json(
            changed=True,
            diff=diff,
            schedule=resp.get("job", desired_payload),
        )

    except BorgUIClientError as exc:
        module.fail_json(msg=str(exc))


def main():
    run_module()


if __name__ == "__main__":
    main()

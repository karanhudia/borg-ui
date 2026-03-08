# -*- coding: utf-8 -*-
# Copyright (c) borg-ui contributors
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Shared argument specs and helpers for borgui.borg_ui Ansible modules."""

from __future__ import absolute_import, division, print_function
__metaclass__ = type

from ansible_collections.borgui.borg_ui.plugins.module_utils.borg_ui_client import (
    BorgUIClient,
    BorgUIClientError,
)

# ---------------------------------------------------------------------------
# Shared argument spec fragments
# ---------------------------------------------------------------------------

AUTH_ARG_SPEC = dict(
    base_url=dict(type="str", required=True),
    token=dict(type="str", no_log=True),
    secret_key=dict(type="str", no_log=True),
    secret_key_file=dict(type="path"),
    username=dict(type="str", default="admin"),
    insecure=dict(type="bool", default=False),
)

COMMON_ARG_SPEC = dict(
    state=dict(type="str", default="present", choices=["present", "absent"]),
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def validate_auth(params):
    """Ensure exactly one of token/secret_key/secret_key_file is provided.

    :raises ValueError: with an actionable message on failure.
    """
    provided = [
        k for k in ("token", "secret_key", "secret_key_file")
        if params.get(k)
    ]
    if not provided:
        raise ValueError(
            "One of token, secret_key, or secret_key_file must be provided"
        )
    if len(provided) > 1:
        raise ValueError(
            "Only one of token, secret_key, or secret_key_file may be provided "
            "(got: {0})".format(", ".join(provided))
        )


def make_client(params):
    """Build and return a configured :class:`BorgUIClient`.

    :param params: Module params dict.
    :returns: :class:`BorgUIClient`
    :raises ValueError: if auth params are invalid.
    """
    validate_auth(params)
    return BorgUIClient(
        base_url=params["base_url"],
        token=params.get("token"),
        secret_key=params.get("secret_key"),
        secret_key_file=params.get("secret_key_file"),
        username=params.get("username", "admin"),
        insecure=params.get("insecure", False),
    )


def diff_dicts(before, after):
    """Return a diff dict ``{before: ..., after: ...}`` for changed keys only.

    Both dicts are expected to contain the same top-level keys.
    """
    changed_before = {}
    changed_after = {}
    for key in set(list(before.keys()) + list(after.keys())):
        bv = before.get(key)
        av = after.get(key)
        if bv != av:
            changed_before[key] = bv
            changed_after[key] = av
    return {"before": changed_before, "after": changed_after}


def arg_spec_with_auth_and_state(**extra):
    """Return a merged arg_spec containing AUTH + COMMON + any extras."""
    spec = {}
    spec.update(AUTH_ARG_SPEC)
    spec.update(COMMON_ARG_SPEC)
    spec.update(extra)
    return spec

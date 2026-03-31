# Account Page & Nav Restructure Design

**Date:** 2026-03-31
**Status:** Approved for future implementation

## Problem

1. The Account settings page contains only a change-password form, making it feel empty and sparse on large screens.
2. "Users" sits under a generic "Management" section in the sidebar. As RBAC and enterprise features land, this grouping won't scale — Management becomes a drawer of unrelated things.

---

## Decisions

### Account Page — Option A: Enrich with Profile Card

Add a read-only profile card above the existing password form. The card shows:
- Avatar (initials-based, coloured by username hash)
- Username
- Role badge (e.g. ADMIN)
- Member since date

No nav changes required. The page grows naturally as new sections are added below.

### Nav Structure — Nav B: Dedicated "Access Control" Section

Move "Users" out of Management into a new "Access Control" section. This section is the long-term home for all identity and permission features. Management becomes operational tools only.

---

## Settings Sidebar — Target Structure

```
PERSONAL
  Account          ← profile card + password (today)
  Appearance
  Notifications
  Preferences

SYSTEM
  System
  MQTT
  Cache
  Logs
  Packages

ACCESS CONTROL     ← new section
  Users            ← moved from Management
  Roles            ← Phase 1 addition
  Audit Log        ← Phase 2 addition (greyed until shipped)
  SSO              ← Phase 2 addition (greyed until shipped)

MANAGEMENT         ← operational tools only
  Mounts
  Scripts
  Export/Import
```

---

## Account Page — Phased Evolution

### Today (current PR)
- Profile card: avatar initials, username, role badge, member since
- Change Password form

### Phase 1 — Role tiers ship
- API Tokens section added below password form
- "Generate Token" action, list of active tokens with revoke controls
- Role badge on profile card reflects the new role system (Admin, Operator, Viewer)

### Phase 2 — Per-resource RBAC ships
- "My Permissions" panel added: table of repositories the user can access with their permission level (Full access / Read + backup / Read only)
- This panel is read-only for non-admins; admins see it too for self-audit

---

## Role Tier Model (Phase 1)

Three built-in roles, no custom roles in Phase 1:

| Role | Description |
|---|---|
| **Admin** | Full access to all features and settings |
| **Operator** | Can run backups, view archives, manage schedules. Cannot manage users, system settings, or repositories configuration |
| **Viewer** | Read-only access: can view repositories, archives, and job history |

Roles are assigned per user. One role per user in Phase 1.

## Per-Resource RBAC Model (Phase 2)

Roles can be scoped to individual repositories. A user can be Operator on `prod-backups` and Viewer on `archive-cold`. The built-in role set stays the same; scope narrows from global to per-resource.

Admin always retains global access regardless of per-resource assignments.

---

## What Does Not Change

- The URL structure for settings pages stays the same
- The Personal section items (Appearance, Notifications, Preferences) are untouched
- System section is untouched
- Management section retains Mounts, Scripts, Export/Import — just loses Users

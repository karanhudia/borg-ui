# Announcement runtime validation

Evidence: production 2.4.5 reports `parseVersion` calling `.trim()` on undefined from `useAnnouncementSurface` on login. The hook trusts `systemInfo.app_version`, while announcement version bounds are already checked as strings before comparison. The public feed checked on 2026-11-01 contains 17 entries with string version bounds and no malformed item identified; no speculative content correction is warranted.

1. Reproduce missing/invalid runtime app versions and malformed announcement items/envelopes with focused tests.
2. Validate untrusted announcement data at the fetch boundary, retain valid neighboring entries, and use existing fallback on malformed envelopes or JSON.
3. Skip version-targeted announcements when the installed version is unavailable or invalid; retain untargeted notice behavior.
4. Guard cached manifest items before the hook reads their IDs. Preserve existing modal UI and release ordering.
5. Run focused utility, service, hook and announcement component tests, then TypeScript/lint checks for the change.

The feed is owned by `docs/announcements.json` and deployed by `updates-worker`; local fallback lives at `frontend/src/data/announcements.json`. Both remain unchanged unless an actual malformed content item is found.

Verification reproduced the exact undefined `.trim()` crash both in the login announcement hook and the sidebar update hook. Both now guard runtime versions and cached entries. The production feed was fetched and checked against the repaired runtime validator: all 17 entries passed, so there is no malformed published item to repair.

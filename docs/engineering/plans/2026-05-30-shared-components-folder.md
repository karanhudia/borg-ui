# Shared Components Folder Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the reusable cross-feature product primitives into `frontend/src/components/shared/` so the file system itself answers "what can I reuse?" — replacing the manually-curated "Shared UI Components" list in `AGENTS.md` with a folder-as-contract rule.

**Architecture:** Pure structural refactor — no behavior changes, no API changes, no new tests except stories/snapshots when story paths change. `shared/` means "shared Borg UI product primitive," not framework-agnostic UI kit. Each task moves one component (or tightly-coupled cluster), updates its imports in every caller, and verifies the full TypeScript + Vitest suite still passes before committing. The existing 1998-test suite plus Storybook snapshots are the safety net.

**Tech Stack:** React + TypeScript + Vite (frontend), MUI, Vitest, Storybook. Path alias `@/*` → `./src/*` exists but is rarely used (16 files); most imports are relative.

---

## Scope decisions

**In scope (move to `components/shared/`):**

Rule of thumb: shared product primitives used across features, or canonical controls
explicitly named in project guidance. These components may know Borg UI concepts
(plans, agents, SSH, schedules), but they should not know a specific page, wizard
step, or business flow.

| Component             | Current location     | Direct callers (non-test/story) |
| --------------------- | -------------------- | ------------------------------- |
| `ResponsiveDialog`    | `components/`        | 27                              |
| `SchedulePicker`      | `components/`        | 4                               |
| `CodeEditor`          | `components/`        | 4                               |
| `CronBuilderDialog`   | `components/`        | 3                               |
| `SshConnectionSelect` | `components/`        | 3                               |
| `RichSelectRow`       | `components/wizard/` | 3                               |
| `ManagedAgentSelect`  | `components/`        | 2                               |
| `PlanGate`            | `components/`        | 2                               |
| `WizardStepIndicator` | `components/wizard/` | 2                               |
| `DestinationSelect`   | `components/`        | 2                               |
| `WizardDialog`        | `components/wizard/` | 1 (via barrel)                  |
| `CronExpressionInput` | `components/`        | 1 (`SchedulePicker`)            |
| `PathSelectorField`   | `components/`        | 1 (`SourceSelectionDialog`)     |

13 components total. `CronExpressionInput`, `PlanGate`, and `PathSelectorField` have low caller counts but qualify as shared product primitives: `CronExpressionInput` travels with the schedule-control family, `PlanGate` is the canonical feature-gating primitive, and `PathSelectorField` is the canonical local/SSH/agent path-picking field. They are not app-agnostic, but they are cross-feature Borg UI primitives.

**Out of scope:**

- Feature components in `components/` (Account*, Archive*, Backup\*, AppHeader, AppSidebar, AuthLayout, etc.) — staying flat.
- Wizard-internal step components in `components/wizard/` (WizardStep\*, RcloneRemoteDialog, BackupFlowPreview, destinations.tsx, repositoryEncryption.ts, RepositoryEncryptionFields, WizardReviewComponents, schedule/) — these have feature knowledge baked in.
- Splitting feature components into per-feature folders (`features/account/`, `features/backups/`, etc.) — a much bigger refactor, separate effort.
- The `frontend/src/pages/` tree — untouched.
- Backward-compat re-exports from old paths (the system prompt says: no shims).
- A generic public UI kit. This folder is for Borg UI product primitives, not framework-neutral design-system packages.

**Folder name:** `shared/` (not `primitives/`, `common/`, `ui/`). Matches the existing `AGENTS.md` section heading "Shared UI Components" and is the term used in this repo's documentation.

**Subfolders inside `shared/`:** None. 13 files flat is easier to scan than the same set split across `dialogs/`, `forms/`, `wizard/`. Revisit if it grows past ~25.

**Stories and tests:** Co-locate with the component (existing pattern is mixed — some stories are siblings, some tests live in `__tests__/`). For the moved files:

- `*.stories.tsx` files move alongside their component (sibling pattern, matches `RcloneRemoteDialog.stories.tsx`).
- `*.test.tsx` files move to `components/shared/__tests__/` (matches `components/__tests__/` pattern).

**Path alias usage:** Continue using relative imports for the moves (matching the existing codebase pattern of 16 `@/` users vs ~150+ relative). No new `@/shared/*` alias.

---

## File Structure

```
frontend/src/components/
├── shared/                         (NEW)
│   ├── ResponsiveDialog.tsx
│   ├── ResponsiveDialog.stories.tsx       (if exists — verify in Task 2)
│   ├── SchedulePicker.tsx
│   ├── SchedulePicker.stories.tsx          (if exists)
│   ├── CronExpressionInput.tsx
│   ├── CronBuilderDialog.tsx
│   ├── CodeEditor.tsx
│   ├── SshConnectionSelect.tsx
│   ├── ManagedAgentSelect.tsx
│   ├── DestinationSelect.tsx
│   ├── RichSelectRow.tsx
│   ├── PlanGate.tsx
│   ├── PathSelectorField.tsx
│   ├── WizardDialog.tsx
│   ├── WizardStepIndicator.tsx
│   └── __tests__/
│       ├── PathSelectorField.test.tsx
│       ├── CronExpressionInput.test.tsx
│       ├── ResponsiveDialog.test.tsx       (if exists)
│       ├── WizardStepIndicator.test.tsx
│       └── ... (others as they exist)
├── (existing feature components stay here)
└── wizard/
    ├── (wizard-step components stay here)
    └── index.ts                    (UPDATE: drop WizardDialog / WizardStepIndicator re-exports)
```

`AGENTS.md` "Shared UI Components" section gets rewritten to point at the folder as the contract, with a short inventory.

---

## Conventions used in every move task

Each move task follows the same shape. Read this once, apply it in every Task 2–9.

1. **Identify callers** — `grep -rln "from .*${Component}'" --include="*.tsx" --include="*.ts" frontend/src` (excluding the file itself).
2. **Move file(s)** — `git mv` so history is preserved. Move the `.tsx` source, sibling `.stories.tsx`, and any `__tests__/${Component}.test.tsx`. Update the test file's relative path back to the moved component if needed.
3. **Update imports in each caller** — relative path changes only. Common patterns:
   - `from '../ResponsiveDialog'` → `from '../shared/ResponsiveDialog'` (caller in `components/`)
   - `from '../../components/ResponsiveDialog'` → `from '../../components/shared/ResponsiveDialog'` (caller in `pages/foo/`)
   - `from '../../../components/ResponsiveDialog'` → `from '../../../components/shared/ResponsiveDialog'` (caller in `pages/foo/bar/`)
   - For `RichSelectRow` (moving out of `components/wizard/`): callers in `components/wizard/` change from `'./RichSelectRow'` to `'../shared/RichSelectRow'`.
4. **Verify** — From `frontend/`:
   ```bash
   npx tsc --noEmit
   npx vitest run
   npx prettier --check src
   ```
   All three must be green. tsc clean, 1998 tests pass, prettier clean.
5. **Commit** — One commit per task. Subject format: `Move <Component> into components/shared/`. Body explains the move briefly and notes how many callers were updated.

**If verification fails:** Stop. Don't proceed to the next task. The most common failure is a missed caller — search again with `grep -rn "${Component}" frontend/src --include="*.tsx" --include="*.ts" | grep -v "components/shared/${Component}"` to find leftovers.

---

## Task 1: Create the shared folder and decide on `__tests__` placement

**Files:**

- Create: `frontend/src/components/shared/` (directory)
- Create: `frontend/src/components/shared/__tests__/` (directory)

- [ ] **Step 1: Create directories**

```bash
mkdir -p frontend/src/components/shared/__tests__
```

- [ ] **Step 2: Add a `.gitkeep` so the empty folder is committable**

```bash
touch frontend/src/components/shared/__tests__/.gitkeep
```

(The `.gitkeep` gets deleted in Task 9 once the first test lands in `shared/__tests__/`. Until then, it keeps the folder visible.)

- [ ] **Step 3: Verify nothing else broke**

```bash
cd frontend && npx tsc --noEmit
```

Expected: exit 0, no output.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/shared/
git commit -m "Create components/shared folder for reusable primitives"
```

---

## Task 2: Move `ResponsiveDialog` (highest blast radius — 27 callers)

**Files:**

- Move: `frontend/src/components/ResponsiveDialog.tsx` → `frontend/src/components/shared/ResponsiveDialog.tsx`
- Move (if exists): `frontend/src/components/ResponsiveDialog.stories.tsx` → `frontend/src/components/shared/ResponsiveDialog.stories.tsx`
- Move (if exists): `frontend/src/components/__tests__/ResponsiveDialog.test.tsx` → `frontend/src/components/shared/__tests__/ResponsiveDialog.test.tsx`
- Update: every caller's import (~27 files)

- [ ] **Step 1: List callers**

```bash
cd frontend && grep -rln "from .*ResponsiveDialog'" src --include="*.tsx" --include="*.ts" | grep -v "ResponsiveDialog\.tsx\|ResponsiveDialog\.stories\.tsx\|ResponsiveDialog\.test\.tsx"
```

Save the list — every entry must be touched.

- [ ] **Step 2: Move the files with `git mv`**

```bash
git mv frontend/src/components/ResponsiveDialog.tsx frontend/src/components/shared/ResponsiveDialog.tsx
# Only run these if the files exist:
[ -f frontend/src/components/ResponsiveDialog.stories.tsx ] && git mv frontend/src/components/ResponsiveDialog.stories.tsx frontend/src/components/shared/ResponsiveDialog.stories.tsx
[ -f frontend/src/components/__tests__/ResponsiveDialog.test.tsx ] && git mv frontend/src/components/__tests__/ResponsiveDialog.test.tsx frontend/src/components/shared/__tests__/ResponsiveDialog.test.tsx
```

- [ ] **Step 3: Fix the test file's relative path to the component if moved**

If `shared/__tests__/ResponsiveDialog.test.tsx` exists, open it and change `from '../ResponsiveDialog'` → `from '../ResponsiveDialog'` (no change — relative path is the same, since both moved together). But double-check: if the test imported anything else from `components/`, those paths now need an extra `..`.

For example:

```ts
// before
import ResponsiveDialog from "../ResponsiveDialog";
import { someHelper } from "../shared-helper"; // ← still in components/, NOT moved
// after
import ResponsiveDialog from "../ResponsiveDialog";
import { someHelper } from "../../shared-helper"; // ← one extra .. now
```

- [ ] **Step 4: Update each caller's import**

For each file in the Step 1 list, update the path:

- Callers in `components/` (sibling): `from './ResponsiveDialog'` → `from './shared/ResponsiveDialog'`
- Callers in `components/wizard/` or other subdirs: `from '../ResponsiveDialog'` → `from '../shared/ResponsiveDialog'`
- Callers in `pages/foo.tsx`: `from '../components/ResponsiveDialog'` → `from '../components/shared/ResponsiveDialog'`
- Callers in `pages/foo/bar.tsx`: `from '../../components/ResponsiveDialog'` → `from '../../components/shared/ResponsiveDialog'`
- Callers in `pages/foo/bar/baz.tsx`: `from '../../../components/ResponsiveDialog'` → `from '../../../components/shared/ResponsiveDialog'`

Recommended bulk-update (run from `frontend/` — review the diff before staging):

```bash
# Sibling form (callers in components/)
grep -rl "from '\./ResponsiveDialog'" src/components --include="*.tsx" --include="*.ts" | xargs sed -i '' "s|from '\./ResponsiveDialog'|from './shared/ResponsiveDialog'|g"

# Parent form (callers in components/<subdir>/)
grep -rl "from '\.\./ResponsiveDialog'" src/components --include="*.tsx" --include="*.ts" | xargs sed -i '' "s|from '\.\./ResponsiveDialog'|from '../shared/ResponsiveDialog'|g"

# Caller depth ../components form (pages/foo.tsx)
grep -rl "from '\.\./components/ResponsiveDialog'" src --include="*.tsx" --include="*.ts" | xargs sed -i '' "s|from '\.\./components/ResponsiveDialog'|from '../components/shared/ResponsiveDialog'|g"

# Caller depth ../../components form
grep -rl "from '\.\./\.\./components/ResponsiveDialog'" src --include="*.tsx" --include="*.ts" | xargs sed -i '' "s|from '\.\./\.\./components/ResponsiveDialog'|from '../../components/shared/ResponsiveDialog'|g"

# Caller depth ../../../components form
grep -rl "from '\.\./\.\./\.\./components/ResponsiveDialog'" src --include="*.tsx" --include="*.ts" | xargs sed -i '' "s|from '\.\./\.\./\.\./components/ResponsiveDialog'|from '../../../components/shared/ResponsiveDialog'|g"
```

If `@/components/ResponsiveDialog` is used anywhere, update that form too:

```bash
grep -rl "from '@/components/ResponsiveDialog'" src --include="*.tsx" --include="*.ts" | xargs sed -i '' "s|from '@/components/ResponsiveDialog'|from '@/components/shared/ResponsiveDialog'|g" 2>/dev/null || true
```

- [ ] **Step 5: Search for leftovers**

```bash
cd frontend && grep -rn "from .*ResponsiveDialog'" src --include="*.tsx" --include="*.ts" | grep -v "components/shared/ResponsiveDialog"
```

Expected: empty. Any remaining match is a missed caller — fix manually.

- [ ] **Step 6: Verify**

```bash
cd frontend && npx tsc --noEmit && npx vitest run && npx prettier --check src
```

Expected: tsc clean, 1998 tests pass, prettier clean.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/shared/ResponsiveDialog* frontend/src/components/shared/__tests__/ResponsiveDialog.test.tsx 2>/dev/null
git add -u  # for moved files git mv tracked, and modified callers
git commit -m "$(cat <<'EOF'
Move ResponsiveDialog into components/shared/

Pure file move + caller import updates. 27 callers across the
components/, components/wizard/, and pages/ trees now import from
components/shared/ResponsiveDialog. No behavior change.
EOF
)"
```

---

## Task 3: Move `RichSelectRow` (moves out of `components/wizard/`)

**Files:**

- Move: `frontend/src/components/wizard/RichSelectRow.tsx` → `frontend/src/components/shared/RichSelectRow.tsx`
- Update callers: `SshConnectionSelect.tsx`, `ManagedAgentSelect.tsx`, `WizardStepLocation.tsx`, plus any test/story.

This one's special because the source file currently lives in `components/wizard/`, so caller paths change differently:

- From `components/`: `from './wizard/RichSelectRow'` → `from './shared/RichSelectRow'`
- From `components/wizard/`: `from './RichSelectRow'` → `from '../shared/RichSelectRow'`
- From `pages/...`: `from '<depth>/components/wizard/RichSelectRow'` → `from '<depth>/components/shared/RichSelectRow'`

- [ ] **Step 1: List callers**

```bash
cd frontend && grep -rln "from .*RichSelectRow'" src --include="*.tsx" --include="*.ts" | grep -v "RichSelectRow\.tsx"
```

- [ ] **Step 2: Move the file**

```bash
git mv frontend/src/components/wizard/RichSelectRow.tsx frontend/src/components/shared/RichSelectRow.tsx
```

- [ ] **Step 3: Update each caller**

For each caller in the Step 1 list, fix the relative path:

- `frontend/src/components/SshConnectionSelect.tsx`: `from './wizard/RichSelectRow'` → `from './shared/RichSelectRow'`
- `frontend/src/components/ManagedAgentSelect.tsx`: `from './wizard/RichSelectRow'` → `from './shared/RichSelectRow'`
- `frontend/src/components/wizard/WizardStepLocation.tsx`: `from './RichSelectRow'` → `from '../shared/RichSelectRow'`
- Any other caller surfaced by Step 1.

(Since callers are few, do them by hand — sed is overkill.)

- [ ] **Step 4: Search for leftovers**

```bash
cd frontend && grep -rn "from .*RichSelectRow'" src --include="*.tsx" --include="*.ts" | grep -v "components/shared/RichSelectRow"
```

Expected: empty.

- [ ] **Step 5: Verify**

```bash
cd frontend && npx tsc --noEmit && npx vitest run && npx prettier --check src
```

- [ ] **Step 6: Commit**

```bash
git add -A frontend/src/components/shared/RichSelectRow.tsx
git add -u
git commit -m "Move RichSelectRow into components/shared/

Was in components/wizard/ but is a pure primitive used by both
SshConnectionSelect and ManagedAgentSelect (which sit in
components/). Move it next to its consumers in the shared folder."
```

---

## Task 4: Move `SshConnectionSelect`, `ManagedAgentSelect`, and `DestinationSelect` together

These three are siblings created in the recent extraction work and share the same 56px-outlined-Select + `RichSelectRow` pattern. Move them in one task.

**Files:**

- Move: `frontend/src/components/SshConnectionSelect.tsx` → `frontend/src/components/shared/SshConnectionSelect.tsx`
- Move: `frontend/src/components/ManagedAgentSelect.tsx` → `frontend/src/components/shared/ManagedAgentSelect.tsx`
- Move: `frontend/src/components/DestinationSelect.tsx` → `frontend/src/components/shared/DestinationSelect.tsx`
- Move: `frontend/src/components/DestinationSelect.stories.tsx` → `frontend/src/components/shared/DestinationSelect.stories.tsx`
- Update callers.

- [ ] **Step 1: List callers**

```bash
cd frontend && grep -rln "from .*SshConnectionSelect'" src --include="*.tsx" --include="*.ts" | grep -v "SshConnectionSelect\.tsx"
cd frontend && grep -rln "from .*ManagedAgentSelect'" src --include="*.tsx" --include="*.ts" | grep -v "ManagedAgentSelect\.tsx"
cd frontend && grep -rln "from .*DestinationSelect'" src --include="*.tsx" --include="*.ts" | grep -v "DestinationSelect\.tsx"
```

Expected callers:

- `SshConnectionSelect`: `components/wizard/WizardStepLocation.tsx`, `components/wizard/WizardStepDataSource.tsx`, `pages/backup-plans/wizard-step/SourceSelectionDialog.tsx`
- `ManagedAgentSelect`: `components/wizard/WizardStepLocation.tsx`, `pages/backup-plans/wizard-step/SourceSelectionDialog.tsx`
- `DestinationSelect`: `components/wizard/WizardStepLocation.tsx`, `pages/backup-plans/wizard-step/SourceSelectionDialog.tsx`, `components/DestinationSelect.stories.tsx`

- [ ] **Step 2: Move all three files**

```bash
git mv frontend/src/components/SshConnectionSelect.tsx frontend/src/components/shared/SshConnectionSelect.tsx
git mv frontend/src/components/ManagedAgentSelect.tsx frontend/src/components/shared/ManagedAgentSelect.tsx
git mv frontend/src/components/DestinationSelect.tsx frontend/src/components/shared/DestinationSelect.tsx
git mv frontend/src/components/DestinationSelect.stories.tsx frontend/src/components/shared/DestinationSelect.stories.tsx
```

- [ ] **Step 3: Update each caller**

Internal import inside `SshConnectionSelect.tsx`, `ManagedAgentSelect.tsx`, and `DestinationSelect.tsx`: their `from './wizard/RichSelectRow'` was rewritten to `from './shared/RichSelectRow'` in Task 3. Now that they themselves move into `shared/`, that path becomes `from './RichSelectRow'`:

```ts
// SshConnectionSelect.tsx, ManagedAgentSelect.tsx, DestinationSelect.tsx
// before (after Task 3):
import RichSelectRow from "./shared/RichSelectRow";
// after (Task 4):
import RichSelectRow from "./RichSelectRow";
```

Caller updates:

- `components/wizard/WizardStepLocation.tsx`: `from '../SshConnectionSelect'` → `from '../shared/SshConnectionSelect'`, `from '../ManagedAgentSelect'` → `from '../shared/ManagedAgentSelect'`, and `from '../DestinationSelect'` → `from '../shared/DestinationSelect'`
- `components/wizard/WizardStepDataSource.tsx`: `from '../SshConnectionSelect'` → `from '../shared/SshConnectionSelect'`
- `pages/backup-plans/wizard-step/SourceSelectionDialog.tsx`: `from '../../../components/SshConnectionSelect'` → `from '../../../components/shared/SshConnectionSelect'`, similarly for `ManagedAgentSelect`, and `from '../../../components/DestinationSelect'` → `from '../../../components/shared/DestinationSelect'`
- `components/shared/DestinationSelect.stories.tsx`: after moving, its `from './DestinationSelect'` import still resolves correctly.

- [ ] **Step 4: Search for leftovers**

```bash
cd frontend && grep -rn "from .*SshConnectionSelect'\|from .*ManagedAgentSelect'\|from .*DestinationSelect'" src --include="*.tsx" --include="*.ts" | grep -v "components/shared/"
```

Expected: empty.

- [ ] **Step 5: Verify**

```bash
cd frontend && npx tsc --noEmit && npx vitest run && npx prettier --check src
```

- [ ] **Step 6: Commit**

```bash
git add -u
git commit -m "Move SshConnectionSelect, ManagedAgentSelect, and DestinationSelect into components/shared/

All three were extracted recently as reusable primitives sharing the
same 56px outlined Select + RichSelectRow pattern. Co-locate them
with RichSelectRow in components/shared/ and move the DestinationSelect
story beside its component."
```

---

## Task 5: Move the Schedule family (`SchedulePicker`, `CronExpressionInput`, `CronBuilderDialog`)

These three are tightly coupled — `SchedulePicker` imports `CronExpressionInput` and uses `CronBuilderDialog`. Move them in one task to avoid intermediate broken states.

**Files:**

- Move: `frontend/src/components/SchedulePicker.tsx` → `frontend/src/components/shared/SchedulePicker.tsx`
- Move: `frontend/src/components/CronExpressionInput.tsx` → `frontend/src/components/shared/CronExpressionInput.tsx`
- Move: `frontend/src/components/CronBuilderDialog.tsx` → `frontend/src/components/shared/CronBuilderDialog.tsx`
- Move (if they exist): each one's `.stories.tsx` sibling and `__tests__/<Name>.test.tsx`.
- Update callers.

- [ ] **Step 1: List callers and inventory test/story files**

```bash
cd frontend && for f in SchedulePicker CronExpressionInput CronBuilderDialog; do
  echo "=== $f ==="
  echo "callers:"
  grep -rln "from .*$f'" src --include="*.tsx" --include="*.ts" | grep -v "$f\.tsx"
  echo "story file:"
  ls src/components/$f.stories.tsx 2>/dev/null
  echo "test file:"
  ls src/components/__tests__/$f.test.tsx 2>/dev/null
done
```

- [ ] **Step 2: Move all files**

```bash
git mv frontend/src/components/SchedulePicker.tsx frontend/src/components/shared/SchedulePicker.tsx
git mv frontend/src/components/CronExpressionInput.tsx frontend/src/components/shared/CronExpressionInput.tsx
git mv frontend/src/components/CronBuilderDialog.tsx frontend/src/components/shared/CronBuilderDialog.tsx

# Move stories if present
for f in SchedulePicker CronExpressionInput CronBuilderDialog; do
  [ -f frontend/src/components/$f.stories.tsx ] && git mv frontend/src/components/$f.stories.tsx frontend/src/components/shared/$f.stories.tsx
done

# Move tests if present
for f in SchedulePicker CronExpressionInput CronBuilderDialog; do
  [ -f frontend/src/components/__tests__/$f.test.tsx ] && git mv frontend/src/components/__tests__/$f.test.tsx frontend/src/components/shared/__tests__/$f.test.tsx
done
```

- [ ] **Step 3: Update internal sibling imports (now in same folder)**

Inside the moved files, sibling imports stay the same (`./CronExpressionInput` still resolves correctly because both moved together). But check:

```bash
cd frontend && grep -n "from '\./CronExpressionInput'\|from '\./CronBuilderDialog'\|from '\./SchedulePicker'" src/components/shared/SchedulePicker.tsx src/components/shared/CronExpressionInput.tsx src/components/shared/CronBuilderDialog.tsx 2>/dev/null
```

These should still work — no change needed.

For test files in `shared/__tests__/`, the path back to the component changes from `'../<Name>'` (when test was in `components/__tests__/`) to `'../<Name>'` (still works — same depth). Verify:

```bash
cd frontend && grep -n "from '\.\." src/components/shared/__tests__/*.test.tsx 2>/dev/null
```

If a test imports `from '../OtherComponentNotMoved'`, that path now needs to be `from '../../OtherComponentNotMoved'`.

- [ ] **Step 4: Update each external caller**

Use the same depth-based rewrite from Task 2's Step 4. The components-level callers are the most common; pages-level callers will use `../components/shared/<Name>`.

- [ ] **Step 5: Search for leftovers**

```bash
cd frontend && for f in SchedulePicker CronExpressionInput CronBuilderDialog; do
  grep -rn "from .*$f'" src --include="*.tsx" --include="*.ts" | grep -v "components/shared/"
done
```

Expected: empty for each.

- [ ] **Step 6: Verify**

```bash
cd frontend && npx tsc --noEmit && npx vitest run && npx prettier --check src
```

- [ ] **Step 7: Commit**

```bash
git add -u
git commit -m "Move schedule controls into components/shared/

SchedulePicker, CronExpressionInput, and CronBuilderDialog form a
tightly-coupled trio used across the Backup Plan wizard, schedule
wizard, and (per AGENTS.md) any schedule-related UI. They're pure
primitives — move them together."
```

---

## Task 6: Move `CodeEditor`

**Files:**

- Move: `frontend/src/components/CodeEditor.tsx` → `frontend/src/components/shared/CodeEditor.tsx`
- Move sibling story/test if present.
- Update 4 callers.

- [ ] **Step 1: List callers**

```bash
cd frontend && grep -rln "from .*CodeEditor'" src --include="*.tsx" --include="*.ts" | grep -v "CodeEditor\.tsx"
```

- [ ] **Step 2: Move file (and story/test if present)**

```bash
git mv frontend/src/components/CodeEditor.tsx frontend/src/components/shared/CodeEditor.tsx
[ -f frontend/src/components/CodeEditor.stories.tsx ] && git mv frontend/src/components/CodeEditor.stories.tsx frontend/src/components/shared/CodeEditor.stories.tsx
[ -f frontend/src/components/__tests__/CodeEditor.test.tsx ] && git mv frontend/src/components/__tests__/CodeEditor.test.tsx frontend/src/components/shared/__tests__/CodeEditor.test.tsx
```

- [ ] **Step 3: Update each caller** (by hand — only 4)

- [ ] **Step 4: Search for leftovers**

```bash
cd frontend && grep -rn "from .*CodeEditor'" src --include="*.tsx" --include="*.ts" | grep -v "components/shared/CodeEditor"
```

- [ ] **Step 5: Verify**

```bash
cd frontend && npx tsc --noEmit && npx vitest run && npx prettier --check src
```

- [ ] **Step 6: Commit**

```bash
git add -u
git commit -m "Move CodeEditor into components/shared/"
```

---

## Task 7: Move `PlanGate` and `PathSelectorField`

Two small shared product primitives. `PlanGate` is not app-agnostic: it depends
on Borg UI plan/feature concepts and `UpgradePrompt`, but it is the canonical
feature-gating wrapper used across product surfaces. `PathSelectorField` depends
on `FileExplorerDialog`, but it is the canonical path field for local, SSH, and
agent-aware flows. One commit each isn't worth it; bundle them.

**Files:**

- Move: `frontend/src/components/PlanGate.tsx` → `frontend/src/components/shared/PlanGate.tsx`
- Move: `frontend/src/components/PathSelectorField.tsx` → `frontend/src/components/shared/PathSelectorField.tsx`
- Move siblings (`PlanGate.test.tsx` and `PathSelectorField.test.tsx` are known to exist at `components/__tests__/`).
- Update callers (2 + 1).

- [ ] **Step 1: List callers**

```bash
cd frontend && for f in PlanGate PathSelectorField; do
  echo "=== $f ==="
  grep -rln "from .*$f'" src --include="*.tsx" --include="*.ts" | grep -v "$f\.tsx"
done
```

- [ ] **Step 2: Move both files plus the known PathSelectorField test**

```bash
git mv frontend/src/components/PlanGate.tsx frontend/src/components/shared/PlanGate.tsx
git mv frontend/src/components/PathSelectorField.tsx frontend/src/components/shared/PathSelectorField.tsx
git mv frontend/src/components/__tests__/PlanGate.test.tsx frontend/src/components/shared/__tests__/PlanGate.test.tsx
git mv frontend/src/components/__tests__/PathSelectorField.test.tsx frontend/src/components/shared/__tests__/PathSelectorField.test.tsx
```

- [ ] **Step 3: Fix the moved test files' imports**

The tests were at `components/__tests__/<Name>.test.tsx`. They now live at `components/shared/__tests__/<Name>.test.tsx`. The relative path to each component remains:

- Before: `from '../<Name>'` (one up from `__tests__/` → `components/`)
- After: `from '../<Name>'` (one up from `shared/__tests__/` → `shared/`)

That path still resolves correctly to the moved file. But any OTHER import in the test files that pointed to something in `components/` (e.g., `from '../SomeOtherComponent'`) now needs an extra `..`. Audit:

```bash
cd frontend && grep -n "^import\|^const.*require" src/components/shared/__tests__/PlanGate.test.tsx src/components/shared/__tests__/PathSelectorField.test.tsx
```

Fix any path that pointed into `components/` but to something NOT in `shared/`.

- [ ] **Step 4: Update each caller** (by hand — 3 total)

- [ ] **Step 5: Search for leftovers**

```bash
cd frontend && grep -rn "from .*PlanGate'\|from .*PathSelectorField'" src --include="*.tsx" --include="*.ts" | grep -v "components/shared/"
```

- [ ] **Step 6: Verify**

```bash
cd frontend && npx tsc --noEmit && npx vitest run && npx prettier --check src
```

- [ ] **Step 7: Commit**

```bash
git add -u
git commit -m "Move PlanGate and PathSelectorField into components/shared/"
```

---

## Task 8: Move `WizardDialog` and `WizardStepIndicator`

These two come out of `components/wizard/`. `WizardDialog` composes `ResponsiveDialog` + `WizardStepIndicator`, so they ship together. The `components/wizard/index.ts` barrel currently re-exports both — that barrel entry must be removed and consumers updated to import from the new path.

**Files:**

- Move: `frontend/src/components/wizard/WizardDialog.tsx` → `frontend/src/components/shared/WizardDialog.tsx`
- Move: `frontend/src/components/wizard/WizardStepIndicator.tsx` → `frontend/src/components/shared/WizardStepIndicator.tsx`
- Move (if exists): `frontend/src/components/wizard/__tests__/WizardStepIndicator.test.tsx` → `frontend/src/components/shared/__tests__/WizardStepIndicator.test.tsx`
- Modify: `frontend/src/components/wizard/index.ts` (drop `WizardDialog` and `WizardStepIndicator` re-exports)
- Update consumers of the barrel that pull these two names.

- [ ] **Step 1: List barrel consumers that import `WizardDialog` or `WizardStepIndicator`**

```bash
cd frontend && grep -rln "from .*components/wizard'" src --include="*.tsx" --include="*.ts"
# For each result, check what they import:
grep -rn "import.*from.*components/wizard'" src --include="*.tsx" --include="*.ts"
```

Current consumers of `WizardDialog` through the barrel: `components/RepositoryWizard.tsx`, `components/ScheduleWizard.tsx`, `components/RestoreWizard.tsx`, `pages/BackupPlans.tsx`, and `pages/managed-agents/AddAgentDialog.tsx`. Other barrel consumers (`pages/backup-plans/state.ts`, `pages/backup-plans/wizard-step/RepositoriesStep.tsx`) should stay on the wizard barrel unless they import `WizardDialog`, `WizardStepIndicator`, or `WizardStep`.

Note which import `WizardDialog` or `WizardStepIndicator` — those need their import lines split, since the rest of the wizard barrel (WizardStepLocation, WizardStepReview, etc.) stays put.

- [ ] **Step 2: Move both files**

```bash
git mv frontend/src/components/wizard/WizardDialog.tsx frontend/src/components/shared/WizardDialog.tsx
git mv frontend/src/components/wizard/WizardStepIndicator.tsx frontend/src/components/shared/WizardStepIndicator.tsx
[ -f frontend/src/components/wizard/__tests__/WizardStepIndicator.test.tsx ] && git mv frontend/src/components/wizard/__tests__/WizardStepIndicator.test.tsx frontend/src/components/shared/__tests__/WizardStepIndicator.test.tsx
```

- [ ] **Step 3: Fix internal imports inside the moved files**

`WizardDialog.tsx` used to be at `components/wizard/WizardDialog.tsx` and imported `WizardStepIndicator` as `from './WizardStepIndicator'` — that still works (both moved together).

It also imports `ResponsiveDialog`. Before this whole plan, that was `from '../ResponsiveDialog'`. After Task 2, it became `from '../shared/ResponsiveDialog'`. Now that `WizardDialog.tsx` itself lives in `shared/`, the path becomes `from './ResponsiveDialog'`. Update:

```ts
// frontend/src/components/shared/WizardDialog.tsx
// before (after Task 2 changes):
import ResponsiveDialog from "../shared/ResponsiveDialog";
// after (Task 8):
import ResponsiveDialog from "./ResponsiveDialog";
```

If the moved test file (`WizardStepIndicator.test.tsx`) imports anything besides the component, audit those paths for `..` adjustments.

- [ ] **Step 4: Update `components/wizard/index.ts`**

Open `frontend/src/components/wizard/index.ts` and remove these two lines:

```ts
export { default as WizardStepIndicator } from "./WizardStepIndicator";
export { default as WizardDialog } from "./WizardDialog";
```

Also remove the corresponding type re-export if any:

```ts
export type { WizardStep } from "./WizardDialog";
```

(Check the file first — the survey showed `export type { WizardStep } from './WizardDialog'` exists. That type re-export also moves out.)

- [ ] **Step 5: Update barrel consumers**

For each consumer file that imported `WizardDialog`, `WizardStepIndicator`, or the `WizardStep` type from `'../components/wizard'`: split the import into two lines.

Example transformation (`pages/managed-agents/AddAgentDialog.tsx`):

```ts
// before
import {
  WizardDialog,
  WizardStepLocation,
  type WizardStep,
} from "../../components/wizard";

// after
import {
  WizardDialog,
  type WizardStep,
} from "../../components/shared/WizardDialog";
import { WizardStepLocation } from "../../components/wizard";
```

(Importing the type directly from `WizardDialog` keeps the surface small. If multiple shared things become barrel candidates later we can add `components/shared/index.ts`; not yet — see Open Questions.)

Also split imports in:

- `frontend/src/components/RepositoryWizard.tsx`
- `frontend/src/components/ScheduleWizard.tsx`
- `frontend/src/components/RestoreWizard.tsx`
- `frontend/src/pages/BackupPlans.tsx`

- [ ] **Step 6: Search for leftovers**

```bash
cd frontend && grep -rn "from .*WizardDialog'\|from .*WizardStepIndicator'" src --include="*.tsx" --include="*.ts" | grep -v "components/shared/"
```

Expected: empty.

- [ ] **Step 7: Verify**

```bash
cd frontend && npx tsc --noEmit && npx vitest run && npx prettier --check src
```

- [ ] **Step 8: Commit**

```bash
git add -u
git commit -m "$(cat <<'EOF'
Move WizardDialog and WizardStepIndicator into components/shared/

WizardDialog composes ResponsiveDialog + WizardStepIndicator and is
documented in AGENTS.md as the canonical multi-step wizard primitive.
Move both out of components/wizard/ (which now exclusively holds
wizard step implementations) into components/shared/.

The components/wizard/index.ts barrel drops the two re-exports;
consumers (BackupPlans, AddAgentDialog, RepositoriesStep, state) now
import WizardDialog directly from components/shared/WizardDialog.
EOF
)"
```

---

## Task 9: Drop the `.gitkeep` and update `AGENTS.md`

By the end of Task 8, `components/shared/__tests__/` has real test files in it, so `.gitkeep` can go. And `AGENTS.md`'s "Shared UI Components" section needs to become "folder-as-contract" rather than a manually-curated list.

**Files:**

- Delete: `frontend/src/components/shared/__tests__/.gitkeep`
- Modify: `AGENTS.md` (rewrite the Shared UI Components section)

- [ ] **Step 1: Verify the `__tests__` folder has real content**

```bash
cd frontend && ls src/components/shared/__tests__/
```

Expected: at least one `*.test.tsx` file. If empty, leave `.gitkeep` and skip its deletion.

- [ ] **Step 2: Delete `.gitkeep` if safe**

```bash
[ -n "$(ls frontend/src/components/shared/__tests__/*.test.tsx 2>/dev/null)" ] && git rm frontend/src/components/shared/__tests__/.gitkeep
```

- [ ] **Step 3: Rewrite the Shared UI Components section in `AGENTS.md`**

Replace the entire "## Shared UI Components" section (including its bullet list) with:

```markdown
## Shared UI Components

Anything in `frontend/src/components/shared/` is a reusable Borg UI product primitive. Reach for what's there before introducing a new pattern — adding a raw MUI `Dialog` or hand-rolling a step indicator is almost always wrong.

The folder is the contract: if a component belongs there, it lives there. The rule of thumb is "used in ≥2 features or named as a canonical control, and contains no page-specific, wizard-step-specific, or flow-specific knowledge."

Current inventory (run `ls frontend/src/components/shared/` for the live list):

- `ResponsiveDialog` — Centered dialog on desktop, bottom drawer on mobile. Use instead of raw `@mui/material` `Dialog`. Place sticky actions in the `footer` prop.
- `WizardDialog` + `WizardStepIndicator` — Multi-step wizard shell composing `ResponsiveDialog`. Pass `steps` (`{ key, label, icon }`), `currentStep`, optional `onStepClick`. Step `key` picks a color from the indicator palette (`location`, `source`, `security`, `config`, `review`, `basic`, `schedule`, `scripts`, `maintenance`).
- `SchedulePicker` + `CronExpressionInput` + `CronBuilderDialog` — Canonical schedule controls; use these (plus the timezone selector rendered by `SchedulePicker`) for any schedule UI instead of ad-hoc cron or timezone fields.
- `SshConnectionSelect` — Picker for SSH connections. Required props: `value`, `onChange(id)`, `connections`, `label`, `emptyMessage`. Cloud icon, `user@host` primary, port/mount secondary, green dot when connected.
- `ManagedAgentSelect` — Picker for enrolled managed agents. Same shape as `SshConnectionSelect`. Laptop icon, hostname-or-name primary, hostname/status secondary, green dot when `online`.
- `DestinationSelect` — Picker for a small set of static rich-row options (icon + label + description). Required props: `value`, `onChange(key)`, `destinations`, `label`. Each destination is `{ key, icon, label, description, disabled? }`. Same 56px outlined Select + `RichSelectRow` shape as the other two.
- `RichSelectRow` — Icon + 2-line text + optional indicator row used inside any rich MUI `Select`. Use this instead of hand-rolled `Box`/`Stack` compositions for select rows.
- `PathSelectorField` — Path picker with local/SSH/agent connection awareness.
- `CodeEditor` — Syntax-highlighted code editor wrapper.
- `PlanGate` — Borg UI plan-feature gating wrapper for premium UI.

When you add a new component that meets the bar, drop it in this folder and add a one-line entry above.
```

(Update the wording if any of the components above were renamed or have different prop names in the actual codebase — verify by opening each `.tsx`. The schedule mention in the "## UI Workflow" section that lists `SchedulePicker`/`CronExpressionInput`/`CronBuilderDialog` should be updated to drop the explicit list and just say "the shared schedule controls in `components/shared/`".)

- [ ] **Step 4: Search for `components/wizard/` references in `AGENTS.md` that should now point to `components/shared/`**

```bash
grep -n "components/wizard/WizardDialog\|components/wizard/WizardStepIndicator" AGENTS.md
```

Update any hit to use `components/shared/`.

- [ ] **Step 5: Verify**

```bash
cd frontend && npx tsc --noEmit && npx vitest run && npx prettier --check src
cd .. && npx prettier --check AGENTS.md
```

- [ ] **Step 6: Commit**

```bash
git add AGENTS.md frontend/src/components/shared/__tests__/.gitkeep 2>/dev/null
git add -u
git commit -m "$(cat <<'EOF'
Document components/shared/ as the shared primitive contract

Rewrite the Shared UI Components section in AGENTS.md to point at
the folder as the source of truth, with a short inventory. Folder
existence + 'used in ≥2 features or canonical, no flow knowledge' is now the
rule for what belongs there — no more manually-curated bullet list
that goes stale.
EOF
)"
```

---

## Task 10: Final verification

After all moves and the AGENTS.md update, do a clean-room verification pass to confirm nothing slipped.

- [ ] **Step 1: Confirm the inventory matches the plan**

```bash
ls frontend/src/components/shared/
```

Expected files (in some order):

- `CodeEditor.tsx`
- `CronBuilderDialog.tsx`
- `CronExpressionInput.tsx`
- `DestinationSelect.tsx`
- `ManagedAgentSelect.tsx`
- `PathSelectorField.tsx`
- `PlanGate.tsx`
- `ResponsiveDialog.tsx`
- `RichSelectRow.tsx`
- `SchedulePicker.tsx`
- `SshConnectionSelect.tsx`
- `WizardDialog.tsx`
- `WizardStepIndicator.tsx`
- (`*.stories.tsx` siblings as they existed before)
- `__tests__/` with the moved test files

- [ ] **Step 2: Confirm no caller still points at an old path**

```bash
cd frontend && for f in ResponsiveDialog SchedulePicker CronExpressionInput CronBuilderDialog CodeEditor SshConnectionSelect RichSelectRow ManagedAgentSelect DestinationSelect PlanGate WizardStepIndicator WizardDialog PathSelectorField; do
  hits=$(grep -rn "from .*$f'" src --include="*.tsx" --include="*.ts" | grep -v "components/shared/$f\|components/shared/__tests__/$f")
  if [ -n "$hits" ]; then
    echo "=== STALE for $f ==="
    echo "$hits"
  fi
done
```

Expected: empty output. Any hit is a missed migration.

- [ ] **Step 3: Confirm `git log --follow` works on at least one moved file**

```bash
cd frontend && git log --follow --oneline -5 -- src/components/shared/ResponsiveDialog.tsx
```

Expected: shows history from before the move (the `git mv` preserved it).

- [ ] **Step 4: Run the full code gate one more time**

```bash
cd frontend && npx tsc --noEmit && npx vitest run && npx prettier --check src
```

Expected: tsc clean, 1998 tests pass, prettier clean.

- [ ] **Step 5: Run Storybook snapshots**

```bash
cd frontend && fnm exec --using 20.19.4 npm run snapshots
```

Expected: Storybook build succeeds and snapshots regenerate. If the active
Node version is already ≥20.19, `npm run snapshots` is fine. Commit any
changed/renamed images with the final verification/documentation changes.

- [ ] **Step 6: Manual UI spot check**

Open the dev server (`cd frontend && npm run dev`) and click through:

- Repository wizard (uses ResponsiveDialog, WizardDialog, WizardStepIndicator, SshConnectionSelect, ManagedAgentSelect, RichSelectRow, PlanGate)
- Backup Plan wizard's Source dialog (uses ResponsiveDialog, SshConnectionSelect, ManagedAgentSelect, RichSelectRow, PathSelectorField, CodeEditor)
- Backup Plan wizard's Schedule step (uses SchedulePicker → CronExpressionInput → CronBuilderDialog)
- Add Agent dialog (uses WizardDialog)

Visual parity expected — these moves shouldn't change pixels.

- [ ] **Step 7: (No commit — verification only unless snapshots changed.)**

---

## Open questions for execution

- **Barrel for `components/shared/`?** Not in this plan. Direct imports are clearer and the folder is shallow. Add `components/shared/index.ts` later if it becomes painful — separate, small refactor.
- **`@/components/shared/*` alias?** Skipping. The repo barely uses `@/` (16 files). Adding new alias usage just for shared/ creates a mixed-convention codebase. Migrate the whole codebase to `@/` later if desired, separately.
- **Stories under a `stories/` subfolder?** No — sibling-to-component is the existing pattern. Don't introduce a new convention in the same change as a move.
- **Should feature components also be folder-organized (e.g., `components/account/`, `components/backup-plans/`)?** Tempting but out of scope. The 154-file flat `components/` directory is a separate, bigger problem worth its own plan.

## Risk surface

- **27-file ResponsiveDialog rewrite (Task 2)** — biggest churn. Mitigated by per-depth sed commands + leftover grep + full vitest. Worst case: a missed caller causes a tsc error, which is loud and easy to fix before commit.
- **Wizard barrel split (Task 8)** — consumers may import multiple names in one statement; the split needs care. Mitigated by listing consumers in Step 1 and manually splitting each.
- **Test files' relative imports** — moved tests may import things outside `shared/`, and those paths need an extra `..`. Tasks 2, 5, 7, 8 each include an explicit audit step.
- **Storybook snapshots** — visual snapshots live under `frontend/storybook-snapshots/` (per AGENTS.md). File moves don't change rendered output, but story file moves can affect Storybook indexing and this repo requires snapshots after UI story changes. Run `cd frontend && fnm exec --using 20.19.4 npm run snapshots` after Task 9 (or `npm run snapshots` if the active Node is already ≥20.19) and commit any changed/renamed images with the documentation/final verification commit.

## Reference: source files before/after

| Component             | Before                                      | After                                       |
| --------------------- | ------------------------------------------- | ------------------------------------------- |
| `ResponsiveDialog`    | `components/ResponsiveDialog.tsx`           | `components/shared/ResponsiveDialog.tsx`    |
| `RichSelectRow`       | `components/wizard/RichSelectRow.tsx`       | `components/shared/RichSelectRow.tsx`       |
| `SshConnectionSelect` | `components/SshConnectionSelect.tsx`        | `components/shared/SshConnectionSelect.tsx` |
| `ManagedAgentSelect`  | `components/ManagedAgentSelect.tsx`         | `components/shared/ManagedAgentSelect.tsx`  |
| `DestinationSelect`   | `components/DestinationSelect.tsx`          | `components/shared/DestinationSelect.tsx`   |
| `SchedulePicker`      | `components/SchedulePicker.tsx`             | `components/shared/SchedulePicker.tsx`      |
| `CronExpressionInput` | `components/CronExpressionInput.tsx`        | `components/shared/CronExpressionInput.tsx` |
| `CronBuilderDialog`   | `components/CronBuilderDialog.tsx`          | `components/shared/CronBuilderDialog.tsx`   |
| `CodeEditor`          | `components/CodeEditor.tsx`                 | `components/shared/CodeEditor.tsx`          |
| `PlanGate`            | `components/PlanGate.tsx`                   | `components/shared/PlanGate.tsx`            |
| `PathSelectorField`   | `components/PathSelectorField.tsx`          | `components/shared/PathSelectorField.tsx`   |
| `WizardDialog`        | `components/wizard/WizardDialog.tsx`        | `components/shared/WizardDialog.tsx`        |
| `WizardStepIndicator` | `components/wizard/WizardStepIndicator.tsx` | `components/shared/WizardStepIndicator.tsx` |

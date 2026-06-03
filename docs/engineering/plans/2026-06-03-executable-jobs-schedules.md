# Executable Jobs Schedules Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reframe legacy repository schedules and Backup Plan schedules as executable Jobs while hiding non-executable repositories from legacy job creation.

**Architecture:** Keep the existing backend and `/schedule` route, but change the visible navigation/copy and first-tab composition. Add a small frontend utility that classifies executable legacy repositories, use it in `Schedule.tsx`, and cover the behavior with Vitest plus Storybook.

**Tech Stack:** React 18, TypeScript, MUI, lucide-react, react-i18next, React Router, TanStack Query, Vitest, Storybook, Markdown docs.

---

## File Structure

- Modify `frontend/src/components/AppSidebar.tsx` only if navigation data needs a new visible name; otherwise locale copy is enough.
- Modify `frontend/src/pages/Schedule.tsx` to rename first-tab behavior/copy, render the legacy jobs section as a first-class section, and pass executable legacy repositories into `ScheduleWizard`.
- Add `frontend/src/utils/executableRepositories.ts` for `isExecutableLegacyRepository` and `getExecutableLegacyRepositories`.
- Add `frontend/src/utils/__tests__/executableRepositories.test.ts` for source/observe filtering.
- Modify `frontend/src/components/__tests__/AppSidebar.test.tsx` to expect Jobs navigation.
- Modify `frontend/src/components/__tests__/ScheduledJobsTable.test.tsx` for changed default/empty copy.
- Add `frontend/src/components/ScheduledJobsTable.stories.tsx` for the Legacy Repository Jobs state.
- Modify locale files `frontend/src/locales/en.json`, `frontend/src/locales/es.json`, and `frontend/src/locales/it.json` with matching keys.
- Modify `docs/navigation.md` and `docs/usage-guide.md` for the visible Jobs flow.

## Task 1: Failing Tests For Navigation And Executable Repositories

**Files:**
- Add: `frontend/src/utils/__tests__/executableRepositories.test.ts`
- Modify: `frontend/src/components/__tests__/AppSidebar.test.tsx`
- Modify: `frontend/src/components/__tests__/ScheduledJobsTable.test.tsx`

- [ ] **Step 1: Add executable repository tests**

Create `frontend/src/utils/__tests__/executableRepositories.test.ts`:

```ts
import { describe, expect, it } from 'vitest'
import type { Repository } from '../../types'
import { getExecutableLegacyRepositories, isExecutableLegacyRepository } from '../executableRepositories'

const repo = (overrides: Partial<Repository>): Repository =>
  ({
    id: 1,
    name: 'Repo',
    path: '/repo',
    mode: 'full',
    ...overrides,
  }) as Repository

describe('executable legacy repository filtering', () => {
  it('includes full-mode repositories with legacy source directories', () => {
    expect(isExecutableLegacyRepository(repo({ source_directories: ['/srv/app'] }))).toBe(true)
  })

  it('includes full-mode repositories with source locations', () => {
    expect(
      isExecutableLegacyRepository(
        repo({
          source_locations: [{ source_type: 'local', paths: ['/srv/app'] }],
        })
      )
    ).toBe(true)
  })

  it('includes full-mode repositories with database backup paths', () => {
    expect(
      isExecutableLegacyRepository(
        repo({
          source_locations: [
            {
              source_type: 'local',
              paths: [],
              database: {
                template_id: 'postgres',
                engine: 'postgres',
                display_name: 'Postgres',
                backup_strategy: 'dump',
                capture_mode: 'dump',
                backup_paths: ['/tmp/pg.sql'],
                script_execution_target: 'server',
              },
            },
          ],
        })
      )
    ).toBe(true)
  })

  it('excludes observe-mode repositories and repositories without sources', () => {
    const executable = repo({ id: 1, source_directories: ['/srv/app'] })
    const observe = repo({ id: 2, mode: 'observe', source_directories: ['/srv/app'] })
    const planOwned = repo({ id: 3, source_directories: [], source_locations: [] })

    expect(getExecutableLegacyRepositories([observe, planOwned, executable]).map((r) => r.id)).toEqual([1])
  })
})
```

- [ ] **Step 2: Update sidebar test to expect Jobs**

In `frontend/src/components/__tests__/AppSidebar.test.tsx`, extend the primary
nav assertion:

```ts
expect(screen.getAllByRole('link', { name: /jobs/i })[0]).toHaveAttribute('href', '/schedule')
expect(screen.queryAllByRole('link', { name: /^schedule$/i })).toHaveLength(0)
```

- [ ] **Step 3: Update scheduled jobs table copy tests**

In `frontend/src/components/__tests__/ScheduledJobsTable.test.tsx`, change the
default title and empty assertions:

```ts
expect(screen.getByText('Legacy Repository Jobs')).toBeInTheDocument()
expect(screen.getByText('No legacy repository jobs found')).toBeInTheDocument()
```

- [ ] **Step 4: Run failing tests**

Run:

```bash
cd frontend && npm run test -- --run src/utils/__tests__/executableRepositories.test.ts src/components/__tests__/AppSidebar.test.tsx src/components/__tests__/ScheduledJobsTable.test.tsx
```

Expected: FAIL because `executableRepositories.ts` does not exist and current copy still says Schedule/Scheduled Jobs.

## Task 2: Implement Jobs Copy And Filtering

**Files:**
- Add: `frontend/src/utils/executableRepositories.ts`
- Modify: `frontend/src/pages/Schedule.tsx`
- Modify: `frontend/src/locales/en.json`
- Modify: `frontend/src/locales/es.json`
- Modify: `frontend/src/locales/it.json`

- [ ] **Step 1: Add executable repository helper**

Create `frontend/src/utils/executableRepositories.ts`:

```ts
import type { Repository, SourceLocation } from '../types'

function hasSourceLocationPath(location: SourceLocation): boolean {
  if (location.paths?.some((path) => path.trim().length > 0)) return true
  return Boolean(location.database?.backup_paths?.some((path) => path.trim().length > 0))
}

export function isExecutableLegacyRepository(repository: Repository): boolean {
  if (repository.mode === 'observe') return false
  if (repository.source_directories?.some((path) => path.trim().length > 0)) return true
  return Boolean(repository.source_locations?.some(hasSourceLocationPath))
}

export function getExecutableLegacyRepositories(repositories: Repository[]): Repository[] {
  return repositories.filter(isExecutableLegacyRepository)
}
```

- [ ] **Step 2: Use helper in Schedule page**

In `frontend/src/pages/Schedule.tsx`, import the helper and derive:

```ts
const executableLegacyRepositories = React.useMemo(
  () => getExecutableLegacyRepositories(manageableRepositories),
  [manageableRepositories]
)
const canCreateLegacyJob = executableLegacyRepositories.length > 0
const canCreateBackupPlan = canManageRepositoriesGlobally || manageableRepositories.length > 0
```

Use `canCreateBackupPlan` for the Backup Plan button and `canCreateLegacyJob`
for the legacy job button. Pass `executableLegacyRepositories` to
`ScheduleWizard`.

- [ ] **Step 3: Make legacy jobs first-class**

In `Schedule.tsx`, keep the Backup Plans button and legacy jobs button in the
first tab, but change labels to:

```tsx
{t('schedule.createLegacyJob', { defaultValue: 'Create legacy job' })}
```

Render `ScheduledJobsTable` unconditionally on the first tab so the empty state
is visible:

```tsx
legacySection={
  <ScheduledJobsTable
    jobs={jobs}
    repositories={repositories}
    isLoading={isLoading}
    title={t('schedule.legacyRepositoryJobsTitle')}
    description={t('schedule.legacyRepositoryJobsDescription')}
    ...
  />
}
```

- [ ] **Step 4: Update locale values without adding unmatched keys**

Set the visible navigation/page/tab values:

```json
"navigation": { "items": { "schedule": "Jobs" } }
"schedule": {
  "title": "Jobs",
  "subtitle": "Schedule and run executable backup work, checks, and restore checks",
  "createLegacySchedule": "Create legacy job",
  "createLegacyJob": "Create legacy job",
  "tabs": { "byPlan": "Executable Jobs" },
  "legacyBackupSchedulesTitle": "Legacy Repository Jobs",
  "legacyBackupSchedulesDescription": "Legacy repository jobs continue to run here for repositories with their own source paths. Use Backup Plans for new plan-owned backup workflows.",
  "legacyRepositoryJobsTitle": "Legacy Repository Jobs",
  "legacyRepositoryJobsDescription": "Legacy repository jobs continue to run here for repositories with their own source paths. Use Backup Plans for new plan-owned backup workflows."
}
"scheduledJobsTableSection": {
  "title": "Legacy Repository Jobs",
  "noJobsFound": "No legacy repository jobs found",
  "noJobsDesc": "Create a legacy job for a repository that still owns source paths."
}
```

Apply matching keys to Spanish and Italian locale files. Existing translated
files may use English fallback text where no reliable translation is already
present; parity is more important than inventing poor translations.

- [ ] **Step 5: Run targeted tests**

Run:

```bash
cd frontend && npm run test -- --run src/utils/__tests__/executableRepositories.test.ts src/components/__tests__/AppSidebar.test.tsx src/components/__tests__/ScheduledJobsTable.test.tsx
```

Expected: PASS.

## Task 3: Storybook And Docs

**Files:**
- Add: `frontend/src/components/ScheduledJobsTable.stories.tsx`
- Modify: `docs/navigation.md`
- Modify: `docs/usage-guide.md`

- [ ] **Step 1: Add story**

Create a `ScheduledJobsTable` story with at least one enabled multi-repository
legacy job and one empty state story. Use static handlers from Storybook
actions or `fn` if available in this repo's Storybook setup.

- [ ] **Step 2: Update navigation docs**

In `docs/navigation.md`, change the Backups row from Schedule to Jobs:

```md
| Backups | Jobs | Review executable backup jobs, legacy repository jobs, scheduled checks, restore checks, and plan activity. |
```

- [ ] **Step 3: Update usage guide**

In `docs/usage-guide.md`, update the Backup Plan Schedules paragraph:

```md
The Jobs area still shows executable repository work, including Legacy Repository Jobs for repositories that still own source paths. New backup schedules should usually live on Backup Plans.
```

Add a short Legacy Repository Jobs subsection explaining the GitHub #559
workflow shape and when to use Backup Plans instead.

## Task 4: Full Validation And Publish

**Files:**
- `.github/PULL_REQUEST_TEMPLATE.md` for PR body content only.

- [ ] **Step 1: Run frontend validation**

Run:

```bash
cd frontend && npm run check:locales && npm run typecheck && npm run lint && npm run build
```

Expected: PASS.

- [ ] **Step 2: Run local walkthrough**

Run the app with an available local dev path and verify:

- sidebar shows Jobs;
- `/schedule` opens the Jobs page;
- first tab is Executable Jobs;
- Legacy Repository Jobs empty/table state is visible;
- Create legacy job opens the shared wizard.

- [ ] **Step 3: Reply on GitHub issue #559**

Post a concise final reply noting that the feature remains supported and is
being reframed as Jobs/Legacy Repository Jobs, with Backup Plans remaining the
preferred path when the plan model fits.

- [ ] **Step 4: Commit and push**

Commit with:

```bash
git add docs/engineering/specs/2026-06-03-executable-jobs-schedules.md docs/engineering/plans/2026-06-03-executable-jobs-schedules.md frontend/src docs
git commit -m "feat(frontend): reframe schedules as executable jobs"
```

Push through the repository push workflow, create/attach the PR, and add the
`symphony` label.

## Plan Self-Review

- Spec coverage: The plan covers the rework feedback, visible naming, executable filtering, docs, Storybook, GitHub reply, and frontend validation.
- Placeholder scan: No `TBD` or unresolved task placeholders remain.
- Type consistency: Repository/source helper names match the planned imports and tests.
- Scope check: Backend schedule behavior remains unchanged because inspection showed it already supports the legacy workflow.

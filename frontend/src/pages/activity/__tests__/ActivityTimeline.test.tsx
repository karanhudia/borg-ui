import { describe, it, expect, vi } from 'vitest'
import { fireEvent, screen, within, renderWithProviders } from '../../../test/test-utils'
import ActivityTimeline from '../ActivityTimeline'
import type { ActivityItem } from '../../Activity'
import type { ActionButton } from '../../../components/RowActions'

// Day groups are calendar days, so the fixtures sit at local noon: an offset
// in hours from "now" lands on the wrong calendar day when the suite runs
// shortly after midnight.
const noonDaysAgo = (days: number) => {
  const day = new Date()
  day.setHours(12, 0, 0, 0)
  day.setDate(day.getDate() - days)
  return day.toISOString()
}
const minutesAfterNoon = (days: number, minutes: number) =>
  new Date(new Date(noonDaysAgo(days)).getTime() + minutes * 60 * 1000).toISOString()

const run = (overrides: Partial<ActivityItem>): ActivityItem => ({
  id: 1,
  type: 'backup',
  kind: 'backup',
  category: 'backup',
  status: 'completed',
  trigger: 'plan',
  started_at: noonDaysAgo(0),
  completed_at: minutesAfterNoon(0, 30),
  error_message: null,
  repository: 'nas',
  repository_id: 1,
  log_file_path: '/logs/1.log',
  archive_name: 'nas-2026-09-05',
  package_name: null,
  repository_path: '/mnt/nas',
  backup_plan_name: 'nightly',
  has_logs: true,
  followups: [],
  ...overrides,
})

const items: ActivityItem[] = [
  run({
    id: 1,
    followups: [
      { ...run({ id: 11, kind: 'archive_sync', type: 'archive_sync', trigger: 'followup' }) },
    ],
  }),
  run({
    id: 2,
    kind: 'prune',
    type: 'prune',
    category: 'maintenance',
    trigger: 'schedule',
    schedule_name: 'weekly',
    backup_plan_name: null,
    status: 'running',
    progress_percent: 42,
    progress_message: 'Pruning archive 3 of 7',
    started_at: noonDaysAgo(1),
    completed_at: null,
    followups: [
      run({
        id: 21,
        kind: 'history_merge',
        type: 'history_merge',
        trigger: 'followup',
        status: 'running',
      }),
    ],
  }),
]

function renderTimeline(overrides: Partial<Parameters<typeof ActivityTimeline>[0]> = {}) {
  return renderWithProviders(
    <ActivityTimeline
      items={items}
      loading={false}
      actions={[]}
      showRepository
      getKey={(item) => String(item.id)}
      {...overrides}
    />
  )
}

describe('ActivityTimeline', () => {
  it('groups runs by day', () => {
    renderTimeline()
    expect(screen.getByText('Today')).toBeInTheDocument()
    expect(screen.getByText('Yesterday')).toBeInTheDocument()
    expect(screen.getAllByTestId('run-entry')).toHaveLength(2)
  })

  it('shows the repository, what ran, and what it belongs to', () => {
    renderTimeline()
    const rows = screen.getAllByTestId('run-entry')
    expect(within(rows[0]).getByText('nas')).toBeInTheDocument()
    expect(within(rows[0]).getByTestId('run-kind')).toHaveTextContent('Backup')
    const bands = screen.getAllByTestId('umbrella-band')
    expect(bands[0]).toHaveTextContent('Plan · nightly')
    expect(bands[0]).toHaveAttribute('data-umbrella', 'plan')
    expect(within(rows[1]).getByTestId('run-kind')).toHaveTextContent('Prune')
    expect(bands[1]).toHaveTextContent('Schedule · weekly')
    expect(bands[1]).toHaveAttribute('data-umbrella', 'schedule')
  })

  it('leads with the archive instead of the repository when the scope is pinned', () => {
    renderTimeline({ showRepository: false })
    const rows = screen.getAllByTestId('run-entry')
    expect(within(rows[0]).queryByText('nas')).not.toBeInTheDocument()
    expect(within(rows[0]).getByText('nas-2026-09-05')).toBeInTheDocument()
  })

  it('shows progress for a running run and folds a succeeded chain', () => {
    renderTimeline()
    const rows = screen.getAllByTestId('run-entry')
    expect(within(rows[0]).getByText('2 steps')).toBeInTheDocument()
    expect(within(rows[1]).getByRole('progressbar')).toHaveAttribute('aria-valuenow', '42')
    expect(within(rows[1]).getByText(/42% · Pruning archive 3 of 7/)).toBeInTheDocument()
    // Steps open as timeline rows of their own, with the run itself in
    // sequence, each on the rail with its start time.
    const steps = within(rows[1]).getAllByTestId('run-step')
    expect(steps.map((step) => step.getAttribute('data-role'))).toEqual(['root', 'step'])
    expect(steps[1]).toHaveTextContent('Fold removed history')
  })

  it('offers the actions it is given on every run', () => {
    const onClick = vi.fn()
    const actions: ActionButton<ActivityItem>[] = [
      { icon: <span>L</span>, label: 'Logs', onClick, show: (item) => item.status !== 'running' },
    ]
    renderTimeline({ actions })
    const rows = screen.getAllByTestId('run-entry')
    fireEvent.click(within(rows[0]).getByRole('button', { name: 'Logs' }))
    expect(onClick).toHaveBeenCalledWith(expect.objectContaining({ id: 1 }))
    expect(within(rows[1]).queryByRole('button', { name: 'Logs' })).not.toBeInTheDocument()
  })

  it('renders a skeleton while loading and an empty state with nothing to show', () => {
    const { unmount } = renderTimeline({ items: [], loading: true })
    expect(screen.getByTestId('activity-skeleton')).toBeInTheDocument()
    unmount()
    renderTimeline({ items: [] })
    expect(screen.getByText('No activity found')).toBeInTheDocument()
  })

  it('spells a status out only when the dot cannot say it', () => {
    renderTimeline({
      items: [
        run({ id: 1, status: 'completed' }),
        run({ id: 2, status: 'failed', repository: 'photos' }),
        run({ id: 3, status: 'skipped', repository: 'downloads' }),
      ],
    })
    const [ok, failed, skipped] = screen.getAllByTestId('run-entry')
    // A clean run reads as a green dot and its duration, nothing more, but
    // the dot still names itself for anyone not looking at the colour.
    expect(within(ok).queryByText(/Completed/)).not.toBeInTheDocument()
    expect(within(ok).getByRole('img', { name: 'Completed' })).toBeInTheDocument()
    // How it ended rides in the cell that says how long it took.
    expect(within(failed).getByText(/^Failed/)).toBeInTheDocument()
    expect(within(skipped).getByText(/^Skipped/)).toBeInTheDocument()
  })

  it('asks for the next page behind one load-more button', () => {
    const onLoadMore = vi.fn()
    const many = Array.from({ length: 70 }, (_, index) =>
      run({ id: index + 1, started_at: minutesAfterNoon(0, index), completed_at: null })
    )
    const { unmount } = renderTimeline({ items: many })
    // Everything loaded is rendered: the only "more" is the next page.
    expect(screen.getAllByTestId('run-entry')).toHaveLength(70)
    expect(screen.queryByRole('button', { name: /more/i })).not.toBeInTheDocument()
    unmount()

    renderTimeline({ items: many, hasMore: true, onLoadMore })
    fireEvent.click(screen.getByRole('button', { name: 'Load more' }))
    expect(onLoadMore).toHaveBeenCalled()
  })

  it('rolls a running follow-up chain up into the band status', () => {
    renderTimeline({
      items: [
        run({ id: 2, backup_plan_run_id: 7, started_at: minutesAfterNoon(0, 5) }),
        run({
          id: 1,
          backup_plan_run_id: 7,
          followups: [
            run({ id: 11, kind: 'stats', type: 'stats', trigger: 'followup', status: 'running' }),
          ],
        }),
      ],
    })
    const band = screen.getByTestId('umbrella-band')
    // Both members finished; only the nested step is still running, and
    // the band says so, in the cell that also carries its span. Steps carry
    // no status text of their own.
    expect(within(band).getByText(/^Running/)).toBeInTheDocument()
  })

  it('groups the runs of one plan run under one band, in the order they happened', () => {
    const planRun = [
      run({
        id: 5,
        type: 'script_execution',
        kind: null,
        category: 'system',
        backup_plan_run_id: 40,
        hook_type: 'pre-backup',
        package_name: 'Mount volumes',
        repository: 'Mount volumes',
        repository_path: null,
        archive_name: null,
        started_at: minutesAfterNoon(0, 1),
        completed_at: minutesAfterNoon(0, 1),
      }),
      run({ id: 6, backup_plan_run_id: 40, started_at: minutesAfterNoon(0, 2) }),
      run({
        id: 7,
        backup_plan_run_id: 40,
        repository: 'photos',
        repository_id: 2,
        repository_path: '/mnt/photos',
        status: 'failed',
        started_at: minutesAfterNoon(0, 3),
      }),
      run({ id: 8, backup_plan_name: null, trigger: 'manual', started_at: minutesAfterNoon(0, 9) }),
    ]
    renderTimeline({ items: [...planRun].reverse() })
    const bands = screen.getAllByTestId('umbrella-band')
    expect(bands).toHaveLength(2)
    // The manual run comes first (newest) under its own band.
    expect(bands[0]).toHaveAttribute('data-umbrella', 'manual')
    expect(bands[0]).toHaveTextContent('Manual')
    const plan = bands[1]
    expect(plan).toHaveTextContent('Plan · nightly')
    expect(plan).toHaveTextContent('2 repositories · 3 runs')
    // Once as the band's roll-up, once beside the failed member's duration.
    expect(within(plan).getAllByText(/^Failed/)).toHaveLength(2)
    expect(
      within(plan)
        .getAllByTestId('run-entry')
        .map((entry) => entry.getAttribute('data-status'))
    ).toEqual(['completed', 'completed', 'failed'])
    // A plan-level hook says which hook it was.
    expect(within(plan).getAllByTestId('run-kind')[0]).toHaveTextContent('Pre-backup script')
  })

  it('groups a schedule firing across repositories by schedule and time', () => {
    const fired = [
      run({
        id: 20,
        kind: 'check',
        type: 'check',
        category: 'maintenance',
        trigger: 'schedule',
        schedule_name: null,
        backup_plan_name: null,
        started_at: minutesAfterNoon(0, 0),
      }),
      run({
        id: 21,
        kind: 'check',
        type: 'check',
        category: 'maintenance',
        trigger: 'schedule',
        schedule_name: null,
        backup_plan_name: null,
        repository: 'photos',
        repository_id: 2,
        repository_path: '/mnt/photos',
        started_at: minutesAfterNoon(0, 1),
      }),
      run({
        id: 22,
        kind: 'check',
        type: 'check',
        category: 'maintenance',
        trigger: 'schedule',
        schedule_name: null,
        backup_plan_name: null,
        started_at: minutesAfterNoon(0, 120),
      }),
    ]
    renderTimeline({ items: [...fired].reverse() })
    const bands = screen.getAllByTestId('umbrella-band')
    expect(bands).toHaveLength(2)
    expect(bands[1]).toHaveTextContent('Schedule · Repository Check')
    expect(bands[1]).toHaveTextContent('2 repositories · 2 runs')
    expect(within(bands[0]).getAllByTestId('run-entry')).toHaveLength(1)
  })
})

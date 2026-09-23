import { describe, it, expect, vi } from 'vitest'
import { fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import RepositoryHubRow from '../RepositoryHubRow'
import type { RepositoryTrack, StageState } from '../repositoryTrack'
import type { HubRepository, OperationItem } from '../../../types/operations'

vi.mock('../../shared/PlanGate', () => ({
  default: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}))

const op = (overrides: Partial<OperationItem>): OperationItem =>
  ({
    id: 1,
    kind: 'stats',
    category: 'index',
    status: 'queued',
    repository_id: 1,
    repository: 'nas',
    started_at: null,
    progress_percent: null,
    backup_plan_name: null,
    followups: [],
    ...overrides,
  }) as OperationItem

const stage = (key: StageState['key'], overrides: Partial<StageState> = {}): StageState => ({
  key,
  status: 'idle',
  operation: null,
  reason: null,
  ...overrides,
})

const track = (overrides: Partial<RepositoryTrack> = {}): RepositoryTrack => ({
  repositoryId: 1,
  repositoryName: 'nas',
  foreground: null,
  stages: [stage('connect'), stage('stats'), stage('archives'), stage('history')],
  ...overrides,
})

const repository = (overrides: Partial<HubRepository> = {}): HubRepository => ({
  repository_id: 1,
  repository_name: 'nas',
  repository_type: 'local',
  index_mode: 'full',
  sync_state: 'fresh',
  last_synced_at: new Date(Date.now() - 12 * 60 * 1000).toISOString(),
  last_stats_at: new Date(Date.now() - 11 * 60 * 1000).toISOString(),
  last_history_at: null,
  archives: 18,
  history: { indexed: 16, pending: 0, failed: 2, skipped: 0, truncated: 1, rows: 16219 },
  ...overrides,
})

function renderRow(props: Partial<React.ComponentProps<typeof RepositoryHubRow>> = {}) {
  const handlers = { onOpen: vi.fn(), onRetry: vi.fn() }
  render(
    <MemoryRouter>
      <RepositoryHubRow repository={repository()} track={null} {...handlers} {...props} />
    </MemoryRouter>
  )
  return handlers
}

describe('RepositoryHubRow', () => {
  it('shows when the derived data last changed, not a column per stage', () => {
    renderRow()
    const row = screen.getByTestId('repository-row')
    expect(within(row).getByText('nas')).toBeInTheDocument()
    // The newest of synced (12 minutes) and refreshed (11 minutes).
    expect(within(row).getByText(/updated 11 minutes ago/i)).toBeInTheDocument()
    expect(within(row).queryByText(/16 of 18 indexed/i)).not.toBeInTheDocument()
    expect(within(row).queryByTestId('stage-stats')).not.toBeInTheDocument()
  })

  it('shows the archive count when nothing needs a look', () => {
    renderRow({
      repository: repository({
        history: { indexed: 18, pending: 0, failed: 0, skipped: 0, truncated: 0, rows: 16219 },
      }),
    })
    expect(screen.getByText(/18 archives/i)).toBeInTheDocument()
    expect(screen.queryByText(/synced/i)).not.toBeInTheDocument()
  })

  it('flags failed and truncated history so the problem is not colour alone', () => {
    renderRow()
    expect(screen.getByText(/2 failed/i)).toBeInTheDocument()
    expect(screen.getByText(/1 truncated/i)).toBeInTheDocument()
  })

  it('says when nothing has been built yet', () => {
    renderRow({
      repository: repository({
        sync_state: 'never',
        last_synced_at: null,
        last_stats_at: null,
        archives: 0,
        history: { indexed: 0, pending: 0, failed: 0, skipped: 0, truncated: 0, rows: 0 },
      }),
    })
    expect(screen.getByText(/not updated yet/i)).toBeInTheDocument()
    expect(screen.getByText(/not indexed yet/i)).toBeInTheDocument()
  })
  it('shows the one stage the repository is in', () => {
    renderRow({
      track: track({
        stages: [
          stage('connect'),
          stage('stats', { status: 'running', operation: op({ status: 'running' }) }),
          stage('archives'),
          stage('history'),
        ],
      }),
    })
    const cell = screen.getByTestId('current-stage')
    expect(within(cell).getByTestId('stage-stats')).toHaveAttribute('data-status', 'running')
    expect(within(cell).getByText('Stats')).toBeInTheDocument()
    expect(screen.queryByTestId('stage-archives')).not.toBeInTheDocument()
  })

  it('prefers the running stage over waiting ones', () => {
    renderRow({
      track: track({
        stages: [
          stage('connect'),
          stage('archives', { status: 'done', operation: op({ status: 'completed' }) }),
          stage('history', {
            status: 'running',
            operation: op({ status: 'running', started_at: new Date().toISOString() }),
          }),
          stage('stats', { status: 'waiting', operation: op({}), reason: 'queued' }),
        ],
      }),
    })
    expect(screen.getByTestId('stage-history')).toHaveAttribute('data-status', 'running')
    expect(screen.queryByText(/next in line/i)).not.toBeInTheDocument()
  })

  it('offers a retry on a failed stage', () => {
    const { onRetry } = renderRow({
      track: track({
        stages: [
          stage('connect'),
          stage('archives', { status: 'failed', operation: op({ status: 'failed' }) }),
          stage('history', { status: 'skipped', operation: op({ status: 'skipped' }) }),
          stage('stats'),
        ],
      }),
    })
    const cell = screen.getByTestId('current-stage')
    expect(within(cell).getByTestId('stage-archives')).toHaveAttribute('data-status', 'failed')
    fireEvent.click(within(cell).getByRole('button', { name: /retry/i }))
    expect(onRetry).toHaveBeenCalledWith(expect.objectContaining({ key: 'archives' }))
  })

  it('says why a waiting stage has not started, next to the numbers', () => {
    renderRow({
      track: track({
        stages: [
          stage('connect', { status: 'done', operation: op({ status: 'completed' }) }),
          stage('archives', { status: 'done', operation: op({ status: 'completed' }) }),
          stage('history', { status: 'waiting', operation: op({}), reason: 'upstream_paused' }),
          stage('stats', { status: 'waiting', operation: op({}), reason: 'queued' }),
        ],
      }),
    })
    expect(screen.getByTestId('stage-history')).toHaveAttribute('data-status', 'waiting')
    expect(screen.getByText(/waiting on a paused stage/i)).toBeInTheDocument()
  })

  it('says the repository is idle at rest', () => {
    renderRow({ track: null })
    expect(screen.getByTestId('current-stage')).toHaveTextContent('Idle')
  })

  it('retries from the failed stage', () => {
    const failed = stage('archives', { status: 'failed', operation: op({ status: 'failed' }) })
    const { onRetry } = renderRow({
      track: track({ stages: [stage('connect'), stage('stats'), failed, stage('history')] }),
    })
    fireEvent.click(screen.getByRole('button', { name: /retry/i }))
    expect(onRetry).toHaveBeenCalledWith(failed)
  })

  it('shows the foreground job with its plan and a link to the repository runs', () => {
    renderRow({
      track: track({
        foreground: op({
          kind: 'backup',
          category: 'backup',
          status: 'running',
          started_at: new Date().toISOString(),
          backup_plan_name: 'nightly',
        }),
      }),
    })
    expect(screen.getByText(/backup running/i)).toBeInTheDocument()
    expect(screen.getByText(/nightly/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /view runs/i })).toHaveAttribute(
      'href',
      '/activity?repository_id=1'
    )
  })

  it('opens the repository detail from its name', () => {
    const { onOpen } = renderRow()
    fireEvent.click(screen.getByRole('button', { name: /open the details for nas/i }))
    expect(onOpen).toHaveBeenCalled()
  })

  it('opens the details from the row rebuild icon, where the stages are chosen', () => {
    const { onOpen } = renderRow()
    fireEvent.click(screen.getByRole('button', { name: /rebuild nas/i }))
    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
    expect(onOpen).toHaveBeenCalled()
  })

  it('renders a system lane with only its track and no repository controls', () => {
    renderRow({
      repository: null,
      track: track({
        repositoryId: null,
        repositoryName: 'System',
        stages: [stage('connect'), stage('stats'), stage('archives'), stage('history')],
      }),
    })
    expect(screen.getByText('System')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /rebuild/i })).not.toBeInTheDocument()
    expect(screen.queryByText(/archives/i)).not.toBeInTheDocument()
  })
})

describe('index mode (spec 6.8)', () => {
  it('does not warn that an off repository is out of date', () => {
    // Spec 6.8: an opted-out repository never reads as a problem, and an
    // amber warning on the row is the same claim the summary counts drop.
    renderRow({ repository: repository({ index_mode: 'off', sync_state: 'stale' }) })
    expect(screen.queryByText(/out of date/i)).not.toBeInTheDocument()
    expect(screen.getByText(/not indexed/i)).toBeInTheDocument()
  })

  it('still warns an archives-mode repository whose listing is stale', () => {
    renderRow({ repository: repository({ index_mode: 'archives', sync_state: 'stale' }) })
    expect(screen.getByText(/out of date/i)).toBeInTheDocument()
  })

  it('reads "Not indexed" for an off repository and drops the track', () => {
    renderRow({ repository: repository({ index_mode: 'off' }) })
    expect(screen.getByText(/not indexed/i)).toBeInTheDocument()
    expect(screen.getByText(/background work is off/i)).toBeInTheDocument()
    expect(screen.getByTestId('current-stage')).toHaveTextContent(/background work is off/i)
  })

  it('shows the stage for an off repository while a manual run is going', () => {
    renderRow({
      repository: repository({ index_mode: 'off' }),
      track: track({
        stages: [
          stage('connect'),
          stage('archives', { status: 'running' }),
          stage('history'),
          stage('stats'),
        ],
      }),
    })
    expect(screen.getByTestId('stage-archives')).toBeInTheDocument()
    expect(screen.queryByText(/background work is off/i)).not.toBeInTheDocument()
  })
})

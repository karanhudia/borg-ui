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
  sync_state: 'fresh',
  last_synced_at: new Date(Date.now() - 12 * 60 * 1000).toISOString(),
  last_stats_at: new Date(Date.now() - 11 * 60 * 1000).toISOString(),
  last_history_at: null,
  archives: 18,
  history: { indexed: 16, pending: 0, failed: 2, skipped: 0, truncated: 1, rows: 16219 },
  ...overrides,
})

function renderRow(props: Partial<React.ComponentProps<typeof RepositoryHubRow>> = {}) {
  const handlers = { onOpen: vi.fn(), onRetry: vi.fn(), onRebuild: vi.fn() }
  render(
    <MemoryRouter>
      <RepositoryHubRow
        repository={repository()}
        track={null}
        historyAvailable
        totalHistoryRows={32438}
        {...handlers}
        {...props}
      />
    </MemoryRouter>
  )
  return handlers
}

describe('RepositoryHubRow', () => {
  it('shows the derived data at rest for a repository with nothing running', () => {
    renderRow()
    const row = screen.getByTestId('repository-row')
    expect(within(row).getByText('nas')).toBeInTheDocument()
    expect(within(row).getByText(/synced 12 minutes ago/i)).toBeInTheDocument()
    expect(within(row).getByText(/18 archives/i)).toBeInTheDocument()
    expect(within(row).getByText(/16 of 18 indexed/i)).toBeInTheDocument()
    expect(within(row).getByText(/16,219 rows/i)).toBeInTheDocument()
    expect(within(row).getByText(/50% of all history rows/i)).toBeInTheDocument()
    expect(within(row).getByText(/refreshed 11 minutes ago/i)).toBeInTheDocument()
    expect(within(row).queryByTestId('stage-stats')).not.toBeInTheDocument()
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
    expect(screen.getByText(/not indexed yet/i)).toBeInTheDocument()
    expect(screen.getByText(/no file history yet/i)).toBeInTheDocument()
    expect(screen.getByText(/not refreshed yet/i)).toBeInTheDocument()
    expect(screen.queryByText(/of all history rows/i)).not.toBeInTheDocument()
  })

  it('marks file history as a Pro feature on Community instead of showing counts', () => {
    renderRow({ historyAvailable: false })
    expect(screen.getByText('Pro')).toBeInTheDocument()
    expect(screen.queryByText(/of 18 indexed/i)).not.toBeInTheDocument()
  })

  it('shows only the stages that belong to the run', () => {
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
    expect(screen.queryByTestId('stage-connect')).not.toBeInTheDocument()
    expect(screen.queryByTestId('stage-archives')).not.toBeInTheDocument()
    expect(screen.queryByTestId('stage-history')).not.toBeInTheDocument()
    expect(screen.getByTestId('stage-stats')).toHaveAttribute('data-status', 'running')
  })

  it('keeps every stage in its own column so bars never move between runs', () => {
    renderRow({
      track: track({
        stages: [
          stage('connect'),
          stage('stats'),
          stage('archives'),
          stage('history', { status: 'running', operation: op({ status: 'running' }) }),
        ],
      }),
    })
    const cells = screen.getAllByTestId(/^stage-cell-/)
    expect(cells.map((cell) => cell.dataset.stage)).toEqual([
      'connect',
      'stats',
      'archives',
      'history',
    ])
    expect(screen.getByTestId('stage-cell-stats')).toHaveAttribute('data-empty', 'true')
    expect(screen.getByTestId('stage-cell-history')).toHaveAttribute('data-empty', 'false')
  })

  it('says a stage was skipped rather than done', () => {
    renderRow({
      track: track({
        stages: [
          stage('connect'),
          stage('stats'),
          stage('archives', { status: 'failed', operation: op({ status: 'failed' }) }),
          stage('history', { status: 'skipped', operation: op({ status: 'skipped' }) }),
        ],
      }),
    })
    expect(screen.getByTestId('stage-history')).toHaveAttribute('data-status', 'skipped')
    expect(screen.getByText(/^skipped$/i)).toBeInTheDocument()
    expect(screen.queryByText(/^done$/i)).not.toBeInTheDocument()
  })

  it('renders the stage track under the numbers while work is running', () => {
    renderRow({
      track: track({
        stages: [
          stage('connect', { status: 'done', operation: op({ status: 'completed' }) }),
          stage('stats', {
            status: 'running',
            operation: op({ status: 'running', started_at: new Date().toISOString() }),
          }),
          stage('archives', { status: 'waiting', operation: op({}), reason: 'queued' }),
          stage('history', { status: 'waiting', operation: op({}), reason: 'workers' }),
        ],
      }),
    })
    expect(screen.getByTestId('stage-stats')).toHaveAttribute('data-status', 'running')
    expect(screen.getByText(/waiting for an index worker/i)).toBeInTheDocument()
    expect(screen.getByText(/next in line/i)).toBeInTheDocument()
    expect(screen.getByText(/16 of 18 indexed/i)).toBeInTheDocument()
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

  it('starts a rebuild from the row menu', () => {
    const { onRebuild } = renderRow()
    fireEvent.click(screen.getByRole('button', { name: /rebuild nas/i }))
    fireEvent.click(screen.getByRole('menuitem', { name: /^1\. stats/i }))
    expect(onRebuild).toHaveBeenCalledWith('stats')
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

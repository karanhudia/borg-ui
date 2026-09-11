import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import PipelineBoard from '../PipelineBoard'
import { archivesAPI, operationsAPI } from '../../../services/api'
import type { HubRepository } from '../../../types/operations'

vi.mock('../../../services/api', () => ({
  operationsAPI: {
    getQueue: vi.fn(),
    getRepositories: vi.fn(),
    getRepositoryDetail: vi.fn(),
    reconcileNow: vi.fn(),
    updateLimits: vi.fn(),
  },
  archivesAPI: {
    rebuild: vi.fn(),
    resync: vi.fn(),
  },
}))

vi.mock('../../../hooks/useOperationEvents', () => ({
  useOperationEvents: vi.fn(),
}))

vi.mock('../../../hooks/usePlan', () => ({
  usePlan: () => ({ plan: 'pro', isLoading: false, isPro: true, isFree: false, can: () => true }),
}))

vi.mock('../../shared/PlanGate', () => ({
  default: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}))

function renderBoard(props: Partial<React.ComponentProps<typeof PipelineBoard>> = {}) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <PipelineBoard canManage {...props} />
      </MemoryRouter>
    </QueryClientProvider>
  )
}

const queueOp = (overrides: Record<string, unknown>) => ({
  activity_key: null,
  id: 1,
  type: 'operation',
  kind: 'stats',
  category: 'index',
  status: 'queued',
  trigger: 'reconcile',
  priority: 20,
  run_id: 'r1',
  depends_on_id: null,
  repository_id: 1,
  repository: 'nas',
  repository_path: '/mnt/nas',
  started_at: null,
  completed_at: null,
  created_at: new Date().toISOString(),
  error_message: null,
  skip_reason: null,
  log_file_path: null,
  triggered_by: 'reconcile',
  schedule_id: null,
  schedule_name: null,
  backup_plan_id: null,
  backup_plan_run_id: null,
  backup_plan_name: null,
  archive_name: null,
  package_name: null,
  has_logs: false,
  progress_percent: null,
  progress_current: null,
  progress_total: null,
  progress_message: null,
  execution_mode: null,
  params: null,
  result: null,
  followups: [],
  ...overrides,
})

const limits = {
  index_workers: 2,
  index_running: 1,
  max_concurrent_backups: 1,
  max_concurrent_scheduled_backups: 2,
  max_concurrent_scheduled_checks: 4,
}

const mockQueue = (repositories: unknown[], paused = false, overrides = {}) =>
  (operationsAPI.getQueue as ReturnType<typeof vi.fn>).mockResolvedValue({
    data: { repositories, limits: { ...limits, ...overrides }, paused },
  })

const hubRepository = (overrides: Partial<HubRepository> = {}): HubRepository => ({
  repository_id: 1,
  repository_name: 'nas',
  repository_type: 'local',
  index_mode: 'full',
  sync_state: 'fresh',
  last_synced_at: new Date(Date.now() - 5 * 60 * 1000).toISOString(),
  last_stats_at: new Date(Date.now() - 4 * 60 * 1000).toISOString(),
  last_history_at: null,
  archives: 18,
  history: { indexed: 18, pending: 0, failed: 0, skipped: 0, truncated: 0, rows: 16219 },
  ...overrides,
})

const mockHub = (repositories: HubRepository[], overrides = {}) =>
  (operationsAPI.getRepositories as ReturnType<typeof vi.fn>).mockResolvedValue({
    data: {
      repositories,
      totals: {
        repositories: repositories.length,
        archives: repositories.reduce((sum, r) => sum + r.archives, 0),
        history_rows: repositories.reduce((sum, r) => sum + r.history.rows, 0),
        history_bytes: 4300000,
      },
      last_reconcile_at: new Date(Date.now() - 12 * 60 * 1000).toISOString(),
      reconcile_interval_minutes: 60,
      history_available: true,
      ...overrides,
    },
  })

describe('PipelineBoard', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockHub([
      hubRepository(),
      hubRepository({ repository_id: 2, repository_name: 'photos', archives: 3 }),
    ])
  })

  it('lists every repository with its derived data even when nothing is running', async () => {
    mockQueue([])
    renderBoard()
    await waitFor(() => expect(screen.getAllByTestId('repository-row')).toHaveLength(2))
    expect(screen.getByText(/2 repositories/i)).toBeInTheDocument()
    expect(screen.getByText(/21 archives indexed/i)).toBeInTheDocument()
    expect(screen.getAllByText(/18 of 18 indexed/i).length).toBeGreaterThan(0)
    expect(screen.getByText(/reconcile runs every 60 minutes/i)).toBeInTheDocument()
    expect(screen.queryByTestId('stage-track')).not.toBeInTheDocument()
  })

  it('keeps a repository with work in progress in its place and shows its track', async () => {
    mockQueue([
      {
        repository_id: 2,
        repository_name: 'photos',
        lane_busy: false,
        operations: [queueOp({ id: 2, repository_id: 2, repository: 'photos', status: 'running' })],
      },
    ])
    renderBoard()
    await waitFor(() => expect(screen.getAllByTestId('repository-row')).toHaveLength(2))
    const rows = screen.getAllByTestId('repository-row')
    expect(within(rows[0]).getByText('nas')).toBeInTheDocument()
    expect(within(rows[0]).queryByTestId('stage-track')).not.toBeInTheDocument()
    expect(within(rows[1]).getByText('photos')).toBeInTheDocument()
    expect(within(rows[1]).getByTestId('stage-stats')).toHaveAttribute('data-status', 'running')
  })

  it('shows the foreground job on its repository row', async () => {
    mockQueue([
      {
        repository_id: 1,
        repository_name: 'nas',
        lane_busy: true,
        operations: [
          queueOp({
            kind: 'backup',
            category: 'backup',
            status: 'running',
            started_at: new Date().toISOString(),
          }),
        ],
      },
    ])
    renderBoard()
    const row = (await screen.findAllByTestId('repository-row'))[0]
    expect(within(row).getByRole('link', { name: /view runs/i })).toBeInTheDocument()
  })

  it('names the operation a waiting stage is held up by', async () => {
    // the lane belongs to whichever exclusive operation runs; saying
    // "backup" while a prune holds it contradicts the row above
    mockQueue([
      {
        repository_id: 1,
        repository_name: 'nas',
        lane_busy: true,
        lane_holder: { kind: 'prune', id: 5 },
        operations: [
          queueOp({
            id: 5,
            kind: 'prune',
            category: 'maintenance',
            status: 'running',
            started_at: new Date().toISOString(),
          }),
          queueOp({ id: 6, kind: 'stats', category: 'index', status: 'queued' }),
        ],
      },
    ])
    renderBoard()
    const row = (await screen.findAllByTestId('repository-row'))[0]
    expect(within(row).getByText(/prune still running/i)).toBeInTheDocument()
    // backup is the kind the old wording named whatever held the lane
    expect(within(row).queryByText(/backup still running/i)).not.toBeInTheDocument()
    expect(within(row).queryByText(/\{\{kind\}\}/)).not.toBeInTheDocument()
  })

  it('falls back to the unnamed wording when the payload carries no holder', async () => {
    mockQueue([
      {
        repository_id: 1,
        repository_name: 'nas',
        lane_busy: true,
        operations: [
          queueOp({
            id: 5,
            kind: 'backup',
            category: 'backup',
            status: 'running',
            started_at: new Date().toISOString(),
          }),
          queueOp({ id: 6, kind: 'stats', category: 'index', status: 'queued' }),
        ],
      },
    ])
    renderBoard()
    const row = (await screen.findAllByTestId('repository-row'))[0]
    expect(within(row).getByText(/another operation is still running/i)).toBeInTheDocument()
  })

  it('stops naming a holder the same payload shows as finished', async () => {
    // an event can mark the holder completed in the cache before the queue
    // is refetched; the row must not wait for an operation it lists as
    // done, while the backup that is still running keeps it waiting
    mockQueue([
      {
        repository_id: 1,
        repository_name: 'nas',
        lane_busy: true,
        lane_holder: { kind: 'prune', id: 5 },
        operations: [
          queueOp({
            id: 5,
            kind: 'prune',
            category: 'maintenance',
            status: 'completed',
          }),
          queueOp({
            id: 7,
            kind: 'backup',
            category: 'backup',
            status: 'running',
            started_at: new Date().toISOString(),
          }),
          queueOp({ id: 6, kind: 'stats', category: 'index', status: 'queued' }),
        ],
      },
    ])
    renderBoard()
    const row = (await screen.findAllByTestId('repository-row'))[0]
    expect(within(row).getByText(/another operation is still running/i)).toBeInTheDocument()
    expect(within(row).queryByText(/prune still running/i)).not.toBeInTheDocument()
  })

  it('adds a system lane below the repositories for work with no repository', async () => {
    mockQueue([
      {
        repository_id: null,
        repository_name: 'System',
        lane_busy: false,
        operations: [
          queueOp({
            id: 9,
            repository_id: null,
            repository: null,
            kind: 'package_install',
            category: 'system',
            status: 'running',
          }),
        ],
      },
    ])
    renderBoard()
    await waitFor(() => expect(screen.getAllByTestId('repository-row')).toHaveLength(3))
    const rows = screen.getAllByTestId('repository-row')
    expect(within(rows[2]).getByText('System')).toBeInTheDocument()
  })

  it('starts a reconcile from the summary and reports how many repositories were queued', async () => {
    mockQueue([])
    ;(operationsAPI.reconcileNow as ReturnType<typeof vi.fn>).mockResolvedValue({
      data: { repositories: 2 },
    })
    renderBoard()
    fireEvent.click(await screen.findByRole('button', { name: /reconcile now/i }))
    await waitFor(() => expect(operationsAPI.reconcileNow).toHaveBeenCalled())
    expect(await screen.findByText(/reconcile queued for 2 repositories/i)).toBeInTheDocument()
  })

  it('says when a reconcile queued nothing because every repository was busy', async () => {
    mockQueue([])
    ;(operationsAPI.reconcileNow as ReturnType<typeof vi.fn>).mockResolvedValue({
      data: { repositories: 0 },
    })
    renderBoard()
    fireEvent.click(await screen.findByRole('button', { name: /reconcile now/i }))
    expect(await screen.findByText(/already has index work queued/i)).toBeInTheDocument()
  })

  it('retries a failed stage through the rebuild route', async () => {
    mockQueue([
      {
        repository_id: 1,
        repository_name: 'nas',
        lane_busy: false,
        operations: [queueOp({ id: 9, repository_id: 1, kind: 'archive_sync', status: 'failed' })],
      },
    ])
    ;(archivesAPI.rebuild as ReturnType<typeof vi.fn>).mockResolvedValue({ data: {} })
    renderBoard()
    fireEvent.click(await screen.findByRole('button', { name: /retry/i }))
    await waitFor(() => expect(archivesAPI.rebuild).toHaveBeenCalledWith(1, 'archives'))
  })

  it('opens the repository detail dialog from the repository name', async () => {
    mockQueue([])
    ;(operationsAPI.getRepositoryDetail as ReturnType<typeof vi.fn>).mockResolvedValue({
      data: { repository_id: 1, failed_archives: [], truncated_archives: [] },
    })
    renderBoard()
    fireEvent.click(await screen.findByRole('button', { name: /open the details for nas/i }))
    expect(await screen.findByRole('dialog')).toBeInTheDocument()
    expect(await screen.findByText(/every archive has its file history/i)).toBeInTheDocument()
  })

  it('says the history stage is not available for an agent repository', async () => {
    mockQueue([])
    mockHub([
      hubRepository({
        repository_name: 'k8s-node',
        history: { indexed: 0, pending: 0, failed: 0, skipped: 18, truncated: 0, rows: 0 },
        history_capability: 'agent_unsupported',
      }),
    ])
    renderBoard()
    expect(await screen.findByText(/not available for agent repositories/i)).toBeInTheDocument()
    expect(screen.queryByText(/no file history yet/i)).not.toBeInTheDocument()
  })

  it('changes the index worker count from the file history column header', async () => {
    mockQueue([])
    ;(operationsAPI.updateLimits as ReturnType<typeof vi.fn>).mockResolvedValue({ data: {} })
    renderBoard()
    fireEvent.click(await screen.findByRole('button', { name: /more index workers/i }))
    await waitFor(() => expect(operationsAPI.updateLimits).toHaveBeenCalledWith(3))
  })

  it('hides the worker control for people who cannot manage the queue', async () => {
    mockQueue([])
    renderBoard({ canManage: false })
    await screen.findAllByTestId('repository-row')
    expect(screen.queryByRole('button', { name: /more index workers/i })).not.toBeInTheDocument()
    expect(screen.getByText(/2 workers/i)).toBeInTheDocument()
  })

  it('retries a failed history segment of an agent repository through a resync', async () => {
    // the segment is the merge (an agent repository has no index stage); a
    // rebuild from the history stage would be refused, and one from the
    // listing would wipe every archive's stored info; the resync runs the
    // listing chain, merge included, and invalidates nothing
    mockQueue([
      {
        repository_id: 1,
        repository_name: 'nas',
        lane_busy: false,
        operations: [queueOp({ id: 9, repository_id: 1, kind: 'history_merge', status: 'failed' })],
      },
    ])
    mockHub([hubRepository({ history_capability: 'agent_unsupported' })])
    ;(archivesAPI.resync as ReturnType<typeof vi.fn>).mockResolvedValue({
      data: { run_id: 'r9', operations: [10, 11] },
    })
    renderBoard()
    fireEvent.click(await screen.findByRole('button', { name: /retry/i }))
    await waitFor(() => expect(archivesAPI.resync).toHaveBeenCalledWith(1))
    expect(archivesAPI.rebuild).not.toHaveBeenCalled()
    expect(screen.queryByText(/already queued or running/i)).not.toBeInTheDocument()
  })

  it('says so when the resync yields to index work already in flight', async () => {
    mockQueue([
      {
        repository_id: 1,
        repository_name: 'nas',
        lane_busy: false,
        operations: [queueOp({ id: 9, repository_id: 1, kind: 'history_merge', status: 'failed' })],
      },
    ])
    mockHub([hubRepository({ history_capability: 'agent_unsupported' })])
    ;(archivesAPI.resync as ReturnType<typeof vi.fn>).mockResolvedValue({
      data: { run_id: null, operations: [] },
    })
    renderBoard()
    fireEvent.click(await screen.findByRole('button', { name: /retry/i }))
    expect(await screen.findByText(/already queued or running/i)).toBeInTheDocument()
  })

  it('retries a failed history segment on a plan-locked repository through a resync too', async () => {
    // Community: the segment is the merge as well, and a rebuild from the
    // history stage is refused by the plan gate; the resync re-runs it
    mockQueue([
      {
        repository_id: 1,
        repository_name: 'nas',
        lane_busy: false,
        operations: [queueOp({ id: 9, repository_id: 1, kind: 'history_merge', status: 'failed' })],
      },
    ])
    mockHub([hubRepository({ history_capability: 'plan_locked' })], { history_available: false })
    ;(archivesAPI.resync as ReturnType<typeof vi.fn>).mockResolvedValue({
      data: { run_id: 'r9', operations: [10, 11] },
    })
    renderBoard()
    fireEvent.click(await screen.findByRole('button', { name: /retry/i }))
    await waitFor(() => expect(archivesAPI.resync).toHaveBeenCalledWith(1))
    expect(archivesAPI.rebuild).not.toHaveBeenCalled()
  })

  it('has no rebuild form below the table, only the per-row menus', async () => {
    mockQueue([])
    renderBoard()
    await screen.findAllByTestId('repository-row')
    expect(screen.queryByText(/rebuild derived data/i)).not.toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: /^rebuild /i })).toHaveLength(2)
  })

  it('filters rows by repository name', async () => {
    mockQueue([])
    renderBoard()
    await screen.findAllByTestId('repository-row')
    fireEvent.change(screen.getByRole('textbox', { name: /filter by name/i }), {
      target: { value: 'PHO' },
    })
    const rows = screen.getAllByTestId('repository-row')
    expect(rows).toHaveLength(1)
    expect(within(rows[0]).getByText('photos')).toBeInTheDocument()
  })

  it('narrows to rows that need attention from the toolbar', async () => {
    mockQueue([])
    mockHub([
      hubRepository(),
      hubRepository({ repository_id: 2, repository_name: 'photos', sync_state: 'stale' }),
    ])
    renderBoard()
    await screen.findAllByTestId('repository-row')
    fireEvent.mouseDown(screen.getByRole('combobox', { name: /show/i }))
    fireEvent.click(await screen.findByRole('option', { name: /^stale$/i }))
    const rows = await screen.findAllByTestId('repository-row')
    expect(rows).toHaveLength(1)
    expect(within(rows[0]).getByText('photos')).toBeInTheDocument()
  })

  it('narrows to a reason by clicking its count in the summary', async () => {
    mockQueue([])
    mockHub([
      hubRepository(),
      hubRepository({ repository_id: 2, repository_name: 'photos', sync_state: 'never' }),
    ])
    renderBoard()
    await screen.findAllByTestId('repository-row')
    fireEvent.click(screen.getByRole('button', { name: /1 never indexed/i }))
    const rows = await screen.findAllByTestId('repository-row')
    expect(rows).toHaveLength(1)
    expect(within(rows[0]).getByText('photos')).toBeInTheDocument()
  })

  it('says when the filter matches nothing without dropping the toolbar', async () => {
    mockQueue([])
    renderBoard()
    await screen.findAllByTestId('repository-row')
    fireEvent.change(screen.getByRole('textbox', { name: /filter by name/i }), {
      target: { value: 'zzz' },
    })
    expect(screen.getByText(/no repositories match/i)).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: /filter by name/i })).toHaveValue('zzz')
  })

  it('sorts by history rows from the toolbar', async () => {
    mockQueue([])
    mockHub([
      hubRepository({ history: { ...hubRepository().history, rows: 10 } }),
      hubRepository({
        repository_id: 2,
        repository_name: 'photos',
        history: { ...hubRepository().history, rows: 999 },
      }),
    ])
    renderBoard()
    await screen.findAllByTestId('repository-row')
    fireEvent.mouseDown(screen.getByRole('combobox', { name: /sort by/i }))
    fireEvent.click(await screen.findByRole('option', { name: /history rows/i }))
    await waitFor(() =>
      expect(
        within(screen.getAllByTestId('repository-row')[0]).getByText('photos')
      ).toBeInTheDocument()
    )
  })

  it('windows long lists and reveals more on request', async () => {
    mockQueue([])
    mockHub(
      Array.from({ length: 120 }, (_, i) =>
        hubRepository({
          repository_id: i + 1,
          repository_name: `repo-${String(i).padStart(3, '0')}`,
        })
      )
    )
    renderBoard()
    await waitFor(() => expect(screen.getAllByTestId('repository-row')).toHaveLength(50))
    fireEvent.click(screen.getByRole('button', { name: /show 50 more/i }))
    expect(screen.getAllByTestId('repository-row')).toHaveLength(100)
    fireEvent.click(screen.getByRole('button', { name: /show 20 more/i }))
    expect(screen.getAllByTestId('repository-row')).toHaveLength(120)
    expect(screen.queryByRole('button', { name: /show .* more/i })).not.toBeInTheDocument()
  })

  it('resets the window when the filter changes', async () => {
    mockQueue([])
    mockHub(
      Array.from({ length: 120 }, (_, i) =>
        hubRepository({
          repository_id: i + 1,
          repository_name: `repo-${String(i).padStart(3, '0')}`,
        })
      )
    )
    renderBoard()
    await waitFor(() => expect(screen.getAllByTestId('repository-row')).toHaveLength(50))
    fireEvent.click(screen.getByRole('button', { name: /show 50 more/i }))
    fireEvent.change(screen.getByRole('textbox', { name: /filter by name/i }), {
      target: { value: 'repo-0' },
    })
    expect(screen.getAllByTestId('repository-row')).toHaveLength(50)
    expect(screen.getByRole('button', { name: /show 50 more/i })).toBeInTheDocument()
  })

  it('shows an empty state when there are no repositories at all', async () => {
    mockQueue([])
    mockHub([])
    renderBoard()
    expect(await screen.findByText(/no repositories yet/i)).toBeInTheDocument()
  })

  it('reports a failed queue fetch instead of showing an empty board', async () => {
    ;(operationsAPI.getQueue as ReturnType<typeof vi.fn>).mockRejectedValue(new Error('boom'))
    renderBoard()
    expect(await screen.findByText(/queue could not be loaded/i)).toBeInTheDocument()
  })

  it('reports a failed summary fetch', async () => {
    mockQueue([])
    ;(operationsAPI.getRepositories as ReturnType<typeof vi.fn>).mockRejectedValue(
      new Error('boom')
    )
    renderBoard()
    expect(await screen.findByText(/summary could not be loaded/i)).toBeInTheDocument()
  })
})

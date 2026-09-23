import { describe, it, expect, vi, beforeEach } from 'vitest'
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import PipelineBoard from '../PipelineBoard'
import BackgroundWorkTab from '../../BackgroundWorkTab'
import { archivesAPI, operationsAPI } from '../../../services/api'
import type { HubRepository } from '../../../types/operations'

vi.mock('../../../services/api', () => ({
  operationsAPI: {
    getQueue: vi.fn(),
    pause: vi.fn().mockResolvedValue({ data: { paused: true } }),
    resume: vi.fn(),
    pauseStage: vi.fn().mockResolvedValue({ data: {} }),
    resumeStage: vi.fn().mockResolvedValue({ data: {} }),
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

import { useOperationEvents } from '../../../hooks/useOperationEvents'

vi.mock('../../../hooks/useOperationEvents', () => ({
  useOperationEvents: vi.fn(),
}))

vi.mock('../../../hooks/usePlan', () => ({
  usePlan: () => ({ plan: 'pro', isLoading: false, isPro: true, isFree: false, can: () => true }),
}))

vi.mock('../../shared/PlanGate', () => ({
  default: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}))

vi.mock('../../../hooks/useAuthorization', () => ({
  useAuthorization: () => ({
    globalRoleRank: new Map([['admin', 3]]),
    currentGlobalRole: 'admin',
  }),
}))

function renderBoard(
  props: Partial<React.ComponentProps<typeof PipelineBoard>> = {},
  withParent = false
) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        {withParent ? <BackgroundWorkTab /> : <PipelineBoard canManage {...props} />}
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
    data: {
      repositories,
      limits: { ...limits, ...overrides },
      paused,
      paused_stages: paused ? ['archives', 'retention', 'history', 'stats'] : [],
    },
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
    expect(screen.getAllByText(/updated 4 minutes ago/i).length).toBeGreaterThan(0)
    expect(screen.getByText(/reconcile runs every 60 minutes/i)).toBeInTheDocument()
    expect(screen.queryByTestId('stage-stats')).not.toBeInTheDocument()
  })

  it('keeps a repository with work in progress in its place and shows its track', async () => {
    mockQueue([
      {
        repository_id: 2,
        repository_name: 'photos',
        lane_busy: false,
        index_holder_ids: [],
        operations: [queueOp({ id: 2, repository_id: 2, repository: 'photos', status: 'running' })],
      },
    ])
    renderBoard()
    await waitFor(() => expect(screen.getAllByTestId('repository-row')).toHaveLength(2))
    const rows = screen.getAllByTestId('repository-row')
    expect(within(rows[0]).getByText('nas')).toBeInTheDocument()
    expect(within(rows[0]).getByTestId('current-stage')).toHaveTextContent('Idle')
    expect(within(rows[1]).getByText('photos')).toBeInTheDocument()
    expect(within(rows[1]).getByTestId('stage-stats')).toHaveAttribute('data-status', 'running')
  })

  it('shows the foreground job on its repository row', async () => {
    mockQueue([
      {
        repository_id: 1,
        repository_name: 'nas',
        lane_busy: true,
        index_holder_ids: [],
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

  it('falls through to next in line when the payload carries no holder', async () => {
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
    expect(within(row).getByText(/next in line/i)).toBeInTheDocument()
  })

  it('stops naming a holder the same payload shows as finished', async () => {
    // an event can mark the holder completed in the cache before the queue
    // is refetched; the row must not wait for an operation it lists as
    // done; a different running backup is not evidence that it holds the lane
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
    expect(within(row).getByText(/next in line/i)).toBeInTheDocument()
    expect(within(row).queryByText(/prune still running/i)).not.toBeInTheDocument()
  })

  it('adds a system lane below the repositories for work with no repository', async () => {
    mockQueue([
      {
        repository_id: null,
        repository_name: 'System',
        lane_busy: false,
        index_holder_ids: [],
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
        index_holder_ids: [],
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
    ;(operationsAPI.getRepositoryDetail as ReturnType<typeof vi.fn>).mockResolvedValue({
      data: { repository_id: 1, failed_archives: [], truncated_archives: [] },
    })
    renderBoard()
    // The row shows when the data last changed; what each stage keeps is in
    // the repository's dialog.
    fireEvent.click((await screen.findAllByRole('button', { name: /k8s-node/i }))[0])
    const tile = await screen.findByTestId('repository-data-history')
    expect(tile).toHaveTextContent(/needs a capable agent/i)
    expect(tile).not.toHaveTextContent(/no file history yet/i)
  })

  it('changes the index worker count from the file history block', async () => {
    mockQueue([])
    ;(operationsAPI.updateLimits as ReturnType<typeof vi.fn>).mockResolvedValue({ data: {} })
    renderBoard()
    const block = await screen.findByTestId('stage-block-history')
    fireEvent.click(within(block).getByRole('button', { name: /more index workers/i }))
    await waitFor(() => expect(operationsAPI.updateLimits).toHaveBeenCalledWith(3))
  })

  it('counts repositories per stage and filters the table by a block', async () => {
    mockHub([
      hubRepository(),
      hubRepository({ repository_id: 2, repository_name: 'photos' }),
      hubRepository({ repository_id: 3, repository_name: 'mail' }),
    ])
    mockQueue([
      {
        repository_id: 1,
        repository_name: 'nas',
        lane_busy: false,
        index_holder_ids: [],
        operations: [queueOp({ id: 1, kind: 'archive_sync', status: 'running' })],
      },
      {
        repository_id: 2,
        repository_name: 'photos',
        lane_busy: false,
        index_holder_ids: [],
        operations: [queueOp({ id: 2, repository_id: 2, repository: 'photos', status: 'queued' })],
      },
    ])
    renderBoard()
    await waitFor(() => expect(screen.getAllByTestId('repository-row')).toHaveLength(3))
    const strip = screen.getByRole('group', { name: 'Background stages' })
    expect(within(strip).getByRole('button', { name: 'Archive list' })).toHaveTextContent(
      '1 running'
    )
    fireEvent.click(within(strip).getByRole('button', { name: 'Stats' }))
    const rows = screen.getAllByTestId('repository-row')
    expect(rows).toHaveLength(1)
    expect(within(rows[0]).getByText('photos')).toBeInTheDocument()
    fireEvent.click(within(strip).getByRole('button', { name: 'Stats' }))
    expect(screen.getAllByTestId('repository-row')).toHaveLength(3)
  })

  it('pauses and resumes a single stage', async () => {
    mockQueue([])
    renderBoard()
    fireEvent.click(await screen.findByRole('button', { name: 'Pause File history' }))
    await waitFor(() => expect(operationsAPI.pauseStage).toHaveBeenCalledWith('history'))
  })

  it('offers to resume a stage the queue reports paused', async () => {
    ;(operationsAPI.getQueue as ReturnType<typeof vi.fn>).mockResolvedValue({
      data: { repositories: [], limits, paused: false, paused_stages: ['stats'] },
    })
    renderBoard()
    fireEvent.click(await screen.findByRole('button', { name: 'Resume Stats' }))
    await waitFor(() => expect(operationsAPI.resumeStage).toHaveBeenCalledWith('stats'))
  })

  it('hides the worker control for people who cannot manage the queue', async () => {
    mockQueue([])
    renderBoard({ canManage: false })
    await screen.findAllByTestId('repository-row')
    expect(screen.queryByRole('button', { name: /more index workers/i })).not.toBeInTheDocument()
    expect(screen.getByText(/2 workers/i)).toBeInTheDocument()
  })

  it('keeps an SSE completion when an older running queue response arrives later', async () => {
    const starting = queueOp({ id: 9, kind: 'stats', status: 'queued', run_id: 'r1' })
    const waiting = queueOp({ id: 10, kind: 'archive_sync', status: 'queued', run_id: 'r1' })
    const repository = {
      repository_id: 1,
      repository_name: 'nas',
      lane_busy: false,
      index_holder_ids: [],
      operations: [starting, waiting],
    }
    mockQueue([repository])
    renderBoard()
    expect(await screen.findByTestId('stage-archives')).toHaveAttribute('data-status', 'waiting')
    const running = { ...starting, status: 'running' }
    const staleResponse = {
      data: {
        repositories: [{ ...repository, index_holder_ids: [9], operations: [running, waiting] }],
        limits,
        paused: false,
        paused_stages: [],
      },
    }
    let finishRequest!: (value: typeof staleResponse) => void
    vi.mocked(operationsAPI.getQueue).mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finishRequest = resolve as typeof finishRequest
        }) as never
    )
    const calls = vi.mocked(useOperationEvents).mock.calls
    const onUpdated = calls[calls.length - 1]?.[0]
    act(() => onUpdated?.(running as never))
    await waitFor(() => expect(operationsAPI.getQueue).toHaveBeenCalledTimes(2))
    mockQueue([{ ...repository, operations: [{ ...running, status: 'completed' }, waiting] }])
    act(() => onUpdated?.({ ...running, status: 'completed' } as never))
    await act(async () => {
      finishRequest(staleResponse)
    })
    await waitFor(() => expect(screen.getByText(/next in line/i)).toBeInTheDocument())
    // Had the stale response won, the running stats would be the current stage.
    expect(screen.queryByTestId('stage-stats')).not.toBeInTheDocument()
    expect(screen.queryByText(/other index work to finish/i)).not.toBeInTheDocument()
  })

  it('keeps an SSE completion during a refetch started by the parent pause control', async () => {
    const running = queueOp({ id: 9, kind: 'stats', status: 'running', run_id: 'r1' })
    const waiting = queueOp({ id: 10, kind: 'archive_sync', status: 'queued', run_id: 'r2' })
    const repository = {
      repository_id: 1,
      repository_name: 'nas',
      lane_busy: false,
      index_holder_ids: [9],
      operations: [running, waiting],
    }
    mockQueue([repository])
    renderBoard({}, true)
    expect(await screen.findByText(/other index work to finish/i)).toBeInTheDocument()
    const staleResponse = {
      data: { repositories: [repository], limits, paused: false, paused_stages: [] },
    }
    let finishRequest!: (value: typeof staleResponse) => void
    vi.mocked(operationsAPI.getQueue).mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finishRequest = resolve as typeof finishRequest
        }) as never
    )
    fireEvent.click(screen.getByRole('button', { name: /^pause all$/i }))
    await waitFor(() => expect(finishRequest).toBeDefined())
    mockQueue([
      {
        ...repository,
        index_holder_ids: [],
        operations: [{ ...running, status: 'completed' }, waiting],
      },
    ])
    const calls = vi.mocked(useOperationEvents).mock.calls
    act(() => calls[calls.length - 1]?.[0]({ ...running, status: 'completed' } as never))
    await act(async () => {
      finishRequest(staleResponse)
    })
    await waitFor(() =>
      expect(screen.queryByText(/other index work to finish/i)).not.toBeInTheDocument()
    )
  })

  it('accepts a completed server snapshot newer than a running event received during the fetch', async () => {
    const starting = queueOp({ id: 9, kind: 'stats', status: 'queued' })
    const repository = {
      repository_id: 1,
      repository_name: 'nas',
      lane_busy: false,
      index_holder_ids: [],
      operations: [starting],
    }
    mockQueue([repository])
    renderBoard()
    expect(await screen.findByTestId('stage-stats')).toHaveAttribute('data-status', 'waiting')
    const completedResponse = {
      data: {
        repositories: [{ ...repository, operations: [{ ...starting, status: 'completed' }] }],
        limits,
        paused: false,
        paused_stages: [],
      },
    }
    let finishRequest!: (value: typeof completedResponse) => void
    vi.mocked(operationsAPI.getQueue)
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            finishRequest = resolve as typeof finishRequest
          }) as never
      )
      .mockResolvedValue(completedResponse as never)
    const calls = vi.mocked(useOperationEvents).mock.calls
    const onUpdated = calls[calls.length - 1]?.[0]
    act(() => onUpdated?.({ ...starting, status: 'running' } as never))
    await waitFor(() => expect(finishRequest).toBeDefined())
    act(() => onUpdated?.({ ...starting, status: 'running' } as never))
    await act(async () => {
      finishRequest(completedResponse)
    })
    // Done is at rest: the repository leaves the Current stage column.
    await waitFor(() => expect(screen.queryByTestId('stage-stats')).not.toBeInTheDocument())
  })

  it('lets a slow initial queue fetch finish during a burst of progress events', async () => {
    const running = queueOp({ id: 9, kind: 'stats', status: 'running', progress_percent: 50 })
    const repository = {
      repository_id: 1,
      repository_name: 'nas',
      lane_busy: false,
      index_holder_ids: [9],
      operations: [running],
    }
    const response = {
      data: { repositories: [repository], limits, paused: false, paused_stages: [] },
    }
    let finishRequest!: (value: typeof response) => void
    vi.mocked(operationsAPI.getQueue)
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            finishRequest = resolve as typeof finishRequest
          }) as never
      )
      .mockResolvedValue(response as never)
    renderBoard({}, true)
    await waitFor(() => expect(finishRequest).toBeDefined())
    const calls = vi.mocked(useOperationEvents).mock.calls
    const onProgress = calls[calls.length - 1]?.[1]
    for (let current = 1; current <= 10; current++) {
      act(() =>
        onProgress?.({
          id: 9,
          progress_current: current,
          progress_total: 20,
          progress_percent: current * 5,
          progress_message: `Archive ${current}`,
        })
      )
    }
    expect(operationsAPI.getQueue).toHaveBeenCalledTimes(1)
    await act(async () => {
      finishRequest(response)
    })
    expect(await screen.findByTestId('stage-stats')).toHaveAttribute('data-status', 'running')
    expect(operationsAPI.getQueue).toHaveBeenCalledTimes(1)
  })

  it('does not chain more refetches when progress continues during the follow-up request', async () => {
    const running = queueOp({ id: 9, kind: 'stats', status: 'running' })
    const response = {
      data: {
        repositories: [
          {
            repository_id: 1,
            repository_name: 'nas',
            lane_busy: false,
            index_holder_ids: [9],
            operations: [running],
          },
        ],
        limits,
        paused: false,
        paused_stages: [],
      },
    }
    let finishInitial!: (value: typeof response) => void
    let finishFollowup!: (value: typeof response) => void
    vi.mocked(operationsAPI.getQueue)
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            finishInitial = resolve as typeof finishInitial
          }) as never
      )
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            finishFollowup = resolve as typeof finishFollowup
          }) as never
      )
      .mockResolvedValue(response as never)
    renderBoard({}, true)
    await waitFor(() => expect(finishInitial).toBeDefined())
    const calls = vi.mocked(useOperationEvents).mock.calls
    const handlers = calls[calls.length - 1]
    act(() => handlers?.[0](running as never))
    await act(async () => {
      finishInitial(response)
    })
    await waitFor(() => expect(finishFollowup).toBeDefined())
    for (let current = 1; current <= 10; current++) {
      act(() =>
        handlers?.[1]({
          id: 9,
          progress_current: current,
          progress_total: 20,
          progress_percent: current * 5,
          progress_message: `Archive ${current}`,
        })
      )
    }
    await act(async () => {
      finishFollowup(response)
    })
    expect(await screen.findByTestId('stage-stats')).toHaveAttribute('data-status', 'running')
    expect(operationsAPI.getQueue).toHaveBeenCalledTimes(2)
  })

  it('follows the running index work through SSE updates between two fetches', async () => {
    mockQueue([
      {
        repository_id: 1,
        repository_name: 'nas',
        lane_busy: false,
        index_holder_ids: [9],
        operations: [
          queueOp({ id: 9, repository_id: 1, kind: 'stats', status: 'running' }),
          // another chain's listing: the running stats is foreign work to it
          queueOp({
            id: 10,
            repository_id: 1,
            kind: 'archive_sync',
            status: 'queued',
            run_id: 'r2',
          }),
        ],
      },
    ])
    renderBoard()
    expect(await screen.findByText(/other index work to finish/i)).toBeInTheDocument()
    const calls = vi.mocked(useOperationEvents).mock.calls
    const onUpdated = calls[calls.length - 1]?.[0]
    expect(onUpdated).toBeDefined()
    act(() => {
      onUpdated?.(queueOp({ id: 9, repository_id: 1, kind: 'stats', status: 'completed' }) as never)
    })
    await waitFor(() =>
      expect(screen.queryByText(/other index work to finish/i)).not.toBeInTheDocument()
    )
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

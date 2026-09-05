import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import PipelineBoard from '../PipelineBoard'
import { activityAPI, archivesAPI, operationsAPI, repositoriesAPI } from '../../../services/api'

vi.mock('../../../services/api', () => ({
  operationsAPI: {
    getQueue: vi.fn(),
    updateLimits: vi.fn(),
  },
  archivesAPI: {
    rebuild: vi.fn(),
  },
  activityAPI: {
    list: vi.fn(),
  },
  repositoriesAPI: {
    getRepositories: vi.fn(),
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

describe('PipelineBoard', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    ;(activityAPI.list as ReturnType<typeof vi.fn>).mockResolvedValue({ data: [] })
    ;(repositoriesAPI.getRepositories as ReturnType<typeof vi.fn>).mockResolvedValue({
      data: { repositories: [{ id: 1, name: 'nas' }] },
    })
  })

  it('renders one row per repository under the stage headers', async () => {
    mockQueue([
      { repository_id: 1, repository_name: 'nas', lane_busy: false, operations: [queueOp({})] },
      {
        repository_id: 2,
        repository_name: 'photos',
        lane_busy: false,
        operations: [queueOp({ id: 2, repository_id: 2, repository: 'photos' })],
      },
    ])
    renderBoard()
    await waitFor(() => expect(screen.getAllByTestId('repository-row')).toHaveLength(2))
    expect(screen.getAllByText('Stats').length).toBeGreaterThan(0)
    expect(screen.getAllByText('File history').length).toBeGreaterThan(0)
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
    const row = await screen.findByTestId('repository-row')
    expect(within(row).getByRole('link', { name: /view runs/i })).toBeInTheDocument()
  })

  it('shows the last reconcile time and an inline rebuild when nothing is running', async () => {
    mockQueue([])
    ;(activityAPI.list as ReturnType<typeof vi.fn>).mockResolvedValue({
      data: [{ id: 3, completed_at: new Date(Date.now() - 5 * 60 * 1000).toISOString() }],
    })
    ;(archivesAPI.rebuild as ReturnType<typeof vi.fn>).mockResolvedValue({ data: {} })
    renderBoard()
    expect(await screen.findByText(/nothing is running/i)).toBeInTheDocument()
    expect(await screen.findByText(/last reconcile ran 5 minutes ago/i)).toBeInTheDocument()
    expect(activityAPI.list).toHaveBeenCalledWith(
      expect.objectContaining({ trigger: ['reconcile'], limit: 1 })
    )

    fireEvent.click(await screen.findByRole('button', { name: /^rebuild$/i }))
    await waitFor(() => expect(archivesAPI.rebuild).toHaveBeenCalledWith(1, 'stats'))
  })

  it('retries a failed stage through the rebuild route', async () => {
    mockQueue([
      {
        repository_id: 5,
        repository_name: 'nas',
        lane_busy: false,
        operations: [queueOp({ id: 9, repository_id: 5, kind: 'archive_sync', status: 'failed' })],
      },
    ])
    ;(archivesAPI.rebuild as ReturnType<typeof vi.fn>).mockResolvedValue({ data: {} })
    renderBoard()
    fireEvent.click(await screen.findByRole('button', { name: /retry/i }))
    await waitFor(() => expect(archivesAPI.rebuild).toHaveBeenCalledWith(5, 'archives'))
  })

  it('opens the repository track dialog from the repository name', async () => {
    mockQueue([
      {
        repository_id: 5,
        repository_name: 'nas',
        lane_busy: false,
        operations: [queueOp({ id: 11, repository_id: 5 })],
      },
    ])
    renderBoard()
    fireEvent.click(await screen.findByRole('button', { name: /open the run track for nas/i }))
    expect(await screen.findByRole('dialog')).toBeInTheDocument()
  })

  it('changes the index worker count from the history stage header', async () => {
    mockQueue([
      { repository_id: 1, repository_name: 'nas', lane_busy: false, operations: [queueOp({})] },
    ])
    ;(operationsAPI.updateLimits as ReturnType<typeof vi.fn>).mockResolvedValue({ data: {} })
    renderBoard()
    fireEvent.click(await screen.findByRole('button', { name: /more index workers/i }))
    await waitFor(() => expect(operationsAPI.updateLimits).toHaveBeenCalledWith(3))
  })

  it('hides the worker control for people who cannot manage the queue', async () => {
    mockQueue([
      { repository_id: 1, repository_name: 'nas', lane_busy: false, operations: [queueOp({})] },
    ])
    renderBoard({ canManage: false })
    await screen.findByTestId('repository-row')
    expect(screen.queryByRole('button', { name: /more index workers/i })).not.toBeInTheDocument()
    expect(screen.getByText(/2 workers/i)).toBeInTheDocument()
  })

  it('reports a failed queue fetch instead of showing an empty board', async () => {
    ;(operationsAPI.getQueue as ReturnType<typeof vi.fn>).mockRejectedValue(new Error('boom'))
    renderBoard()
    expect(await screen.findByText(/could not be loaded/i)).toBeInTheDocument()
  })
})

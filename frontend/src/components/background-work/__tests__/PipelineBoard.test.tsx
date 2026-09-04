import { describe, it, expect, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import PipelineBoard from '../PipelineBoard'
import { operationsAPI } from '../../../services/api'

vi.mock('../../../services/api', () => ({
  operationsAPI: {
    getQueue: vi.fn(),
    cancel: vi.fn(),
  },
}))

vi.mock('../../../hooks/useOperationEvents', () => ({
  useOperationEvents: vi.fn(),
}))

function renderBoard() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <PipelineBoard />
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

describe('PipelineBoard', () => {
  it('renders a column per stage with the right operations', async () => {
    ;(operationsAPI.getQueue as ReturnType<typeof vi.fn>).mockResolvedValue({
      data: {
        repositories: [
          { repository_id: 1, repository_name: 'nas', lane_busy: false, operations: [queueOp({})] },
        ],
        limits: {
          index_workers: 2,
          index_running: 1,
          max_concurrent_backups: 1,
          max_concurrent_scheduled_backups: 2,
          max_concurrent_scheduled_checks: 4,
        },
        paused: false,
      },
    })
    renderBoard()
    await waitFor(() => expect(screen.getByText('nas')).toBeInTheDocument())
    expect(screen.getByText('Stats')).toBeInTheDocument()
  })

  it('renders the foreground lane row for a running exclusive operation', async () => {
    ;(operationsAPI.getQueue as ReturnType<typeof vi.fn>).mockResolvedValue({
      data: {
        repositories: [
          {
            repository_id: 1,
            repository_name: 'nas',
            lane_busy: true,
            operations: [queueOp({ kind: 'backup', category: 'backup', status: 'running' })],
          },
        ],
        limits: {
          index_workers: 2,
          index_running: 0,
          max_concurrent_backups: 1,
          max_concurrent_scheduled_backups: 2,
          max_concurrent_scheduled_checks: 4,
        },
        paused: false,
      },
    })
    renderBoard()
    await waitFor(() => expect(screen.getByRole('link', { name: /activity/i })).toBeInTheDocument())
  })

  it('shows the empty state when nothing is running', async () => {
    ;(operationsAPI.getQueue as ReturnType<typeof vi.fn>).mockResolvedValue({
      data: {
        repositories: [],
        limits: {
          index_workers: 2,
          index_running: 0,
          max_concurrent_backups: 1,
          max_concurrent_scheduled_backups: 2,
          max_concurrent_scheduled_checks: 4,
        },
        paused: false,
      },
    })
    renderBoard()
    await waitFor(() => expect(screen.getByText(/nothing is running/i)).toBeInTheDocument())
  })
})

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import RepositoryTrackDialog from '../RepositoryTrackDialog'
import { archivesAPI, operationsAPI } from '../../../services/api'
import type { OperationItem } from '../../../types/operations'

const mockCan = vi.fn(() => true)

vi.mock('../../../hooks/usePlan', () => ({
  usePlan: () => ({
    plan: 'pro',
    isLoading: false,
    isPro: true,
    isFree: false,
    can: mockCan,
  }),
}))

vi.mock('../../../services/api', () => ({
  archivesAPI: { rebuild: vi.fn().mockResolvedValue({ data: { run_id: 'r1', operations: [1] } }) },
  operationsAPI: { getRepositoryDetail: vi.fn() },
}))

const op = (overrides: Partial<OperationItem>): OperationItem => ({
  activity_key: null,
  id: 1,
  type: 'operation',
  kind: 'stats',
  category: 'index',
  status: 'completed',
  trigger: 'reconcile',
  priority: 20,
  run_id: 'r1',
  depends_on_id: null,
  repository_id: 3,
  repository: 'nas',
  repository_path: '/mnt/nas',
  started_at: '2026-09-04T00:00:00Z',
  completed_at: '2026-09-04T00:01:00Z',
  created_at: '2026-09-04T00:00:00Z',
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

const detail = (overrides = {}) => ({
  repository_id: 3,
  failed_archives: [],
  truncated_archives: [],
  ...overrides,
})

function renderDialog(props: Partial<React.ComponentProps<typeof RepositoryTrackDialog>> = {}) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <RepositoryTrackDialog
          open
          onClose={vi.fn()}
          repositoryId={3}
          repositoryName="nas"
          operations={[op({})]}
          {...props}
        />
      </MemoryRouter>
    </QueryClientProvider>
  )
}

describe('RepositoryTrackDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockCan.mockReturnValue(true)
    ;(operationsAPI.getRepositoryDetail as ReturnType<typeof vi.fn>).mockResolvedValue({
      data: detail(),
    })
  })

  it('says history is not available for an agent repository with no index and locks the stage with that reason', async () => {
    renderDialog({
      historyCapability: 'agent_unsupported',
      history: { indexed: 0, pending: 0, failed: 0, skipped: 18, truncated: 0, rows: 0 },
    })
    // the detail section, once loaded, and the stage picker each say so
    expect(await screen.findByText(/not available for agent repositories/i)).toBeInTheDocument()
    expect(screen.getByText(/repositories executed by an agent/i)).toBeInTheDocument()
    expect(screen.queryByText(/every archive has its file history/i)).not.toBeInTheDocument()
    expect(screen.getByTestId('rebuild-stage-history')).toHaveAttribute('data-state', 'locked')
  })

  it('keeps showing an index an agent repository built before it moved', async () => {
    renderDialog({
      historyCapability: 'agent_unsupported',
      history: { indexed: 12, pending: 0, failed: 0, skipped: 0, truncated: 0, rows: 4000 },
    })
    expect(await screen.findByText(/every archive has its file history/i)).toBeInTheDocument()
    expect(screen.getByTestId('rebuild-stage-history')).toHaveAttribute('data-state', 'locked')
  })

  it('says how far an agent repository got and why the rest stays uncovered', async () => {
    renderDialog({
      historyCapability: 'agent_unsupported',
      history: { indexed: 12, pending: 0, failed: 0, skipped: 6, truncated: 0, rows: 4000 },
    })
    expect(await screen.findByText(/covers 12 of 18 archives/i)).toBeInTheDocument()
    expect(screen.getByText(/not available for agent repositories/i)).toBeInTheDocument()
    expect(screen.queryByText(/every archive has its file history/i)).not.toBeInTheDocument()
  })

  it('describes a narrower index mode as the choice made, not as an index in progress', async () => {
    renderDialog({
      indexMode: 'archives',
      history: { indexed: 0, pending: 18, failed: 0, skipped: 0, truncated: 0, rows: 0 },
    })
    expect(await screen.findByText(/archives only/i)).toBeInTheDocument()
    expect(screen.queryByText(/covers 0 of 18 archives/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/every archive has its file history/i)).not.toBeInTheDocument()
  })

  it('makes no claim about an index a plan-locked repository never built', async () => {
    mockCan.mockReturnValue(false)
    renderDialog({
      historyCapability: 'plan_locked',
      history: { indexed: 0, pending: 18, failed: 0, skipped: 0, truncated: 0, rows: 0 },
    })
    expect(await screen.findByText(/no file history yet/i)).toBeInTheDocument()
    expect(screen.queryByText(/every archive has its file history/i)).not.toBeInTheDocument()
  })

  it('says how far the index got while archives are still pending or skipped', async () => {
    renderDialog({
      historyCapability: 'available',
      history: { indexed: 30, pending: 2, failed: 0, skipped: 6, truncated: 0, rows: 9000 },
    })
    expect(await screen.findByText(/covers 30 of 38 archives/i)).toBeInTheDocument()
    expect(screen.queryByText(/every archive has its file history/i)).not.toBeInTheDocument()
  })

  it('drops a picked history stage when the repository loses the stage while open', async () => {
    const { rerender } = renderDialog({ historyCapability: 'available' })
    fireEvent.click(await screen.findByTestId('rebuild-stage-history'))
    expect(screen.getByTestId('rebuild-stage-history')).toHaveAttribute('aria-checked', 'true')

    rerender(
      <QueryClientProvider
        client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
      >
        <MemoryRouter>
          <RepositoryTrackDialog
            open
            onClose={vi.fn()}
            repositoryId={3}
            repositoryName="nas"
            operations={[op({})]}
            historyCapability="agent_unsupported"
          />
        </MemoryRouter>
      </QueryClientProvider>
    )
    await waitFor(() =>
      expect(screen.getByTestId('rebuild-stage-archives')).toHaveAttribute('aria-checked', 'true')
    )
    fireEvent.click(screen.getByRole('button', { name: /^rebuild$/i }))
    await waitFor(() => expect(archivesAPI.rebuild).toHaveBeenCalledWith(3, 'archives'))
  })

  it('renders one row per operation with its stage timing', () => {
    renderDialog({ operations: [op({ kind: 'stats' }), op({ id: 2, kind: 'archive_sync' })] })
    expect(screen.getByText('nas')).toBeInTheDocument()
  })

  it('rebuilds everything from the archive list by default', async () => {
    renderDialog()
    expect(screen.getByText(/rebuild everything for nas/i)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /^rebuild$/i }))
    await waitFor(() => expect(archivesAPI.rebuild).toHaveBeenCalledWith(3, 'archives'))
  })

  it('lists the stage cards in the order the runner executes them', () => {
    renderDialog()
    const names = screen.getAllByRole('radio').map((r) => r.textContent)
    expect(names[0]).toMatch(/1\. archive list/i)
    expect(names[1]).toMatch(/2\. file history/i)
    expect(names[2]).toMatch(/3\. stats/i)
  })

  it('rebuilds from the stage card the person picks and the stages after it', async () => {
    renderDialog()
    fireEvent.click(screen.getByRole('radio', { name: /file history/i }))
    expect(screen.getByText(/rebuild file history and stats for nas/i)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /^rebuild$/i }))
    await waitFor(() => expect(archivesAPI.rebuild).toHaveBeenCalledWith(3, 'history'))
  })

  it('rebuilds only the totals when stats is picked', async () => {
    renderDialog()
    fireEvent.click(screen.getByRole('radio', { name: /stats/i }))
    expect(screen.getByText(/rebuild stats for nas/i)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /^rebuild$/i }))
    await waitFor(() => expect(archivesAPI.rebuild).toHaveBeenCalledWith(3, 'stats'))
  })

  it('locks the file history card on Community', () => {
    mockCan.mockReturnValue(false)
    renderDialog()
    const history = screen.getByRole('radio', { name: /file history/i })
    expect(history).toHaveAttribute('aria-disabled', 'true')
    fireEvent.click(screen.getByRole('radio', { name: /archive list/i }))
    expect(screen.getByText(/rebuild archive list and stats for nas/i)).toBeInTheDocument()
  })

  it('lists the archives whose file history failed or was truncated', async () => {
    ;(operationsAPI.getRepositoryDetail as ReturnType<typeof vi.fn>).mockResolvedValue({
      data: detail({
        failed_archives: [
          {
            id: 7,
            name: 'nas-2026-09-01',
            start: '2026-09-01T02:00:00',
            history_attempts: 3,
            history_rows: null,
          },
        ],
        truncated_archives: [
          {
            id: 8,
            name: 'nas-2026-08-30',
            start: '2026-08-30T02:00:00',
            history_attempts: 0,
            history_rows: 200000,
          },
        ],
      }),
    })
    renderDialog()
    expect(await screen.findByText(/archives whose file history failed/i)).toBeInTheDocument()
    expect(screen.getByText('nas-2026-09-01')).toBeInTheDocument()
    expect(screen.getByText(/3 attempts/i)).toBeInTheDocument()
    expect(screen.getByText(/archives with truncated file history/i)).toBeInTheDocument()
    expect(screen.getByText('nas-2026-08-30')).toBeInTheDocument()
    expect(operationsAPI.getRepositoryDetail).toHaveBeenCalledWith(3)
  })

  it('says so when every archive has its file history', async () => {
    renderDialog()
    expect(await screen.findByText(/every archive has its file history/i)).toBeInTheDocument()
  })

  it('says what a rebuild from the chosen stage covers', () => {
    renderDialog()
    expect(screen.getByText(/rebuild everything for nas/i)).toBeInTheDocument()
  })

  it('links to the index runs of the repository', () => {
    renderDialog()
    expect(screen.getByRole('link', { name: /view index runs/i })).toHaveAttribute(
      'href',
      '/activity?repository_id=3&category=index'
    )
  })
})

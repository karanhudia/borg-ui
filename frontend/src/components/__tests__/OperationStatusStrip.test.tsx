import { describe, it, expect, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import OperationStatusStrip from '../OperationStatusStrip'
import { archivesAPI } from '../../services/api'

vi.mock('../../services/api', () => ({
  archivesAPI: { getStatusStrip: vi.fn() },
}))

vi.mock('../../hooks/useOperationEvents', () => ({ useOperationEvents: vi.fn() }))

function renderStrip(repositoryId = 1) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <OperationStatusStrip repositoryId={repositoryId} />
    </QueryClientProvider>
  )
}

describe('OperationStatusStrip', () => {
  it('renders a cell per category with its age', async () => {
    ;(archivesAPI.getStatusStrip as ReturnType<typeof vi.fn>).mockResolvedValue({
      data: {
        cells: [
          {
            cell: 'backup',
            status: 'completed',
            completed_at: '2026-09-04T00:00:00Z',
            age_seconds: 7200,
            threshold_days: 2,
            overdue: false,
            running: false,
            source: 'operations',
          },
          {
            cell: 'index',
            status: null,
            completed_at: null,
            age_seconds: null,
            threshold_days: 2,
            overdue: null,
            running: true,
            source: null,
          },
        ],
        overdue_available: true,
      },
    })
    renderStrip()
    await waitFor(() => expect(screen.getByText(/backup/i)).toBeInTheDocument())
    expect(screen.getByText(/syncing/i)).toBeInTheDocument()
  })

  it('shows an overdue indicator only when the cell is flagged and overdue data is available', async () => {
    ;(archivesAPI.getStatusStrip as ReturnType<typeof vi.fn>).mockResolvedValue({
      data: {
        cells: [
          {
            cell: 'compact',
            status: 'completed',
            completed_at: '2026-07-25T00:00:00Z',
            age_seconds: 41 * 86400,
            threshold_days: 30,
            overdue: true,
            running: false,
            source: 'legacy',
          },
        ],
        overdue_available: true,
      },
    })
    renderStrip()
    await waitFor(() =>
      expect(screen.getByTestId('status-strip-cell-compact')).toHaveAttribute(
        'data-overdue',
        'true'
      )
    )
  })

  it('labels maintenance cells distinctly instead of collapsing them', async () => {
    ;(archivesAPI.getStatusStrip as ReturnType<typeof vi.fn>).mockResolvedValue({
      data: {
        cells: ['check', 'prune', 'compact'].map((cell) => ({
          cell,
          status: 'completed',
          completed_at: '2026-09-04T00:00:00Z',
          age_seconds: 7200,
          threshold_days: 30,
          overdue: false,
          running: false,
          source: 'operations',
        })),
        overdue_available: true,
      },
    })
    renderStrip()
    await waitFor(() => expect(screen.getByText('Check')).toBeInTheDocument())
    expect(screen.getByText('Prune')).toBeInTheDocument()
    expect(screen.getByText('Compact')).toBeInTheDocument()
    expect(screen.queryByText('Maintenance')).not.toBeInTheDocument()
  })

  it('marks a failed cell as failed rather than done', async () => {
    ;(archivesAPI.getStatusStrip as ReturnType<typeof vi.fn>).mockResolvedValue({
      data: {
        cells: [
          {
            cell: 'backup',
            status: 'failed',
            completed_at: '2026-09-04T00:00:00Z',
            age_seconds: 7200,
            threshold_days: 2,
            overdue: false,
            running: false,
            source: 'operations',
          },
        ],
        overdue_available: true,
      },
    })
    renderStrip()
    await waitFor(() =>
      expect(screen.getByTestId('status-strip-cell-backup')).toHaveAttribute(
        'data-status',
        'failed'
      )
    )
  })

  it('omits the mirror cell when the backend omits it', async () => {
    ;(archivesAPI.getStatusStrip as ReturnType<typeof vi.fn>).mockResolvedValue({
      data: {
        cells: [
          {
            cell: 'backup',
            status: 'completed',
            completed_at: '2026-09-04T00:00:00Z',
            age_seconds: 7200,
            threshold_days: 2,
            overdue: false,
            running: false,
            source: 'operations',
          },
        ],
        overdue_available: true,
      },
    })
    renderStrip()
    await waitFor(() => expect(screen.getByText(/backup/i)).toBeInTheDocument())
    expect(screen.queryByTestId('status-strip-cell-mirror')).not.toBeInTheDocument()
  })
})

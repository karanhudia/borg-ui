import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import BackgroundWorkTab from '../BackgroundWorkTab'
import { operationsAPI } from '../../services/api'

vi.mock('../../services/api', () => ({
  operationsAPI: {
    getQueue: vi.fn().mockResolvedValue({
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
    }),
    pause: vi.fn().mockResolvedValue({ data: { paused: true } }),
    resume: vi.fn().mockResolvedValue({ data: { paused: false } }),
    updateLimits: vi.fn().mockResolvedValue({ data: {} }),
  },
  archivesAPI: { rebuild: vi.fn() },
  activityAPI: { list: vi.fn().mockResolvedValue({ data: [] }) },
  repositoriesAPI: { getRepositories: vi.fn().mockResolvedValue({ data: { repositories: [] } }) },
}))

vi.mock('../../hooks/useOperationEvents', () => ({ useOperationEvents: vi.fn() }))

vi.mock('../../hooks/useAuthorization', () => ({
  useAuthorization: () => ({
    globalRoleRank: new Map([
      ['viewer', 1],
      ['operator', 2],
      ['admin', 3],
    ]),
    currentGlobalRole: 'admin',
  }),
}))

function renderTab() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <BackgroundWorkTab />
      </MemoryRouter>
    </QueryClientProvider>
  )
}

describe('BackgroundWorkTab', () => {
  it('pauses background work from the header control', async () => {
    renderTab()
    fireEvent.click(await screen.findByRole('button', { name: /pause/i }))
    await waitFor(() => expect(operationsAPI.pause).toHaveBeenCalled())
  })

  it('shows a paused banner with a resume action when the queue is paused', async () => {
    ;(operationsAPI.getQueue as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      data: { repositories: [], limits: { index_workers: 2, index_running: 0 }, paused: true },
    })
    renderTab()
    expect(await screen.findByRole('alert')).toHaveTextContent(/background work is paused/i)
    fireEvent.click(screen.getByRole('button', { name: /resume/i }))
    await waitFor(() => expect(operationsAPI.resume).toHaveBeenCalled())
  })

  it('keeps no global rebuild menu in the header', async () => {
    renderTab()
    await screen.findByText(/nothing is running/i)
    expect(screen.queryByRole('button', { name: /rebuild/i })).not.toBeInTheDocument()
  })
})

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

  it('renders the rebuild menu', async () => {
    renderTab()
    expect(await screen.findByRole('button', { name: /rebuild/i })).toBeInTheDocument()
  })
})

import { useEffect, useState, type ReactNode } from 'react'
import type { Meta, StoryObj } from '@storybook/react-vite'
import MockAdapter from 'axios-mock-adapter'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Box } from '@mui/material'
import OperationStatusStrip from './OperationStatusStrip'
import api from '../services/api'

const hoursAgo = (hours: number) => new Date(Date.now() - hours * 3600 * 1000).toISOString()

const cell = (overrides: Record<string, unknown>) => ({
  cell: 'backup',
  status: 'completed',
  completed_at: hoursAgo(2),
  age_seconds: 7200,
  threshold_days: 2,
  overdue: false,
  running: false,
  source: 'operations',
  ...overrides,
})

// Mirrors the spec 10.2 mock: a healthy repository with one overdue compact
// and a running index sync.
const healthy = {
  cells: [
    cell({ cell: 'backup' }),
    cell({ cell: 'check', completed_at: hoursAgo(72), age_seconds: 259200 }),
    cell({ cell: 'prune' }),
    cell({
      cell: 'compact',
      completed_at: hoursAgo(41 * 24),
      age_seconds: 41 * 86400,
      threshold_days: 30,
      overdue: true,
    }),
    cell({ cell: 'index', status: null, completed_at: null, age_seconds: null, running: true }),
    cell({ cell: 'mirror', completed_at: hoursAgo(6), age_seconds: 21600 }),
  ],
  overdue_available: true,
}

const withFailure = {
  cells: [
    cell({ cell: 'backup', status: 'failed' }),
    cell({ cell: 'check', status: 'cancelled', completed_at: hoursAgo(30) }),
    cell({ cell: 'prune', status: null, completed_at: null, age_seconds: null }),
  ],
  overdue_available: true,
}

function StoryProviders({ children, response }: { children: ReactNode; response: unknown }) {
  const [isReady, setIsReady] = useState(false)

  useEffect(() => {
    const mock = new MockAdapter(api)
    mock.onGet(/\/repositories\/\d+\/status-strip/).reply(200, response)
    mock.onAny().reply(200, {})
    setIsReady(true)
    return () => {
      mock.restore()
    }
  }, [response])

  if (!isReady) return null

  return (
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      {children}
    </QueryClientProvider>
  )
}

function renderStrip(response: unknown) {
  return (
    <StoryProviders response={response}>
      <Box sx={{ p: 3, maxWidth: 640 }}>
        <OperationStatusStrip repositoryId={1} />
      </Box>
    </StoryProviders>
  )
}

const meta = {
  title: 'Components/OperationStatusStrip',
} satisfies Meta<typeof OperationStatusStrip>

export default meta

type Story = StoryObj<typeof meta>

export const Default: Story = {
  render: () => renderStrip(healthy),
}

export const WithFailures: Story = {
  render: () => renderStrip(withFailure),
}

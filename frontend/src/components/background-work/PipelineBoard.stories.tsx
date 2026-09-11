import { useEffect, useState, type ReactNode } from 'react'
import type { Meta, StoryObj } from '@storybook/react-vite'
import MockAdapter from 'axios-mock-adapter'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Box } from '@mui/material'
import PipelineBoard from './PipelineBoard'
import api from '../../services/api'
import {
  busyQueue,
  emptyQueue,
  hubDetail,
  hubResponse,
  maintenanceLaneQueue,
  unnamedLaneQueue,
} from './storyFixtures'
import type { HubResponse, QueueResponse } from '../../types/operations'

function StoryProviders({
  children,
  queue,
  hub,
}: {
  children: ReactNode
  queue: QueueResponse
  hub: HubResponse
}) {
  const [ready, setReady] = useState(false)
  useEffect(() => {
    const mock = new MockAdapter(api)
    mock.onGet('/operations/queue').reply(200, queue)
    mock.onGet('/operations/repositories').reply(200, hub)
    mock.onGet(/\/operations\/repositories\/\d+/).reply(200, hubDetail)
    mock.onGet('/system/info').reply(200, {
      app_version: '2.3.0',
      borg_version: '1.4.0',
      borg2_version: null,
      plan: 'pro',
      features: {},
      feature_access: { archive_history: true },
    })
    mock.onGet('/repositories/').reply(200, {
      repositories: hub.repositories.map((r) => ({ id: r.repository_id, name: r.repository_name })),
    })
    mock.onAny().reply(200, {})
    setReady(true)
    return () => mock.restore()
  }, [queue, hub])
  if (!ready) return null
  return (
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <Box sx={{ p: 3 }}>{children}</Box>
    </QueryClientProvider>
  )
}

const meta = {
  title: 'BackgroundWork/PipelineBoard',
  parameters: { layout: 'fullscreen' },
} satisfies Meta<typeof PipelineBoard>

export default meta

type Story = StoryObj<typeof meta>

export const Busy: Story = {
  render: () => (
    <StoryProviders queue={busyQueue} hub={hubResponse}>
      <PipelineBoard canManage />
    </StoryProviders>
  ),
}

// A prune holds the lane: the queued stages name it instead of claiming a
// backup is running.
export const MaintenanceHoldsTheLane: Story = {
  render: () => (
    <StoryProviders queue={maintenanceLaneQueue} hub={hubResponse}>
      <PipelineBoard canManage />
    </StoryProviders>
  ),
}

// The lane is taken by something this payload does not name: the caption
// says so instead of picking a kind.
export const LaneHolderUnnamed: Story = {
  render: () => (
    <StoryProviders queue={unnamedLaneQueue} hub={hubResponse}>
      <PipelineBoard canManage />
    </StoryProviders>
  ),
}

export const Idle: Story = {
  render: () => (
    <StoryProviders queue={emptyQueue} hub={hubResponse}>
      <PipelineBoard canManage />
    </StoryProviders>
  ),
}

export const Community: Story = {
  render: () => (
    <StoryProviders queue={emptyQueue} hub={{ ...hubResponse, history_available: false }}>
      <PipelineBoard canManage />
    </StoryProviders>
  ),
}

export const NoRepositories: Story = {
  render: () => (
    <StoryProviders
      queue={emptyQueue}
      hub={{
        ...hubResponse,
        repositories: [],
        totals: { repositories: 0, archives: 0, history_rows: 0, history_bytes: null },
      }}
    >
      <PipelineBoard canManage />
    </StoryProviders>
  ),
}

export const ReadOnly: Story = {
  render: () => (
    <StoryProviders queue={busyQueue} hub={hubResponse}>
      <PipelineBoard canManage={false} />
    </StoryProviders>
  ),
}

import { useEffect, useState } from 'react'
import type { Meta, StoryObj } from '@storybook/react-vite'
import MockAdapter from 'axios-mock-adapter'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { Button } from '@mui/material'
import RepositoryTrackDialog from './RepositoryTrackDialog'
import api from '../../services/api'
import { hubDetail, op } from './storyFixtures'
import type { HubRepositoryDetail } from '../../types/operations'

function Wrapper({ detail }: { detail: HubRepositoryDetail }) {
  const [open, setOpen] = useState(true)
  const [ready, setReady] = useState(false)
  useEffect(() => {
    const mock = new MockAdapter(api)
    mock.onGet(/\/operations\/repositories\/\d+/).reply(200, detail)
    mock.onAny().reply(200, {})
    setReady(true)
    return () => mock.restore()
  }, [detail])
  if (!ready) return null
  return (
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <MemoryRouter>
        <Button onClick={() => setOpen(true)}>Open</Button>
        <RepositoryTrackDialog
          open={open}
          onClose={() => setOpen(false)}
          repositoryId={4}
          repositoryName="laptop"
          operations={[
            op({ kind: 'stats', status: 'completed' }),
            op({ id: 2, kind: 'archive_sync', status: 'running' }),
          ]}
        />
      </MemoryRouter>
    </QueryClientProvider>
  )
}

const meta = {
  title: 'BackgroundWork/RepositoryTrackDialog',
} satisfies Meta<typeof RepositoryTrackDialog>

export default meta

type Story = StoryObj<typeof meta>

export const WithProblems: Story = {
  render: () => <Wrapper detail={hubDetail} />,
}

export const AllIndexed: Story = {
  render: () => (
    <Wrapper detail={{ repository_id: 4, failed_archives: [], truncated_archives: [] }} />
  ),
}

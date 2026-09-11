import { useEffect, useState } from 'react'
import type { Meta, StoryObj } from '@storybook/react-vite'
import MockAdapter from 'axios-mock-adapter'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Button } from '@mui/material'
import RepositoryTrackDialog from './RepositoryTrackDialog'
import api from '../../services/api'
import { hubDetail, op } from './storyFixtures'
import type { HubHistorySummary, HubRepositoryDetail, IndexMode } from '../../types/operations'
import type { HistoryCapability } from '../../types/archives'

function Wrapper({
  detail,
  historyCapability,
  history,
  indexMode,
}: {
  detail: HubRepositoryDetail
  historyCapability?: HistoryCapability
  history?: HubHistorySummary
  indexMode?: IndexMode
}) {
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
      <Button onClick={() => setOpen(true)}>Open</Button>
      <RepositoryTrackDialog
        open={open}
        onClose={() => setOpen(false)}
        repositoryId={4}
        repositoryName="laptop"
        historyCapability={historyCapability}
        history={history}
        indexMode={indexMode}
        operations={[
          op({ kind: 'stats', status: 'completed' }),
          op({ id: 2, kind: 'archive_sync', status: 'running' }),
        ]}
      />
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

// An agent's repository: the history stage is locked by the executor, with
// its own wording rather than a plan chip.
export const AgentRepository: Story = {
  render: () => (
    <Wrapper
      detail={{ ...hubDetail, failed_archives: [], truncated_archives: [] }}
      historyCapability="agent_unsupported"
    />
  ),
}

// An index still being built: the dialog says how far it got instead of
// claiming every archive is covered.
export const HistoryPartial: Story = {
  render: () => (
    <Wrapper
      detail={{ repository_id: 4, failed_archives: [], truncated_archives: [] }}
      history={{ indexed: 14, pending: 24, failed: 0, skipped: 0, truncated: 0, rows: 8501 }}
    />
  ),
}

// A repository indexed in `archives` mode: its pending archives are the
// choice made (spec 6.8), so the summary names the mode rather than an
// index in progress.
export const ArchivesOnlyMode: Story = {
  render: () => (
    <Wrapper
      detail={{ repository_id: 4, failed_archives: [], truncated_archives: [] }}
      indexMode="archives"
      history={{ indexed: 0, pending: 18, failed: 0, skipped: 0, truncated: 0, rows: 0 }}
    />
  ),
}

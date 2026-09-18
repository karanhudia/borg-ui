import { useEffect, useMemo, useState } from 'react'
import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box } from '@mui/material'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import MockAdapter from 'axios-mock-adapter'

import api from '../services/api'

import LogManagementTab from './LogManagementTab'

const baseSettings = {
  log_retention_days: 30,
  log_save_policy: 'failed_and_warnings',
  log_max_total_size_mb: 500,
  log_cleanup_on_startup: true,
  cleanup_retention_days: 90,
}

const baseStorage = {
  total_size_mb: 42.7,
  file_count: 128,
  oldest_log_date: '2026-01-05T04:00:00+00:00',
  newest_log_date: '2026-01-31T02:15:00+00:00',
  usage_percent: 9,
  files_by_type: { backup: 96, restore: 4, check: 18, compact: 6, prune: 4, package: 0 },
  limit_mb: 500,
  retention_days: 30,
}

function createQueryClient(
  settings: Partial<typeof baseSettings>,
  storage: Partial<typeof baseStorage> | null
) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, staleTime: Infinity },
      mutations: { retry: false },
    },
  })
  queryClient.setQueryData(['system-settings'], {
    settings: { ...baseSettings, ...settings },
  })
  // the figures as data, so the first render needs no request at all
  if (storage !== null) {
    queryClient.setQueryData(['log-storage-stats'], {
      storage: { ...baseStorage, ...storage },
    })
  }
  return queryClient
}

// The tab refetches the storage route every 30 s, so each story answers it
// on the shared axios instance for as long as it is mounted: the same
// figures again, or 500 for the unavailable state. One adapter per mounted
// story, restored on unmount.
function installStorageMock(storage: Partial<typeof baseStorage> | null): MockAdapter {
  // only the storage route is answered here; anything else passes through
  const adapter = new MockAdapter(api, { onNoMatch: 'passthrough' })
  if (storage === null) {
    adapter.onGet('/settings/system/logs/storage').reply(500, {
      detail: { key: 'backend.errors.settings.failedGetLogStorageStats' },
    })
  } else {
    adapter
      .onGet('/settings/system/logs/storage')
      .reply(200, { storage: { ...baseStorage, ...storage } })
  }
  return adapter
}

// Stable defaults: fresh {} literals per render would churn the useMemo below
// and rebuild the query client on every render.
const DEFAULT_SETTINGS: Partial<typeof baseSettings> = {}
const DEFAULT_STORAGE: Partial<typeof baseStorage> = {}

function LogManagementTabStory({
  settings = DEFAULT_SETTINGS,
  storage = DEFAULT_STORAGE,
}: {
  settings?: Partial<typeof baseSettings>
  // null: the storage route fails
  storage?: Partial<typeof baseStorage> | null
}) {
  // Installed in an effect, restored in its cleanup. The tab mounts only
  // once the adapter is on, so the unavailable story's first request (the
  // only first request: the others hold their figures as data) hits it.
  const [ready, setReady] = useState(false)
  useEffect(() => {
    const mock = installStorageMock(storage)
    setReady(true)
    return () => {
      setReady(false)
      mock.restore()
    }
  }, [storage])
  const queryClient = useMemo(() => createQueryClient(settings, storage), [settings, storage])

  if (!ready) return null
  return (
    <QueryClientProvider client={queryClient}>
      <Box sx={{ maxWidth: 1120, mx: 'auto', p: 3 }}>
        <LogManagementTab />
      </Box>
    </QueryClientProvider>
  )
}

const meta = {
  title: 'Components/LogManagementTab',
  component: LogManagementTab,
  parameters: {
    layout: 'fullscreen',
  },
} satisfies Meta<typeof LogManagementTab>

export default meta

type Story = StoryObj<typeof meta>

export const Defaults: Story = {
  render: () => <LogManagementTabStory />,
}

// Hoisted: a fresh literal per render would reinstall the mock on every
// re-render.
const HIGH_USAGE: Partial<typeof baseStorage> = { total_size_mb: 431.2, usage_percent: 86 }
const LEGACY_RETENTION: Partial<typeof baseSettings> = { cleanup_retention_days: 365 }

export const HighStorageUsage: Story = {
  render: () => <LogManagementTabStory storage={HIGH_USAGE} />,
}

export const StorageUnavailable: Story = {
  // The storage route fails from the start: the card says so and shows no
  // zero figures that would read as an empty store.
  render: () => <LogManagementTabStory storage={null} />,
}

export const LegacyRetentionOutOfRange: Story = {
  // A stored window from before the shared 7-90 day scale (or written via the
  // API) must clamp into range instead of desyncing the slider from its label.
  render: () => <LogManagementTabStory settings={LEGACY_RETENTION} />,
}

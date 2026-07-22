import { useMemo } from 'react'
import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box } from '@mui/material'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

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
  storage: Partial<typeof baseStorage>
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
  queryClient.setQueryData(['log-storage-stats'], {
    storage: { ...baseStorage, ...storage },
  })
  return queryClient
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
  storage?: Partial<typeof baseStorage>
}) {
  const queryClient = useMemo(() => createQueryClient(settings, storage), [settings, storage])

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

export const HighStorageUsage: Story = {
  render: () => <LogManagementTabStory storage={{ total_size_mb: 431.2, usage_percent: 86 }} />,
}

export const LegacyRetentionOutOfRange: Story = {
  // A stored window from before the shared 7-90 day scale (or written via the
  // API) must clamp into range instead of desyncing the slider from its label.
  render: () => <LogManagementTabStory settings={{ cleanup_retention_days: 365 }} />,
}

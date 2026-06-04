import { useEffect, useMemo } from 'react'
import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box } from '@mui/material'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Toaster, toast } from 'react-hot-toast'

import PackagesTab from './PackagesTab'
import { translateBackendKey } from '../utils/translateBackendKey'

const packageRows = [
  {
    id: 7,
    name: 'curl',
    install_command: 'sudo apt-get update && sudo apt-get install -y curl',
    description: 'Transfer data from URLs in backup scripts.',
    status: 'pending',
    install_log: null,
    installed_at: null,
    last_check: null,
    created_at: '2026-01-01T00:00:00+00:00',
    updated_at: '2026-01-01T00:00:00+00:00',
  },
  {
    id: 8,
    name: 'jq',
    install_command: 'sudo apt-get update && sudo apt-get install -y jq',
    description: 'JSON processor for hook scripts.',
    status: 'installed',
    install_log: 'Installed successfully',
    installed_at: '2026-01-02T12:30:00+00:00',
    last_check: '2026-01-02T12:30:00+00:00',
    created_at: '2026-01-01T00:00:00+00:00',
    updated_at: '2026-01-02T12:30:00+00:00',
  },
]

function createPackagesQueryClient() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, staleTime: Infinity },
      mutations: { retry: false },
    },
  })
  queryClient.setQueryData(['packages'], packageRows)
  return queryClient
}

function PackagesTabStory({ showInstallToast = false }: { showInstallToast?: boolean }) {
  const queryClient = useMemo(() => createPackagesQueryClient(), [])

  useEffect(() => {
    if (!showInstallToast) return

    toast.success(
      translateBackendKey({
        key: 'backend.success.packages.installationStarted',
        params: { name: 'curl' },
      }),
      { duration: Infinity, id: 'package-install-started' }
    )

    return () => toast.dismiss('package-install-started')
  }, [showInstallToast])

  return (
    <QueryClientProvider client={queryClient}>
      <Box sx={{ maxWidth: 1120, mx: 'auto', p: 3 }}>
        <PackagesTab />
      </Box>
      <Toaster position="top-right" />
    </QueryClientProvider>
  )
}

const meta = {
  title: 'Components/PackagesTab',
  component: PackagesTab,
  parameters: {
    layout: 'fullscreen',
  },
} satisfies Meta<typeof PackagesTab>

export default meta

type Story = StoryObj<typeof meta>

export const PackageList: Story = {
  render: () => <PackagesTabStory />,
}

export const InstallStartedToast: Story = {
  render: () => <PackagesTabStory showInstallToast />,
}

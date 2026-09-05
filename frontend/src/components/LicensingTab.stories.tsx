import { useMemo } from 'react'
import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box } from '@mui/material'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import LicensingTab from './LicensingTab'
import type { SystemInfo } from '../hooks/useSystemInfo'
import type { Plan } from '../core/features'

function systemInfo(plan: Plan): SystemInfo {
  return {
    app_version: '1.0.0',
    borg_version: '1.4.0',
    borg2_version: null,
    plan,
    features: {},
    entitlement: {
      status: 'none',
      access_level: plan,
      is_full_access: false,
      full_access_consumed: false,
      expires_at: null,
      starts_at: null,
      instance_id: 'inst_story',
      ui_state: 'community',
      last_refresh_at: null,
      last_refresh_error: null,
    },
  }
}

function createLicensingQueryClient(plan: Plan) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, staleTime: Infinity },
      mutations: { retry: false },
    },
  })
  queryClient.setQueryData(['system-info'], systemInfo(plan))
  return queryClient
}

function LicensingTabStory({ plan }: { plan: Plan }) {
  const queryClient = useMemo(() => createLicensingQueryClient(plan), [plan])

  return (
    <QueryClientProvider client={queryClient}>
      <Box sx={{ maxWidth: 640, mx: 'auto', p: 3 }}>
        <LicensingTab />
      </Box>
    </QueryClientProvider>
  )
}

const meta = {
  title: 'Components/LicensingTab',
  component: LicensingTab,
  parameters: {
    layout: 'fullscreen',
  },
} satisfies Meta<typeof LicensingTab>

export default meta

type Story = StoryObj<typeof meta>

/** Pro plan: the buy link sells the next tier up (Enterprise). */
export const ProWithUpgradeLink: Story = {
  render: () => <LicensingTabStory plan="pro" />,
}

/** Enterprise plan: there is no tier above it, so no buy link is rendered. */
export const EnterpriseNoUpgradeLink: Story = {
  render: () => <LicensingTabStory plan="enterprise" />,
}

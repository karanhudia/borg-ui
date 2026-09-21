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

function paidSystemInfo(): SystemInfo {
  const info = systemInfo('pro')
  return {
    ...info,
    entitlement: {
      ...systemInfo('pro').entitlement!,
      status: 'active',
      ui_state: 'paid_active',
      license_id: 'lic_9f2b94a7bdd1',
      expires_at: '2027-07-14T00:00:00Z',
      instance_id: 'bacabf29-b8ef-4a58-ba73-d201e9cac211',
    },
  }
}

const STORY_SEATS = {
  instance_id: 'bacabf29-b8ef-4a58-ba73-d201e9cac211',
  license: { plan: 'pro', expires_at: '2027-07-14T00:00:00Z', max_instances: 3 },
  seats: [
    {
      instance_id: 'bacabf29-b8ef-4a58-ba73-d201e9cac211',
      hostname: 'e298aa862b77',
      app_version: '2.3.0-alpha.1',
      activated_at: '2026-07-14T09:12:00Z',
      last_seen_at: '2026-09-21T10:29:22Z',
    },
    {
      instance_id: '7c1f0a55-2b41-4d0e-9a7b-1f0c2e6d4488',
      hostname: 'borg-k8s-0',
      app_version: '2.2.4',
      activated_at: '2026-05-02T11:40:00Z',
      last_seen_at: null,
    },
  ],
}

function createLicensingQueryClient(plan: Plan, paid: boolean) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, staleTime: Infinity },
      mutations: { retry: false },
    },
  })
  queryClient.setQueryData(['system-info'], paid ? paidSystemInfo() : systemInfo(plan))
  if (paid) {
    queryClient.setQueryData(['license-seats'], STORY_SEATS)
  }
  return queryClient
}

function LicensingTabStory({ plan, paid = false }: { plan: Plan; paid?: boolean }) {
  const queryClient = useMemo(() => createLicensingQueryClient(plan, paid), [plan, paid])

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

/** A paid licence is live: the key field is behind "Replace licence", and the
 *  seats on the licence are listed with a release action on the other rows. */
export const PaidActiveWithSeats: Story = {
  render: () => <LicensingTabStory plan="pro" paid />,
}

/** Enterprise plan: there is no tier above it, so no buy link is rendered. */
export const EnterpriseNoUpgradeLink: Story = {
  render: () => <LicensingTabStory plan="enterprise" />,
}

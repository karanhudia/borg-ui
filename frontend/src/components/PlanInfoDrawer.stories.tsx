import { useRef, type ComponentProps } from 'react'
import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box, CssBaseline } from '@mui/material'
import { ThemeProvider } from '@mui/material/styles'
import { darkTheme } from '../theme'
import PlanInfoDrawer from './PlanInfoDrawer'
import type { EntitlementInfo } from '../hooks/useSystemInfo'

const featureMap = {
  borg_v2: 'pro',
  backup_plan_multi_repository: 'pro',
  backup_plan_mixed_sources: 'pro',
  extra_users: 'pro',
  rclone: 'pro',
  managed_agents: 'pro',
  rbac: 'enterprise',
} as const

const DAY_MS = 24 * 60 * 60 * 1000

const fullAccessEndingSoon: EntitlementInfo = {
  status: 'active',
  access_level: 'full_access',
  is_full_access: true,
  full_access_consumed: true,
  expires_at: new Date(Date.now() + 6 * DAY_MS).toISOString(),
  starts_at: new Date(Date.now() - 54 * DAY_MS).toISOString(),
  instance_id: 'inst_story',
  ui_state: 'full_access_active',
  last_refresh_at: null,
  last_refresh_error: null,
}

const fullAccessExpired: EntitlementInfo = {
  status: 'expired',
  access_level: 'community',
  is_full_access: false,
  full_access_consumed: true,
  expires_at: null,
  starts_at: null,
  instance_id: 'inst_story',
  ui_state: 'full_access_expired',
  last_refresh_at: null,
  last_refresh_error: null,
}

const proLite: EntitlementInfo = {
  status: 'active',
  access_level: 'pro',
  is_full_access: false,
  full_access_consumed: true,
  expires_at: new Date(Date.now() + 300 * DAY_MS).toISOString(),
  starts_at: new Date(Date.now() - 65 * DAY_MS).toISOString(),
  instance_id: 'inst_story',
  license_plan: 'lite',
  ui_state: 'paid_active',
  last_refresh_at: null,
  last_refresh_error: null,
}

const proPreviewExpires = new Date(Date.now() + 9 * DAY_MS).toISOString()
const proPreview: EntitlementInfo = {
  status: 'active',
  access_level: 'community',
  is_full_access: false,
  full_access_consumed: true,
  expires_at: proPreviewExpires,
  starts_at: new Date(Date.now() - 5 * DAY_MS).toISOString(),
  instance_id: 'inst_story',
  ui_state: 'community',
  trial_features: [
    { feature: 'archive_history', expires_at: proPreviewExpires },
    { feature: 'backup_reports', expires_at: proPreviewExpires },
  ],
  last_refresh_at: null,
  last_refresh_error: null,
}

function PlanInfoDrawerStory(args: ComponentProps<typeof PlanInfoDrawer>) {
  const hostRef = useRef<HTMLDivElement>(null)

  return (
    <Box
      ref={hostRef}
      sx={{
        minHeight: 520,
        width: '100%',
        bgcolor: 'background.default',
        position: 'relative',
        overflow: 'hidden',
      }}
    >
      <PlanInfoDrawer
        {...args}
        open={true}
        onClose={() => {}}
        container={() => hostRef.current ?? document.body}
      />
    </Box>
  )
}

const meta = {
  title: 'Components/PlanInfoDrawer',
  component: PlanInfoDrawer,
  parameters: {
    layout: 'fullscreen',
  },
} satisfies Meta<typeof PlanInfoDrawer>

export default meta

type Story = StoryObj<typeof meta>

export const CommunityUpgradeDrawer: Story = {
  args: {
    open: true,
    plan: 'community',
    appVersion: '2.0.2',
    features: featureMap,
    onClose: () => {},
  },
  render: (args) => <PlanInfoDrawerStory {...args} />,
}

export const DarkCommunityUpgradeDrawer: Story = {
  args: {
    open: true,
    plan: 'community',
    appVersion: '2.0.2',
    features: featureMap,
    onClose: () => {},
  },
  render: (args) => (
    <ThemeProvider theme={darkTheme}>
      <CssBaseline />
      <PlanInfoDrawerStory {...args} />
    </ThemeProvider>
  ),
}

/** Six days of full access left: countdown banner plus the trial-sourced buy link. */
export const FullAccessEndingSoonDrawer: Story = {
  args: {
    open: true,
    plan: 'community',
    appVersion: '2.0.2',
    features: featureMap,
    entitlement: fullAccessEndingSoon,
    onClose: () => {},
  },
  render: (args) => <PlanInfoDrawerStory {...args} />,
}

/** Already on Pro: the footer sells Enterprise, never Pro again. */
export const ProPlanDrawer: Story = {
  args: {
    open: true,
    plan: 'pro',
    appVersion: '2.0.2',
    features: featureMap,
    onClose: () => {},
  },
  render: (args) => <PlanInfoDrawerStory {...args} />,
}

/** Lite: gated as Pro, named as bought, with the one-installation note under the title. */
export const ProLiteDrawer: Story = {
  args: {
    open: true,
    plan: 'pro',
    appVersion: '2.0.2',
    features: featureMap,
    entitlement: proLite,
    onClose: () => {},
  },
  render: (args) => <PlanInfoDrawerStory {...args} />,
}

/** A Pro preview on Community opens on Your Plan with the countdown and what it unlocked. */
export const ProPreviewDrawer: Story = {
  args: {
    open: true,
    plan: 'community',
    appVersion: '2.0.2',
    features: featureMap,
    entitlement: proPreview,
    onClose: () => {},
  },
  render: (args) => <PlanInfoDrawerStory {...args} />,
}

/** Enterprise: nothing above it, so there is no upgrade button. */
export const EnterprisePlanDrawer: Story = {
  args: {
    open: true,
    plan: 'enterprise',
    appVersion: '2.0.2',
    features: featureMap,
    onClose: () => {},
  },
  render: (args) => <PlanInfoDrawerStory {...args} />,
}

/** Full access has ended: warning with the "Restore Pro features" button under the text and the expiry offer link. */
export const FullAccessExpiredDrawer: Story = {
  args: {
    open: true,
    plan: 'community',
    appVersion: '2.0.2',
    features: featureMap,
    entitlement: fullAccessExpired,
    onClose: () => {},
  },
  render: (args) => <PlanInfoDrawerStory {...args} />,
}

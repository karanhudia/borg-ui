import type { Meta, StoryObj } from '@storybook/react-vite'
import { Stack } from '@mui/material'
import PlanBadge from './PlanBadge'
import type { EntitlementInfo } from '../hooks/useSystemInfo'

const DAY_MS = 24 * 60 * 60 * 1000

function fullAccess(daysLeft: number): EntitlementInfo {
  return {
    status: 'active',
    access_level: 'full_access',
    is_full_access: true,
    full_access_consumed: true,
    expires_at: new Date(Date.now() + daysLeft * DAY_MS).toISOString(),
    starts_at: new Date(Date.now() - (60 - daysLeft) * DAY_MS).toISOString(),
    instance_id: 'inst_story',
    ui_state: 'full_access_active',
    last_refresh_at: null,
    last_refresh_error: null,
  }
}

const proLite: EntitlementInfo = {
  status: 'active',
  access_level: 'pro',
  is_full_access: false,
  full_access_consumed: true,
  expires_at: null,
  starts_at: null,
  instance_id: 'inst_story',
  license_plan: 'lite',
  ui_state: 'paid_active',
  last_refresh_at: null,
  last_refresh_error: null,
}

function proPreview(daysLeft: number): EntitlementInfo {
  const expires = new Date(Date.now() + daysLeft * DAY_MS).toISOString()
  return {
    status: 'active',
    access_level: 'community',
    is_full_access: false,
    full_access_consumed: true,
    expires_at: expires,
    starts_at: null,
    instance_id: 'inst_story',
    ui_state: 'community',
    trial_features: [{ feature: 'archive_history', expires_at: expires }],
    last_refresh_at: null,
    last_refresh_error: null,
  }
}

const meta = {
  title: 'Components/PlanBadge',
  component: PlanBadge,
  parameters: { layout: 'centered' },
  args: { onClick: () => {} },
} satisfies Meta<typeof PlanBadge>

export default meta
type Story = StoryObj<typeof meta>

export const Community: Story = {
  args: { plan: 'community' },
}

export const Pro: Story = {
  args: { plan: 'pro' },
}

/** A Lite license is gated as Pro; the badge names what was bought. */
export const ProLite: Story = {
  args: { plan: 'pro', entitlement: proLite },
}

/** A per-feature trial on Community: the badge names the preview and counts down. */
export const ProPreview: Story = {
  args: { plan: 'community', entitlement: proPreview(9) },
}

/** More than 14 days left: the badge only says Full Access. */
export const FullAccessEarly: Story = {
  args: { plan: 'community', entitlement: fullAccess(40) },
}

/** Fewer than 14 days left: the badge adds the remaining-days countdown. */
export const FullAccessCountdown: Story = {
  args: { plan: 'community', entitlement: fullAccess(5) },
}

export const AllStates: Story = {
  args: { plan: 'community' },
  render: () => (
    <Stack spacing={1.5} sx={{ p: 3, alignItems: 'flex-start' }}>
      <PlanBadge plan="community" onClick={() => {}} />
      <PlanBadge plan="pro" onClick={() => {}} />
      <PlanBadge plan="pro" entitlement={proLite} onClick={() => {}} />
      <PlanBadge plan="enterprise" onClick={() => {}} />
      <PlanBadge plan="community" entitlement={proPreview(9)} onClick={() => {}} />
      <PlanBadge plan="community" entitlement={fullAccess(40)} onClick={() => {}} />
      <PlanBadge plan="community" entitlement={fullAccess(5)} onClick={() => {}} />
    </Stack>
  ),
}

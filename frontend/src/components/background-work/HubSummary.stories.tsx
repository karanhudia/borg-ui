import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box } from '@mui/material'
import HubSummary from './HubSummary'
import { hubResponse } from './storyFixtures'

const meta = {
  title: 'BackgroundWork/HubSummary',
  component: HubSummary,
  parameters: { layout: 'fullscreen' },
  decorators: [
    (Story) => (
      <Box sx={{ p: 3 }}>
        <Story />
      </Box>
    ),
  ],
  args: {
    totals: hubResponse.totals,
    lastReconcileAt: hubResponse.last_reconcile_at,
    reconcileIntervalMinutes: 60,
    canManage: true,
    onReconcile: () => {},
  },
} satisfies Meta<typeof HubSummary>

export default meta

type Story = StoryObj<typeof meta>

export const Default: Story = {}

export const SizeUnknown: Story = {
  args: { totals: { ...hubResponse.totals, history_bytes: null } },
}

export const NeverReconciled: Story = {
  args: { lastReconcileAt: null },
}

export const ReconcileOff: Story = {
  args: { reconcileIntervalMinutes: 0 },
}

export const ReadOnly: Story = {
  args: { canManage: false },
}

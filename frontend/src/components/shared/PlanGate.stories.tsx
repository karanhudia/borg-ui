import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box, Typography } from '@mui/material'
import PlanGate from './PlanGate'
import { communitySystemInfo } from '../../services/remoteBackends/planStoryFixtures'

const meta = {
  title: 'Components/PlanGate',
  component: PlanGate,
  parameters: {
    layout: 'centered',
    systemInfo: communitySystemInfo,
  },
} satisfies Meta<typeof PlanGate>

export default meta

type Story = StoryObj<typeof meta>

export const WithMessage: Story = {
  args: {
    feature: 'remote_clients',
    message:
      'Remote client switching is available on Pro and Enterprise plans. Upgrade to add or switch to remote Borg UI servers.',
    surface: 'plan_gate_story',
    operation: 'view_message_story',
    children: (
      <Typography variant="body2">
        Remote client management is visible when the plan includes the feature.
      </Typography>
    ),
  },
  render: (args) => (
    <Box sx={{ width: 420, maxWidth: 'calc(100vw - 32px)' }}>
      <PlanGate {...args} />
    </Box>
  ),
}

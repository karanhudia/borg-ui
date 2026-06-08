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

export const WithPreview: Story = {
  args: {
    feature: 'remote_clients',
    message:
      'Remote client switching is available on Pro and Enterprise plans. Upgrade to add or switch to remote Borg UI servers.',
    surface: 'plan_gate_story',
    operation: 'view_preview_story',
    preview: (
      <Box sx={{ display: 'grid', gap: 1.5 }}>
        <Typography variant="h5" fontWeight={700}>
          Remote Clients
        </Typography>
        <Typography color="text.secondary">
          Register Borg UI client servers on other machines, check their health, and switch targets.
        </Typography>
        <Box
          sx={{
            mt: 1,
            p: 2,
            border: '1px solid',
            borderColor: 'divider',
            borderRadius: 2,
            bgcolor: 'background.paper',
          }}
        >
          <Typography fontWeight={700}>This server</Typography>
          <Typography variant="body2" color="text.secondary">
            Current Borg UI server
          </Typography>
        </Box>
      </Box>
    ),
    children: (
      <Typography variant="body2">
        Remote client management is visible when the plan includes the feature.
      </Typography>
    ),
  },
  render: (args) => (
    <Box sx={{ width: 720, maxWidth: 'calc(100vw - 32px)' }}>
      <PlanGate {...args} />
    </Box>
  ),
}

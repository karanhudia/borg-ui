import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box } from '@mui/material'
import WizardStepCloudMirror from './WizardStepCloudMirror'

const remotes = [
  {
    id: 3,
    name: 'local-test',
    provider: 'local',
    last_test_status: 'success',
  },
  {
    id: 4,
    name: 's3-archive',
    provider: 's3',
    last_test_status: 'success',
  },
]

const meta = {
  title: 'Components/Wizard/Cloud Mirror',
  component: WizardStepCloudMirror,
  parameters: {
    layout: 'centered',
  },
} satisfies Meta<typeof WizardStepCloudMirror>

export default meta

type Story = StoryObj<typeof meta>

const baseArgs = {
  data: {
    cloudMirrorEnabled: false,
    rcloneRemoteId: '' as number | '',
    rcloneRemotePath: '',
    rcloneRemotePathVerified: false,
    rcloneSyncPolicy: 'after_success' as const,
    rcloneSyncCronExpression: '0 */6 * * *',
    rcloneSyncTimezone: 'UTC',
    rcloneExtraFlags: '',
  },
  rcloneRemotes: remotes,
  rcloneStatus: { available: true, version: 'rclone v1.66.0' },
  eligible: true,
  onChange: () => {},
  onAddRcloneRemote: () => {},
  onBrowseRemotePath: () => {},
}

export const DisabledByDefault: Story = {
  args: baseArgs,
  render: (args) => (
    <Box sx={{ width: 720, maxWidth: 'calc(100vw - 32px)' }}>
      <WizardStepCloudMirror {...args} />
    </Box>
  ),
}

export const Enabled: Story = {
  args: {
    ...baseArgs,
    data: {
      ...baseArgs.data,
      cloudMirrorEnabled: true,
      rcloneRemoteId: 3,
      rcloneRemotePath: 'borg-ui/production',
      rcloneRemotePathVerified: true,
      rcloneExtraFlags: '--fast-list',
    },
  },
  render: (args) => (
    <Box sx={{ width: 720, maxWidth: 'calc(100vw - 32px)' }}>
      <WizardStepCloudMirror {...args} />
    </Box>
  ),
}

export const RequiresPro: Story = {
  args: {
    ...baseArgs,
    canUseRclone: false,
    rcloneStatus: { available: false, error: 'Cloud mirroring with rclone requires Pro.' },
  },
  render: (args) => (
    <Box sx={{ width: 720, maxWidth: 'calc(100vw - 32px)' }}>
      <WizardStepCloudMirror {...args} />
    </Box>
  ),
}

export const Scheduled: Story = {
  args: {
    ...baseArgs,
    data: {
      ...baseArgs.data,
      cloudMirrorEnabled: true,
      rcloneRemoteId: 4,
      rcloneRemotePath: 'borg-ui/production',
      rcloneRemotePathVerified: true,
      rcloneSyncPolicy: 'scheduled',
      rcloneSyncCronExpression: '15 */4 * * *',
      rcloneSyncTimezone: 'UTC',
      rcloneExtraFlags: '--fast-list',
    },
  },
  render: (args) => (
    <Box sx={{ width: 720, maxWidth: 'calc(100vw - 32px)' }}>
      <WizardStepCloudMirror {...args} />
    </Box>
  ),
}

export const SshPrimaryEnabled: Story = {
  args: {
    ...baseArgs,
    primaryLocation: 'ssh',
    data: {
      ...baseArgs.data,
      cloudMirrorEnabled: true,
      rcloneRemoteId: 4,
      rcloneRemotePath: 'borg-ui/ssh-primary',
      rcloneRemotePathVerified: true,
    },
  },
  render: (args) => (
    <Box sx={{ width: 720, maxWidth: 'calc(100vw - 32px)' }}>
      <WizardStepCloudMirror {...args} />
    </Box>
  ),
}

export const ManagedAgentPrimaryEnabled: Story = {
  args: {
    ...baseArgs,
    primaryLocation: 'agent',
    data: {
      ...baseArgs.data,
      cloudMirrorEnabled: true,
      rcloneRemoteId: 4,
      rcloneRemotePath: 'borg-ui/agent-primary',
      rcloneRemotePathVerified: true,
    },
  },
  render: (args) => (
    <Box sx={{ width: 720, maxWidth: 'calc(100vw - 32px)' }}>
      <WizardStepCloudMirror {...args} />
    </Box>
  ),
}

export const CachedRcloneRepository: Story = {
  args: {
    ...baseArgs,
    storageMode: 'cachedRepository',
    data: {
      ...baseArgs.data,
      cloudMirrorEnabled: true,
      rcloneRemoteId: 4,
      rcloneRemotePath: 'borg-ui/cached-primary',
      rcloneRemotePathVerified: true,
      rcloneSyncPolicy: 'manual',
      rcloneExtraFlags: '--fast-list',
    },
  },
  render: (args) => (
    <Box sx={{ width: 720, maxWidth: 'calc(100vw - 32px)' }}>
      <WizardStepCloudMirror {...args} />
    </Box>
  ),
}

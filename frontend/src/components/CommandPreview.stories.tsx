import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box } from '@mui/material'
import CommandPreview from './CommandPreview'

const meta = {
  title: 'Components/CommandPreview',
  component: CommandPreview,
  parameters: {
    layout: 'centered',
  },
} satisfies Meta<typeof CommandPreview>

export default meta

type Story = StoryObj<typeof meta>

export const LocalBackupCommands: Story = {
  args: {
    mode: 'create',
    repositoryPath: '/mnt/borg/production',
    encryption: 'repokey-blake2',
    compression: 'zstd,6',
    sourceDirs: ['/srv/app', '/etc/borg-ui'],
    repositoryMode: 'full',
    dataSource: 'local',
    borgVersion: 2,
  },
  render: (args) => (
    <Box sx={{ width: 680, maxWidth: 'calc(100vw - 32px)' }}>
      <CommandPreview {...args} />
    </Box>
  ),
}

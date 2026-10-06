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

// Borg 2 has no --remote-path; the remote command travels in BORG_REMOTE_PATH
export const Borg2RemotePath: Story = {
  args: {
    mode: 'create',
    repositoryPath: '/srv/borg/production',
    repositoryLocation: 'ssh',
    host: 'backup-host',
    username: 'borg',
    encryption: 'repokey-aes-ocb',
    compression: 'zstd,6',
    sourceDirs: ['/srv/app'],
    remotePath: '/usr/local/bin/borg2',
    repositoryMode: 'full',
    dataSource: 'local',
    borgVersion: 2,
  },
  render: LocalBackupCommands.render,
}

// Paths with spaces or quotes are shell-quoted in the command
export const PathsNeedingQuotes: Story = {
  args: {
    mode: 'create',
    repositoryPath: '/mnt/borg/my repo',
    encryption: 'repokey-blake2',
    compression: 'zstd,6',
    sourceDirs: ['/srv/my app', "/home/o'brien"],
    excludePatterns: ['/srv/my app/cache dir', '*.tmp'],
    repositoryMode: 'full',
    dataSource: 'local',
    borgVersion: 1,
  },
  render: LocalBackupCommands.render,
}

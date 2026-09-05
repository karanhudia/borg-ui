import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box } from '@mui/material'
import ArchiveSearchField from './ArchiveSearchField'
import { communitySystemInfo, proSystemInfo } from '../../services/remoteBackends/planStoryFixtures'

const meta = {
  title: 'Components/Archives/ArchiveSearchField',
  component: ArchiveSearchField,
  args: {
    repositoryId: 7,
    newestArchiveId: 12,
  },
  render: (args) => (
    <Box sx={{ width: 420, maxWidth: 'calc(100vw - 32px)' }}>
      <ArchiveSearchField {...args} />
    </Box>
  ),
} satisfies Meta<typeof ArchiveSearchField>

export default meta

type Story = StoryObj<typeof meta>

export const Unlocked: Story = {
  parameters: {
    systemInfo: proSystemInfo,
  },
}

export const Locked: Story = {
  parameters: {
    systemInfo: communitySystemInfo,
  },
}

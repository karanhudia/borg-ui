import type { Meta, StoryObj } from '@storybook/react-vite'
import RebuildMenu from './RebuildMenu'
import { communitySystemInfo, proSystemInfo } from '../../services/remoteBackends/planStoryFixtures'

const meta = {
  title: 'BackgroundWork/RebuildMenu',
} satisfies Meta<typeof RebuildMenu>

export default meta

type Story = StoryObj<typeof meta>

export const Default: Story = {
  parameters: {
    systemInfo: proSystemInfo,
  },
  render: () => <RebuildMenu onSelect={() => {}} />,
}

export const Locked: Story = {
  parameters: {
    systemInfo: communitySystemInfo,
  },
  render: () => <RebuildMenu onSelect={() => {}} />,
}

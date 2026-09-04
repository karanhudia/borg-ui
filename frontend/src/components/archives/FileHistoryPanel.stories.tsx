import type { Meta, StoryObj } from '@storybook/react-vite'
import FileHistoryPanel from './FileHistoryPanel'
import { communitySystemInfo, proSystemInfo } from '../../services/remoteBackends/planStoryFixtures'

const meta = {
  title: 'Components/Archives/FileHistoryPanel',
  component: FileHistoryPanel,
  args: {
    repositoryId: 7,
    path: 'home/karan/docs/invoices.xlsx',
    onRestoreEntry: () => {},
  },
} satisfies Meta<typeof FileHistoryPanel>

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

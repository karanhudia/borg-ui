import type { Meta, StoryObj } from '@storybook/react-vite'
import ArchiveFileDetailsPane from './ArchiveFileDetailsPane'
import { proSystemInfo } from '../../services/remoteBackends/planStoryFixtures'

const meta = {
  title: 'Components/Archives/ArchiveFileDetailsPane',
  component: ArchiveFileDetailsPane,
  args: {
    repositoryId: 7,
    onRestore: () => {},
    onDownload: () => {},
  },
  parameters: {
    systemInfo: proSystemInfo,
  },
} satisfies Meta<typeof ArchiveFileDetailsPane>

export default meta

type Story = StoryObj<typeof meta>

export const Folder: Story = {
  args: {
    selectedPath: null,
    selectedEntry: null,
  },
}

export const File: Story = {
  args: {
    selectedPath: 'home/karan/docs/invoices.xlsx',
    selectedEntry: {
      name: 'invoices.xlsx',
      type: 'file',
      path: 'home/karan/docs/invoices.xlsx',
      size: 412_000,
    },
  },
}

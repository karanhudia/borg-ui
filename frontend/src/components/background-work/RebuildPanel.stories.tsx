import type { Meta, StoryObj } from '@storybook/react-vite'
import RebuildPanel from './RebuildPanel'
import type { Repository } from '@/types'

const repositories = [
  { id: 1, name: 'nas-backup', path: '/mnt/nas' },
  { id: 2, name: 'photos', path: '/mnt/photos' },
] as Repository[]

const meta: Meta<typeof RebuildPanel> = {
  title: 'BackgroundWork/RebuildPanel',
  component: RebuildPanel,
  args: { repositories, onRebuild: () => {} },
}

export default meta

type Story = StoryObj<typeof RebuildPanel>

export const Pro: Story = { args: { historyLocked: false } }
export const Community: Story = { args: { historyLocked: true } }

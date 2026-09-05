import type { Meta, StoryObj } from '@storybook/react-vite'
import RunChainRow, { type RunChainOperation } from './RunChainRow'

const meta: Meta<typeof RunChainRow> = {
  title: 'Activity/RunChainRow',
  component: RunChainRow,
}

export default meta

type Story = StoryObj<typeof RunChainRow>

const followup = (kind: string, status: string): RunChainOperation => ({ kind, status })

export const TwoFollowups: Story = {
  args: {
    operation: {
      kind: 'backup',
      status: 'completed',
      followups: [followup('archive_sync', 'completed'), followup('stats', 'completed')],
    },
  },
}

export const Collapsed: Story = {
  args: {
    operation: {
      kind: 'prune',
      status: 'completed',
      followups: [
        followup('history_merge', 'completed'),
        followup('archive_sync', 'completed'),
        followup('stats', 'completed'),
        followup('history_index', 'completed'),
      ],
    },
  },
}

export const WithRunning: Story = {
  args: {
    operation: {
      kind: 'backup',
      status: 'running',
      followups: [
        followup('archive_sync', 'completed'),
        { kind: 'history_index', status: 'running', progress_current: 14, progress_total: 38 },
      ],
    },
  },
}

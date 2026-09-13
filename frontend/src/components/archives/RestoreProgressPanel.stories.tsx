import type { Meta, StoryObj } from '@storybook/react-vite'
import { RestoreProgressPanelView } from './RestoreProgressPanel'

const meta: Meta<typeof RestoreProgressPanelView> = {
  title: 'Archives/RestoreProgressPanel',
  component: RestoreProgressPanelView,
  args: { repositoryId: 7, onDismiss: () => {} },
  parameters: { layout: 'fullscreen' },
}
export default meta
type Story = StoryObj<typeof RestoreProgressPanelView>

export const Queued: Story = { args: { job: undefined } }

export const Running: Story = {
  args: {
    job: {
      id: 42,
      status: 'running',
      destination: '/mnt/restore/2026-09-13',
      progress_details: {
        nfiles: 1284,
        current_file: 'local/Users/karanhudia/Downloads/photos/2026/summer/IMG_4123.HEIC',
        progress_percent: 37.5,
      },
    },
  },
}

export const Completed: Story = {
  args: {
    job: {
      id: 42,
      status: 'completed',
      destination: '/mnt/restore/2026-09-13',
      progress_details: { nfiles: 3209, current_file: '', progress_percent: 100 },
    },
  },
}

export const Failed: Story = {
  args: {
    job: {
      id: 42,
      status: 'failed',
      destination: '/mnt/restore/2026-09-13',
      error_message: 'Destination is not writable: /mnt/restore/2026-09-13',
    },
  },
}

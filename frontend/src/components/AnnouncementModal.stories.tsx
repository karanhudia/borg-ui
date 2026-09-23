import type { Meta, StoryObj } from '@storybook/react-vite'
import { fn } from 'storybook/test'
import AnnouncementModal from './AnnouncementModal'

// Accent text follows the theme palette and the muted line stays at 4.5:1,
// so check both modes with the Theme toolbar.
const meta = {
  title: 'Components/AnnouncementModal',
  component: AnnouncementModal,
  args: {
    open: true,
    onAcknowledge: fn(),
    onSnooze: fn(),
    onCtaClick: fn(),
    announcement: {
      id: 'story-release',
      type: 'release_highlight',
      title: 'Faster archive browsing',
      message: 'Archive listings now load from the index, so large repositories open quickly.',
      highlights: ['Instant archive search', 'Space usage per archive'],
      cta_label: 'Read the release notes',
      cta_url: 'https://example.com/releases',
      dismissible: true,
      snooze_days: 7,
    },
  },
} satisfies Meta<typeof AnnouncementModal>

export default meta

type Story = StoryObj<typeof meta>

export const ReleaseHighlight: Story = {}

export const MaintenanceNotice: Story = {
  args: {
    announcement: {
      id: 'story-maintenance',
      type: 'maintenance_notice',
      title: 'Scheduled maintenance',
      message: 'Backups pause for about ten minutes while the database is upgraded.',
      dismissible: true,
      snooze_days: 1,
    },
  },
}

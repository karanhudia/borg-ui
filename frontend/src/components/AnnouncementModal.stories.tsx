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

// A long release list must scroll inside the dialog, keeping the actions on screen.
export const ManyHighlights: Story = {
  args: {
    announcement: {
      id: 'story-update-many-highlights',
      type: 'update_available',
      title: 'Borg UI 2.3.0 is available',
      message: 'This release brings restore checks, storage insights and a new activity timeline.',
      highlights: [
        'Scheduled restore checks prove archives can be read back',
        'Storage insights show where repository space goes',
        'Activity timeline groups every job in one place',
        'Backup change summary lists added, changed and removed files',
        'Availability backups keep a second copy on another target',
        'Prune preview shows which archives a policy would remove',
        'Archive browsing loads from the index for large repositories',
        'Faster repository stats with fewer borg calls',
        'Agents recover on their own after a lost connection',
        'German translation now covers the whole app',
        'Accessible colours in both themes',
        'Clearer lock error recovery',
        'Many smaller fixes across schedules and notifications',
      ],
      cta_label: 'Read the release notes',
      cta_url: 'https://example.com/releases',
      dismissible: true,
      snooze_days: 7,
    },
  },
}

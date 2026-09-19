import type { Meta, StoryObj } from '@storybook/react-vite'
import { fn } from 'storybook/test'
import ArchiveCard from './ArchiveCard'

const archive = {
  id: 'Downloads-Backup-(Onsite-and-Offsite)-2026-09-18T20:52:01.198',
  archive: 'Downloads-Backup-(Onsite-and-Offsite)-2026-09-18T20:52:01.198',
  name: 'Downloads-Backup-(Onsite-and-Offsite)-2026-09-18T20:52:01.198',
  start: '2026-09-18T15:22:40Z',
  time: '2026-09-18T15:22:40Z',
  triggered_by: 'schedule',
}

const meta: Meta<typeof ArchiveCard> = {
  title: 'Components/ArchiveCard',
  component: ArchiveCard,
  args: {
    archive,
    onView: fn(),
    onRestore: fn(),
    onMount: fn(),
    onDelete: fn(),
  },
}

export default meta

type Story = StoryObj<typeof ArchiveCard>

/** A row in the archive list: the whole row opens the archive's page. */
export const Openable: Story = { args: { onOpen: fn() } }

/** Without an opener the row is inert; only its action icons do anything. */
export const ActionsOnly: Story = {}

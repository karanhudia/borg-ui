import { useState } from 'react'
import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box } from '@mui/material'
import ArchivePickerMenu, { type ArchivePickerRow } from './ArchivePickerMenu'

// Plan archive names run long ({plan}-{repo}-{timestamp}), which is what the
// menu has to hold without spilling across the calendar.
const archives: ArchivePickerRow[] = [
  { id: 1, name: 'raspberrypi-2026-09-24T08:31:11', start: '2026-09-24T03:01:11', size: 0 },
  {
    id: 2,
    name: 'SSH-repo-Backup-Plan-(imp)-SSH-repo-2026-09-24T09:13:00.833',
    start: '2026-09-24T03:43:00',
    size: 0,
  },
  {
    id: 3,
    name: 'Multi-source-remote,-and-repository-on-one-of-the-remotes-SSH-repo-2026-09-24T09:26:55.556',
    start: '2026-09-24T03:57:00',
    size: 0,
  },
  {
    id: 4,
    name: 'Different-remote-source-and-different-remote-destination-SSH-repo-2026-09-24T09:31:30.594',
    start: '2026-09-24T04:01:30',
    size: 53,
  },
  {
    id: 5,
    name: 'Different-remote-source-(files)-and-different-remote-destination-SSH-repo-2026-09-24T09:33:47.503',
    start: '2026-09-24T04:03:47',
    size: 52,
  },
]

function Open({ rows }: { rows: ArchivePickerRow[] }) {
  const [anchor, setAnchor] = useState<HTMLElement | null>(null)
  return (
    <Box sx={{ height: 420 }}>
      <Box ref={setAnchor} sx={{ width: 16, height: 16, bgcolor: 'primary.main', ml: 4 }} />
      <ArchivePickerMenu
        anchorEl={anchor}
        date="2026-09-24"
        archives={rows}
        onPick={() => {}}
        onClose={() => {}}
      />
    </Box>
  )
}

const meta = {
  title: 'Components/Archives/ArchivePickerMenu',
  component: Open,
} satisfies Meta<typeof Open>

export default meta

type Story = StoryObj<typeof meta>

export const LongPlanNames: Story = { args: { rows: archives } }

export const ShortNames: Story = {
  args: { rows: archives.slice(0, 2).map((row, i) => ({ ...row, name: `nightly-${i + 1}` })) },
}

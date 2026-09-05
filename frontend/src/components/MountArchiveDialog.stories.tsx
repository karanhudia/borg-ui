import { useState } from 'react'
import type { Meta, StoryObj } from '@storybook/react-vite'
import MountArchiveDialog from './MountArchiveDialog'
import type { Archive } from '../types'
import { getDefaultMountPoint } from '../utils/mountPoint'

// Borg 1 archive names are unique (here from a `{now:%Y-%m-%d-%s}` template),
// so the name alone identifies the archive.
const borg1Archive = {
  id: 'c3f9d2a17b4e',
  archive: 'nas-2026-09-04-1756951200',
  name: 'nas-2026-09-04-1756951200',
  start: '2026-09-04T02:00:00+00:00',
  time: '2026-09-04T02:00:00+00:00',
} as Archive

// Borg 2 series archives share one name; name plus timestamp identifies the
// archive for the user, while the id addresses it in the mount request.
const borg2SeriesArchive = {
  id: 'ab8f4e89cf1a891c12a1dcf2a3259b62ea765cccea6b373a9a9485fe5a942401',
  archive: 'nas',
  name: 'nas',
  start: '2026-09-04T02:00:00+00:00',
  time: '2026-09-04T02:00:00+00:00',
} as Archive

function MountDialogStory({
  archive,
  borgVersion,
  mounting: initialMounting = false,
}: {
  archive: Archive
  borgVersion: 1 | 2
  mounting?: boolean
}) {
  // Same pre-fill as the Archives page: sanitised name, plus the start time on Borg 2.
  const [mountPoint, setMountPoint] = useState(getDefaultMountPoint(archive, borgVersion))
  const [mounting, setMounting] = useState(initialMounting)
  return (
    <MountArchiveDialog
      open
      archive={archive}
      mountPoint={mountPoint}
      onMountPointChange={setMountPoint}
      onClose={() => {}}
      onConfirm={() => setMounting(true)}
      mounting={mounting}
    />
  )
}

const meta = {
  title: 'Components/MountArchiveDialog',
  component: MountArchiveDialog,
  parameters: { layout: 'fullscreen' },
  args: {
    open: true,
    archive: borg1Archive,
    mountPoint: getDefaultMountPoint(borg1Archive, 1),
    onMountPointChange: () => {},
    onClose: () => {},
    onConfirm: () => {},
  },
} satisfies Meta<typeof MountArchiveDialog>

export default meta
type Story = StoryObj<typeof meta>

export const Borg1Archive: Story = {
  render: () => <MountDialogStory archive={borg1Archive} borgVersion={1} />,
}

export const Borg2SeriesArchive: Story = {
  render: () => <MountDialogStory archive={borg2SeriesArchive} borgVersion={2} />,
}

export const Borg2SeriesArchiveMounting: Story = {
  render: () => <MountDialogStory archive={borg2SeriesArchive} borgVersion={2} />,
  play: async () => {
    await new Promise((resolve) => window.setTimeout(resolve, 0))
    // The dialog renders in a portal outside the story canvas.
    Array.from(document.querySelectorAll('button'))
      .find((button) => button.textContent?.trim() === 'Mount')
      ?.click()
  },
}

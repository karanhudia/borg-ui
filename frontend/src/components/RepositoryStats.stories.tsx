import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box } from '@mui/material'
import RepositoryStats from './RepositoryStats'
import {
  backfilledStorage,
  borg1Storage,
  borg2Storage,
  unknownStorage,
  withheldStorage,
} from './repositoryStatsFixtures'

const meta = {
  title: 'Components/RepositoryStats',
  component: RepositoryStats,
  parameters: {
    layout: 'padded',
  },
  render: (args) => (
    <Box sx={{ width: 960 }}>
      <RepositoryStats {...args} />
    </Box>
  ),
} satisfies Meta<typeof RepositoryStats>

export default meta

type Story = StoryObj<typeof meta>

export const Borg1Header: Story = {
  args: {
    variant: 'grid',
    storage: borg1Storage,
    borgVersion: 1,
    archiveCount: 21,
  },
}

export const Borg2Header: Story = {
  args: {
    variant: 'grid',
    storage: borg2Storage,
    borgVersion: 2,
    archiveCount: 35,
  },
}

export const HeaderUnknown: Story = {
  args: {
    variant: 'grid',
    storage: unknownStorage,
    borgVersion: 2,
    archiveCount: 0,
  },
}

export const HeaderIndexingAfterImport: Story = {
  args: {
    variant: 'grid',
    storage: unknownStorage,
    borgVersion: 2,
    archiveCount: 0,
    indexPendingKinds: ['stats', 'archive_sync', 'history_index'],
  },
}

export const HeaderSizeStillMeasuring: Story = {
  args: {
    variant: 'grid',
    storage: { ...borg2Storage, size_bytes: null, size_source: null, measured_at: null },
    borgVersion: 2,
    archiveCount: 35,
    indexPendingKinds: ['stats'],
  },
}

export const HeaderArchivesWithheld: Story = {
  args: {
    variant: 'grid',
    storage: withheldStorage,
    borgVersion: 2,
    archiveCount: 36,
  },
}

export const HeaderArchivesLoading: Story = {
  args: {
    variant: 'grid',
    storage: borg1Storage,
    borgVersion: 1,
    archiveCount: 0,
    archivesLoading: true,
  },
}

export const Borg1Detail: Story = {
  args: {
    variant: 'detail',
    storage: borg1Storage,
    borgVersion: 1,
  },
}

export const Borg2DetailWithCompact: Story = {
  args: {
    variant: 'detail',
    storage: borg2Storage,
    borgVersion: 2,
  },
}

export const DetailBackfilledSize: Story = {
  args: {
    variant: 'detail',
    storage: backfilledStorage,
    borgVersion: 1,
  },
}

export const DetailUnknown: Story = {
  args: {
    variant: 'detail',
    storage: unknownStorage,
    borgVersion: 1,
  },
}

export const DetailNotLoaded: Story = {
  args: {
    variant: 'detail',
    storage: undefined,
    borgVersion: 2,
  },
}

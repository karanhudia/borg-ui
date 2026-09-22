import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box } from '@mui/material'
import RepositoryStats from './RepositoryStats'
import {
  repositoryFigureStorage,
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

// The archive header: four tiles, the same on both Borg versions.

export const Borg1Header: Story = {
  args: {
    variant: 'grid',
    storage: borg1Storage,
    archiveCount: 21,
    freeSpaceHref: '/repositories/1/prune-preview',
  },
}

export const Borg2Header: Story = {
  args: { variant: 'grid', storage: borg2Storage, archiveCount: 36 },
}

export const HeaderUnknown: Story = {
  args: { variant: 'grid', storage: unknownStorage, archiveCount: 0 },
}

export const HeaderIndexingAfterImport: Story = {
  args: {
    variant: 'grid',
    storage: unknownStorage,
    archiveCount: 0,
    indexPendingKinds: ['stats', 'archive_sync', 'history_index'],
  },
}

export const HeaderSizeStillMeasuring: Story = {
  args: {
    variant: 'grid',
    storage: { ...borg2Storage, size_bytes: null, size_source: null, measured_at: null },
    archiveCount: 36,
    indexPendingKinds: ['stats'],
  },
}

export const HeaderArchivesWithheld: Story = {
  args: { variant: 'grid', storage: withheldStorage, archiveCount: 37 },
}

export const HeaderArchivesLoading: Story = {
  args: { variant: 'grid', storage: borg1Storage, archiveCount: 0, archivesLoading: true },
}

// The info dialog: three coloured cards, three outlined ones.

export const Borg1Detail: Story = {
  args: { variant: 'detail', storage: borg1Storage, archiveCount: 21 },
}

export const Borg2Detail: Story = {
  args: { variant: 'detail', storage: borg2Storage, archiveCount: 36 },
}

export const DetailBackfilledSize: Story = {
  args: { variant: 'detail', storage: backfilledStorage, archiveCount: 21 },
}

export const DetailUnknown: Story = {
  args: { variant: 'detail', storage: unknownStorage, archiveCount: 0 },
}

export const DetailIndexingAfterImport: Story = {
  args: {
    variant: 'detail',
    storage: unknownStorage,
    archiveCount: 0,
    indexPendingKinds: ['stats', 'archive_sync', 'history_index'],
  },
}

export const DetailNotLoaded: Story = {
  args: { variant: 'detail', storage: undefined, archiveCount: 21 },
}

// An archive row is still waiting for its info: the figure Borg reports
// for the whole repository answers, and the tile's hint says so.
export const DetailOriginalSizeFromBorg: Story = {
  args: { variant: 'detail', storage: repositoryFigureStorage, archiveCount: 21 },
}

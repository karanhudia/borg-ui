import { useEffect, type ComponentProps } from 'react'
import type { Meta, StoryObj } from '@storybook/react-vite'
import MockAdapter from 'axios-mock-adapter'
import { Box } from '@mui/material'
import ArchiveSearchField from './ArchiveSearchField'
import api from '../../services/api'
import { communitySystemInfo, proSystemInfo } from '../../services/remoteBackends/planStoryFixtures'

const results = [
  {
    path: 'local/Users/karanhudia/Downloads/cv_em.pdf',
    first_seen_archive_id: 3,
    first_seen: '2026-04-30T14:00:05Z',
    last_seen_archive_id: 9,
    last_seen: '2026-09-10T14:00:05Z',
    archive_count: 7,
    series: 'nightly',
    present_in_latest: false,
  },
  {
    path: 'local/Users/karanhudia/Documents/taxes/2025/return-final.pdf',
    first_seen_archive_id: 4,
    first_seen: '2026-05-02T02:00:00Z',
    last_seen_archive_id: 12,
    last_seen: '2026-09-13T02:00:00Z',
    archive_count: 31,
    series: 'nightly',
    present_in_latest: true,
  },
  {
    path: 'local/Users/karanhudia/Documents/scans/passport.png',
    first_seen_archive_id: 6,
    first_seen: '2026-06-11T02:00:00Z',
    last_seen_archive_id: 12,
    last_seen: '2026-09-13T02:00:00Z',
    archive_count: 18,
    series: 'nightly',
    present_in_latest: true,
  },
]

// The search route, the path history behind a picked result, and the series
// listing the history panel reads to say how many older archives lack it.
function useSearchMocks() {
  useEffect(() => {
    const mock = new MockAdapter(api, { onNoMatch: 'passthrough' })
    mock.onGet(/\/search/).reply(200, { query: 'pdf', results, truncated: false })
    mock.onGet(/\/history/).reply(200, {
      path: results[0].path,
      entries: [
        {
          archive_id: 9,
          archive_name: 'nightly-2026-09-10',
          series: 'nightly',
          start: '2026-09-10T14:00:05Z',
          change: 'modified',
          size_before: 240_000,
          size_after: 244_000,
        },
        {
          archive_id: 3,
          archive_name: 'nightly-2026-04-30',
          series: 'nightly',
          start: '2026-04-30T14:00:05Z',
          change: 'added',
          size_before: null,
          size_after: 240_000,
        },
      ],
      present: [{ series: 'nightly', from_archive_id: 3, to_archive_id: 9 }],
      coverage: { indexed: 12, total: 12, exhausted: 0, capability: 'available' },
    })
    mock.onGet(/\/archives(\?|$)/).reply(200, { archives: [], series: [] })
    return () => {
      mock.restore()
    }
  }, [])
}

function SearchFieldStory(args: ComponentProps<typeof ArchiveSearchField>) {
  useSearchMocks()
  return (
    <Box sx={{ width: 420, maxWidth: 'calc(100vw - 32px)' }}>
      <ArchiveSearchField {...args} />
    </Box>
  )
}

const meta = {
  title: 'Components/Archives/ArchiveSearchField',
  component: ArchiveSearchField,
  args: {
    repositoryId: 7,
    newestArchiveIdBySeries: { nightly: 12 },
    onRestorePath: () => {},
  },
  render: (args) => <SearchFieldStory {...args} />,
} satisfies Meta<typeof ArchiveSearchField>

export default meta

type Story = StoryObj<typeof meta>

export const Unlocked: Story = {
  parameters: {
    systemInfo: proSystemInfo,
  },
}

export const Locked: Story = {
  parameters: {
    systemInfo: communitySystemInfo,
  },
}

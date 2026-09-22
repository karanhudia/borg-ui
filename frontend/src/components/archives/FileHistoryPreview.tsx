import { Box } from '@mui/material'
import FileHistoryEntryLine from './FileHistoryEntryLine'
import type { HistoryEntry } from '../../types/archives'

// Example versions, never this path's own: on this plan the server sends the
// count and the window and nothing else. The sample says what the list looks
// like, the line above it says what is true.
const FIXTURE_ENTRIES: HistoryEntry[] = [
  {
    archive_id: 3,
    archive_name: 'example-2026-09-02',
    series: 'example',
    start: '2026-09-02T02:00:00Z',
    change: 'modified',
    size_before: 2_048_000,
    size_after: 2_113_000,
    mode_changed: false,
    owner_changed: false,
  },
  {
    archive_id: 2,
    archive_name: 'example-2026-06-01',
    series: 'example',
    start: '2026-06-01T02:00:00Z',
    change: 'modified',
    size_before: 1_890_000,
    size_after: 2_048_000,
    mode_changed: false,
    owner_changed: false,
  },
  {
    archive_id: 1,
    archive_name: 'example-2026-03-03',
    series: 'example',
    start: '2026-03-03T02:00:00Z',
    change: 'added',
    size_before: null,
    size_after: 1_890_000,
    mode_changed: false,
    owner_changed: false,
  },
]

export default function FileHistoryPreview() {
  return (
    <Box>
      {FIXTURE_ENTRIES.map((entry) => (
        <FileHistoryEntryLine
          key={entry.archive_id}
          entry={entry}
          isFirst={entry.change === 'added'}
          onRestore={() => {}}
        />
      ))}
    </Box>
  )
}

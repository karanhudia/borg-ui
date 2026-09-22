import { Box } from '@mui/material'
import ChangeRowLine from './ChangeRowLine'
import type { ChangeRow } from '../../types/archives'

const FIXTURE_ROWS: ChangeRow[] = [
  {
    path: 'home/example/docs/report.xlsx',
    change: 'modified',
    size_before: 374_000,
    size_after: 412_000,
    mode_changed: false,
    owner_changed: false,
    summary_count: null,
  },
  {
    path: 'home/example/photos/sample.jpg',
    change: 'added',
    size_before: null,
    size_after: 4_200_000,
    mode_changed: false,
    owner_changed: false,
    summary_count: null,
  },
  {
    path: 'home/example/archive/old-file.pdf',
    change: 'removed',
    size_before: 890_000,
    size_after: null,
    mode_changed: false,
    owner_changed: false,
    summary_count: null,
  },
  {
    path: 'var/log/example.log',
    change: 'modified',
    size_before: 1_000_000,
    size_after: 1_050_000,
    mode_changed: false,
    owner_changed: false,
    summary_count: null,
  },
  {
    path: 'home/example/projects',
    change: 'summary',
    size_before: null,
    size_after: null,
    mode_changed: false,
    owner_changed: false,
    summary_count: 14,
  },
  {
    path: 'etc/example.yaml',
    change: 'modified',
    size_before: 2_048,
    size_after: 2_112,
    mode_changed: true,
    owner_changed: false,
    summary_count: null,
  },
]

export default function ArchiveChangesPreview() {
  return (
    <Box sx={{ border: 1, borderColor: 'divider', borderRadius: 2, py: 0.5 }}>
      {FIXTURE_ROWS.map((row) => (
        <ChangeRowLine key={row.path} row={row} />
      ))}
    </Box>
  )
}

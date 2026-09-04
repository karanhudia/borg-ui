import { Box, Chip, Stack, Table, TableBody, TableCell, TableRow, Typography } from '@mui/material'
import { formatBytes } from '../../utils/dateUtils'
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
    <Box>
      <Stack direction="row" spacing={1} sx={{ mb: 1.5 }}>
        <Chip size="small" label="Added" />
        <Chip size="small" label="Removed" />
        <Chip size="small" label="Modified" />
      </Stack>
      <Table size="small">
        <TableBody>
          {FIXTURE_ROWS.map((row) => (
            <TableRow key={row.path}>
              <TableCell>{row.path}</TableCell>
              <TableCell>{row.change}</TableCell>
              <TableCell>
                {row.change === 'modified' && (
                  <Typography variant="body2">
                    {formatBytes(row.size_before)} → {formatBytes(row.size_after)}
                  </Typography>
                )}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </Box>
  )
}

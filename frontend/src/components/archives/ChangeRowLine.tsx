import { Box, Tooltip, Typography, useTheme } from '@mui/material'
import { Folder } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import ChangeBadge from './ChangeBadge'
import { changeColor } from './changeStyle'
import { splitPath } from './pathParts'
import { formatBytes } from '../../utils/dateUtils'
import type { ChangeRow } from '../../types/archives'

interface ChangeRowLineProps {
  row: ChangeRow
}

function signedDelta(before: number | null, after: number | null): string | null {
  if (before == null || after == null) return null
  const delta = after - before
  if (delta === 0) return null
  return `${delta > 0 ? '+' : '−'}${formatBytes(Math.abs(delta))}`
}

export default function ChangeRowLine({ row }: ChangeRowLineProps) {
  const { t } = useTranslation()
  const theme = useTheme()
  const { dir, name } = splitPath(row.path)
  const color = changeColor(theme, row.change)
  const delta = row.change === 'modified' ? signedDelta(row.size_before, row.size_after) : null

  return (
    <Box
      sx={{
        display: 'grid',
        gridTemplateColumns: { xs: '20px minmax(0, 1fr)', sm: '20px minmax(0, 1fr) auto' },
        columnGap: 1.5,
        // On a phone the sizes drop under the path; the badge stays on the
        // path's line rather than floating between the two.
        alignItems: { xs: 'start', sm: 'center' },
        py: 1,
        px: 1.5,
        // Square and flush: the list around the rows owns the frame, so a
        // rounded hover left a gap above the first row and below the last.
        '&:hover': { bgcolor: 'action.hover' },
      }}
    >
      {row.change === 'summary' ? (
        <Folder size={16} color={theme.palette.text.secondary} aria-hidden />
      ) : (
        <ChangeBadge change={row.change} />
      )}
      <Tooltip title={row.path} enterDelay={700} placement="top-start">
        <Typography
          variant="body2"
          noWrap
          data-path={row.path}
          sx={{
            fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
            fontSize: '0.8125rem',
          }}
        >
          {row.change === 'summary' ? (
            <>
              <Box component="span" sx={{ color: 'text.secondary' }}>
                {dir}
              </Box>
              {name}
              <Box component="span" sx={{ color: 'text.secondary', ml: 1 }}>
                {t('archives.changes.summaryRow', {
                  count: row.summary_count ?? 0,
                  path: '',
                }).trim()}
              </Box>
            </>
          ) : (
            <>
              <Box component="span" sx={{ color: 'text.secondary' }}>
                {dir}
              </Box>
              {name}
            </>
          )}
        </Typography>
      </Tooltip>
      {row.change !== 'summary' && (
        <Box
          sx={{
            display: 'flex',
            alignItems: 'baseline',
            gap: 1,
            justifyContent: { xs: 'flex-start', sm: 'flex-end' },
            gridColumn: { xs: '2', sm: 'auto' },
            fontVariantNumeric: 'tabular-nums',
            mt: { xs: 0.25, sm: 0 },
            '& .MuiTypography-root': { fontSize: { xs: '0.75rem', sm: '0.875rem' } },
          }}
        >
          {row.change === 'modified' ? (
            <>
              <Typography variant="body2" sx={{ color: 'text.secondary' }}>
                {formatBytes(row.size_before)} → {formatBytes(row.size_after)}
              </Typography>
              {delta && (
                <Typography variant="body2" sx={{ color, fontWeight: 600 }}>
                  {delta}
                </Typography>
              )}
            </>
          ) : (
            <Typography variant="body2" sx={{ color, fontWeight: 600 }}>
              {row.change === 'added' ? '+' : '−'}
              {formatBytes(row.size_after ?? row.size_before)}
            </Typography>
          )}
        </Box>
      )}
    </Box>
  )
}

import { Box, Typography, useTheme } from '@mui/material'
import { Folder } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import ChangeBadge from './ChangeBadge'
import { changeColor } from './changeStyle'
import { formatBytes } from '../../utils/dateUtils'
import type { ChangeRow } from '../../types/archives'

interface ChangeRowLineProps {
  row: ChangeRow
}

function splitPath(path: string): { dir: string; name: string } {
  const index = path.lastIndexOf('/')
  if (index < 0) return { dir: '', name: path }
  return { dir: path.slice(0, index + 1), name: path.slice(index + 1) }
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
        alignItems: 'center',
        py: 1,
        px: 1.5,
        borderRadius: 1.5,
        '&:hover': { bgcolor: 'action.hover' },
      }}
    >
      {row.change === 'summary' ? (
        <Folder size={16} color={theme.palette.text.secondary} aria-hidden />
      ) : (
        <ChangeBadge change={row.change} />
      )}
      <Typography
        variant="body2"
        noWrap
        title={row.path}
        sx={{ fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace', fontSize: '0.8125rem' }}
      >
        {row.change === 'summary' ? (
          <>
            <Box component="span" sx={{ color: 'text.secondary' }}>
              {dir}
            </Box>
            {name}
            <Box component="span" sx={{ color: 'text.secondary', ml: 1 }}>
              {t('archives.changes.summaryRow', { count: row.summary_count ?? 0, path: '' }).trim()}
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
      {row.change !== 'summary' && (
        <Box
          sx={{
            display: 'flex',
            alignItems: 'baseline',
            gap: 1,
            justifyContent: 'flex-end',
            gridColumn: { xs: '2', sm: 'auto' },
            fontVariantNumeric: 'tabular-nums',
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

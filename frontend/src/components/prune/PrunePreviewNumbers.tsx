import { useTranslation } from 'react-i18next'
import { Box, Paper, Typography } from '@mui/material'
import { formatBytes } from '../../utils/dateUtils'

export interface PrunePreviewNumbersProps {
  deletedCount: number
  keptCount: number
  freedAtLeast: number
  footprintBefore: number | null
  footprintAfterAtMost: number | null
}

function Tile({
  testId,
  label,
  value,
  sub,
}: {
  testId: string
  label: string
  value: string
  sub?: string
}) {
  return (
    <Paper variant="outlined" sx={{ p: 1.5 }} data-testid={testId}>
      <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
        {label}
      </Typography>
      <Typography variant="h6" sx={{ fontWeight: 700 }}>
        {value}
      </Typography>
      {sub && (
        <Typography variant="caption" color="text.secondary">
          {sub}
        </Typography>
      )}
    </Paper>
  )
}

export default function PrunePreviewNumbers({
  deletedCount,
  keptCount,
  freedAtLeast,
  footprintBefore,
  footprintAfterAtMost,
}: PrunePreviewNumbersProps) {
  const { t } = useTranslation()

  return (
    <Box
      sx={{
        display: 'grid',
        gridTemplateColumns: { xs: 'repeat(2, 1fr)', sm: 'repeat(4, 1fr)' },
        gap: 1.5,
      }}
    >
      <Tile
        testId="prune-preview-deleted"
        label={t('prunePreview.deleted')}
        value={String(deletedCount)}
        sub={t('prunePreview.kept', { count: keptCount })}
      />
      <Tile
        testId="prune-preview-freed"
        label={t('prunePreview.freed')}
        value={t('prunePreview.atLeast', { size: formatBytes(freedAtLeast) })}
        sub={t('prunePreview.freedSub')}
      />
      <Tile
        testId="prune-preview-before"
        label={t('prunePreview.before')}
        value={
          footprintBefore != null ? formatBytes(footprintBefore) : t('prunePreview.notMeasured')
        }
      />
      <Tile
        testId="prune-preview-after"
        label={t('prunePreview.after')}
        value={
          footprintAfterAtMost != null
            ? formatBytes(footprintAfterAtMost)
            : t('prunePreview.notMeasured')
        }
        sub={footprintAfterAtMost != null ? t('prunePreview.atMost') : undefined}
      />
    </Box>
  )
}

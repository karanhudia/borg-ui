import { useTranslation } from 'react-i18next'
import { Box, Stack, Typography, alpha, useTheme } from '@mui/material'
import { Archive, Database, Shrink, Trash2 } from 'lucide-react'
import { formatBytes } from '../../utils/dateUtils'
import TintedTile from '../shared/TintedTile'

export interface PrunePreviewNumbersProps {
  deletedCount: number
  keptCount: number
  /** Borg's per-archive unique sum: the floor of the storage freed.
   *  The logical size of the files that go is deliberately not here: it is
   *  file data, not disk space, and pairing the two read as a range from
   *  one to the other. It has its own panel, which says what it means. */
  freedAtLeast: number
  footprintBefore: number | null
  footprintAfterAtMost: number | null
}

/** One bar for the whole verdict: what stays in green, what goes in red,
 * in proportion. The four figures sit under it in the same tones. */
export default function PrunePreviewNumbers({
  deletedCount,
  keptCount,
  freedAtLeast,
  footprintBefore,
  footprintAfterAtMost,
}: PrunePreviewNumbersProps) {
  const { t } = useTranslation()
  const theme = useTheme()
  const after = footprintAfterAtMost
  const total = deletedCount + keptCount
  const deletedShare = total > 0 ? (deletedCount / total) * 100 : 0

  return (
    <Box>
      <Stack
        direction="row"
        sx={{ justifyContent: 'space-between', alignItems: 'baseline', mb: 0.75 }}
      >
        <Typography variant="body2" sx={{ fontWeight: 700, color: 'success.main' }}>
          {t('prunePreview.kept', { count: keptCount })}
        </Typography>
        <Typography variant="body2" sx={{ fontWeight: 700, color: 'error.main' }}>
          {t('prunePreview.deletedCount', { count: deletedCount })}
        </Typography>
      </Stack>
      <Box
        data-testid="prune-preview-verdict-bar"
        role="img"
        aria-label={`${t('prunePreview.kept', { count: keptCount })}, ${t(
          'prunePreview.deletedCount',
          { count: deletedCount }
        )}`}
        sx={{
          display: 'flex',
          height: 12,
          borderRadius: 6,
          overflow: 'hidden',
          bgcolor: alpha(theme.palette.text.primary, 0.08),
          mb: 2,
        }}
      >
        <Box
          sx={{
            flex: `0 0 ${100 - deletedShare}%`,
            bgcolor: theme.palette.success.main,
            transition: 'flex-basis 300ms ease',
          }}
        />
        <Box
          sx={{
            flex: `0 0 ${deletedShare}%`,
            bgcolor: theme.palette.error.main,
            transition: 'flex-basis 300ms ease',
          }}
        />
      </Box>

      <Box
        sx={{
          display: 'grid',
          gridTemplateColumns: { xs: 'repeat(2, 1fr)', md: 'repeat(4, 1fr)' },
          gap: 1.5,
        }}
      >
        <TintedTile
          testId="prune-preview-deleted"
          label={t('prunePreview.deleted')}
          value={String(deletedCount)}
          sub={t('prunePreview.kept', { count: keptCount })}
          tone="error"
          icon={Trash2}
        />
        <TintedTile
          testId="prune-preview-freed"
          label={t('prunePreview.freed')}
          value={t('prunePreview.atLeast', { size: formatBytes(freedAtLeast) })}
          sub={t('prunePreview.freedSub')}
          tone="success"
          icon={Shrink}
        />
        <TintedTile
          testId="prune-preview-before"
          label={t('prunePreview.before')}
          value={
            footprintBefore != null ? formatBytes(footprintBefore) : t('prunePreview.notMeasured')
          }
          tone="info"
          icon={Database}
          muted={footprintBefore == null}
        />
        <TintedTile
          testId="prune-preview-after"
          label={t('prunePreview.after')}
          value={after != null ? formatBytes(after) : t('prunePreview.notMeasured')}
          sub={after != null ? t('prunePreview.atMost') : undefined}
          tone="info"
          icon={Archive}
          muted={after == null}
        />
      </Box>
    </Box>
  )
}

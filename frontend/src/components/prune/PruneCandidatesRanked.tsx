import { useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Box, Button, ButtonBase, Chip, Stack, Typography, alpha, useTheme } from '@mui/material'
import { formatBytes } from '../../utils/dateUtils'
import type { PrunePreviewArchive } from '../../types/archives'

export interface PruneCandidatesRankedProps {
  archives: PrunePreviewArchive[]
  partialMeasure: boolean
  onOpen: (archiveId: number) => void
}

const VISIBLE_CAP = 25

const rowSx = { display: 'flex', alignItems: 'center', gap: 1.5, width: '100%', px: 0.5 }

// A verdict line the index has no row for (not yet listed) has no archive
// page to open, so it is plain text, not a button.
function Row({
  archiveId,
  onOpen,
  children,
}: {
  archiveId: number | null
  onOpen: (archiveId: number) => void
  children: ReactNode
}) {
  if (archiveId == null) return <Box sx={rowSx}>{children}</Box>
  return (
    <ButtonBase
      onClick={() => onOpen(archiveId)}
      sx={{ ...rowSx, textAlign: 'left', borderRadius: 1 }}
    >
      {children}
    </ButtonBase>
  )
}

export default function PruneCandidatesRanked({
  archives,
  partialMeasure,
  onOpen,
}: PruneCandidatesRankedProps) {
  const { t } = useTranslation()
  const theme = useTheme()
  const [showAll, setShowAll] = useState(false)

  const deleted = archives
    .filter((a) => a.verdict === 'deleted')
    .sort((a, b) => (b.deduplicated_size ?? -1) - (a.deduplicated_size ?? -1))
  const max = Math.max(0, ...deleted.map((a) => a.deduplicated_size ?? 0))
  const visible = showAll ? deleted : deleted.slice(0, VISIBLE_CAP)

  return (
    <Box>
      <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
        {t('prunePreview.rankedTitle')}
      </Typography>
      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1.5 }}>
        {partialMeasure
          ? t('prunePreview.remeasuredPartial', { cap: 50, count: deleted.length })
          : t('prunePreview.remeasured', { count: deleted.length })}
      </Typography>
      <Stack spacing={0.75}>
        {visible.map((a) => {
          const size = a.deduplicated_size
          const width = size != null && max > 0 ? Math.max(2, (size / max) * 100) : 0
          return (
            <Row key={a.borg_id} archiveId={a.id} onOpen={onOpen}>
              <Typography
                variant="body2"
                sx={{
                  width: 180,
                  flexShrink: 0,
                  fontFamily: 'monospace',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                }}
                title={a.name}
              >
                {a.name}
              </Typography>
              <Box sx={{ flex: 1, position: 'relative', height: 8 }}>
                <Box
                  sx={{
                    position: 'absolute',
                    inset: 0,
                    borderRadius: 1,
                    bgcolor: alpha(theme.palette.error.main, 0.12),
                  }}
                />
                <Box
                  sx={{
                    position: 'absolute',
                    inset: 0,
                    width: `${width}%`,
                    borderRadius: 1,
                    bgcolor: alpha(theme.palette.error.main, 0.85),
                  }}
                />
              </Box>
              {a.stale && (
                <Chip size="small" label={t('prunePreview.remeasuring')} sx={{ flexShrink: 0 }} />
              )}
              <Typography
                variant="body2"
                sx={{ width: 88, flexShrink: 0, textAlign: 'right', fontWeight: 600 }}
              >
                {size != null ? formatBytes(size) : t('prunePreview.notMeasured')}
              </Typography>
            </Row>
          )
        })}
      </Stack>
      {!showAll && deleted.length > VISIBLE_CAP && (
        <Button size="small" onClick={() => setShowAll(true)} sx={{ mt: 1 }}>
          {t('prunePreview.showAll', { count: deleted.length })}
        </Button>
      )}
    </Box>
  )
}

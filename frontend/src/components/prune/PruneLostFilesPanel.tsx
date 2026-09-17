import { useTranslation } from 'react-i18next'
import { Link as RouterLink } from 'react-router-dom'
import {
  Alert,
  Box,
  Chip,
  Link,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
} from '@mui/material'
import { PLAN_LABEL } from '../../core/features'
import { formatBytes } from '../../utils/dateUtils'
import type { PruneLostFiles } from '../../types/archives'

export interface PruneLostFilesPanelProps {
  repositoryId: number
  lost: PruneLostFiles
}

export default function PruneLostFilesPanel({ repositoryId, lost }: PruneLostFilesPanelProps) {
  const { t } = useTranslation()

  if (!lost.available) {
    const reason =
      lost.capability === 'agent_unsupported'
        ? t('prunePreview.lostAgent')
        : t('prunePreview.lostUnavailable')
    return (
      <Box>
        <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 1 }}>
          {t('prunePreview.lostTitle')}
          <Chip size="small" label={PLAN_LABEL.pro} sx={{ ml: 1 }} />
        </Typography>
        <Typography variant="body2" color="text.secondary">
          {reason}
        </Typography>
      </Box>
    )
  }

  const totalCount = lost.total_count ?? 0
  const totalSize = lost.total_size ?? 0
  const top = lost.top ?? []
  const byFolder = lost.by_folder ?? []

  return (
    <Box>
      <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 1 }}>
        {t('prunePreview.lostTitle')}
        <Chip size="small" label={PLAN_LABEL.pro} sx={{ ml: 1 }} />
      </Typography>

      {lost.incomplete && (
        <Alert severity="warning" sx={{ mb: 1.5 }}>
          {t('prunePreview.warnIncomplete', { count: lost.unindexed_archive_ids?.length ?? 0 })}
        </Alert>
      )}

      {totalCount === 0 ? (
        <Typography variant="body2" color="text.secondary">
          {t('prunePreview.lostNone')}
        </Typography>
      ) : (
        <>
          <Typography variant="body2" sx={{ mb: 1.5 }}>
            {t('prunePreview.lostSummary', { count: totalCount, size: formatBytes(totalSize) })}
          </Typography>

          {byFolder.length > 0 && (
            <Stack direction="row" spacing={1} sx={{ mb: 1.5, flexWrap: 'wrap', gap: 1 }}>
              {byFolder.map((f) => (
                <Chip
                  key={f.folder}
                  size="small"
                  variant="outlined"
                  label={`${f.folder} (${f.count}, ${formatBytes(f.size)})`}
                />
              ))}
            </Stack>
          )}

          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>{t('prunePreview.lostPath')}</TableCell>
                <TableCell align="right">{t('prunePreview.lostSize')}</TableCell>
                <TableCell>{t('prunePreview.lostHeldBy')}</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {top.map((f) => (
                <TableRow key={f.path}>
                  <TableCell
                    sx={{
                      maxWidth: 260,
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                      fontFamily: 'monospace',
                    }}
                    title={f.path}
                  >
                    {f.path}
                  </TableCell>
                  <TableCell align="right">{f.size != null ? formatBytes(f.size) : '–'}</TableCell>
                  <TableCell>
                    {f.last_held_archive_id != null ? (
                      <Link
                        component={RouterLink}
                        to={`/archives/${repositoryId}/${f.last_held_archive_id}`}
                      >
                        {f.last_held_archive_name}
                      </Link>
                    ) : (
                      '–'
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          {totalCount > top.length && (
            <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>
              {t('prunePreview.lostMore', { count: totalCount - top.length })}
            </Typography>
          )}
        </>
      )}
    </Box>
  )
}

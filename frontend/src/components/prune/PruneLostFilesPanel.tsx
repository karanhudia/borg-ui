import { useState } from 'react'
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
  alpha,
  useTheme,
} from '@mui/material'
import { CheckCircle2, FileX } from 'lucide-react'
import { PLAN_LABEL } from '../../core/features'
import { formatBytes } from '../../utils/dateUtils'
import SearchBox from '../shared/SearchBox'
import UpgradePrompt from '../UpgradePrompt'
import type { PruneLostFiles } from '../../types/archives'
import { tintChipSx } from '../shared/tones'

function Header({
  tone,
  showPlanChip = true,
}: {
  tone: 'warning' | 'success' | 'primary'
  showPlanChip?: boolean
}) {
  const { t } = useTranslation()
  const theme = useTheme()
  const color = theme.palette[tone].main
  return (
    <Stack direction="row" sx={{ alignItems: 'center', gap: 1.5, mb: 1.5 }}>
      <Box
        sx={{
          width: 36,
          height: 36,
          borderRadius: 1.5,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color,
          bgcolor: alpha(color, theme.palette.mode === 'dark' ? 0.16 : 0.1),
          flexShrink: 0,
        }}
      >
        {tone === 'success' ? <CheckCircle2 size={20} /> : <FileX size={20} />}
      </Box>
      <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
        {t('prunePreview.lostTitle')}
        {showPlanChip && (
          <Chip
            size="small"
            label={PLAN_LABEL.pro}
            sx={{ ml: 1, ...tintChipSx(theme, 'primary') }}
          />
        )}
      </Typography>
    </Stack>
  )
}

export interface PruneLostFilesPanelProps {
  repositoryId: number
  lost: PruneLostFiles
}

export default function PruneLostFilesPanel({ repositoryId, lost }: PruneLostFilesPanelProps) {
  const { t } = useTranslation()
  const theme = useTheme()
  const [filter, setFilter] = useState('')

  if (!lost.available) {
    const reason =
      lost.capability === 'agent_unsupported'
        ? t('prunePreview.lostAgent')
        : t('prunePreview.lostUnavailable')
    return (
      <Box>
        {/* No plan chip: what is missing here is the index, and neither
            reason below is one an upgrade fixes. */}
        <Header tone="primary" showPlanChip={false} />
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
  // The count is the last warning before an irreversible delete, so every
  // plan reads it. Which files they are is the Pro part.
  const locked = lost.detail_locked === true
  // The largest rows the server sent, narrowed by path; the rows beyond
  // the cap are not here to search.
  const needle = filter.trim().toLowerCase()
  const rows = needle ? top.filter((f) => f.path.toLowerCase().includes(needle)) : top

  return (
    <Box>
      <Header
        tone={totalCount === 0 && !lost.incomplete ? 'success' : 'warning'}
        showPlanChip={locked}
      />

      {lost.incomplete && (
        <Alert severity="warning" sx={{ mb: 1.5 }}>
          {t('prunePreview.warnIncomplete', { count: lost.unindexed_archive_ids?.length ?? 0 })}
        </Alert>
      )}

      {totalCount === 0 ? (
        <Typography
          variant="body2"
          sx={{
            p: 1.5,
            borderRadius: 1.5,
            color: lost.incomplete ? 'text.secondary' : 'success.main',
            bgcolor: alpha(
              lost.incomplete ? theme.palette.text.primary : theme.palette.success.main,
              theme.palette.mode === 'dark' ? 0.08 : 0.06
            ),
          }}
        >
          {lost.incomplete ? t('prunePreview.lostUnknown') : t('prunePreview.lostNone')}
        </Typography>
      ) : (
        <>
          <Typography variant="body2" sx={{ mb: 1.5, fontWeight: 600, color: 'warning.main' }}>
            {t('prunePreview.lostSummary', { count: totalCount, size: formatBytes(totalSize) })}
          </Typography>

          {locked && (
            <UpgradePrompt
              compact
              requiredPlan="pro"
              message={t('prunePreview.lostLocked', { count: totalCount })}
              feature="archive_history"
            />
          )}

          {!locked && byFolder.length > 0 && (
            <Stack direction="row" spacing={1} sx={{ mb: 1.5, flexWrap: 'wrap', gap: 1 }}>
              {byFolder.map((f) => (
                <Chip
                  key={f.folder}
                  size="small"
                  sx={{ ...tintChipSx(theme, 'warning'), fontFamily: 'monospace' }}
                  label={`${f.folder} (${f.count}, ${formatBytes(f.size)})`}
                />
              ))}
            </Stack>
          )}

          {!locked && (
            <>
              <SearchBox
                value={filter}
                onChange={setFilter}
                placeholder={t('prunePreview.lostSearch')}
                sx={{ mb: 1.5 }}
              />
              <Box
                sx={{
                  maxHeight: 420,
                  overflowY: 'auto',
                  border: '1px solid',
                  borderColor: 'divider',
                  borderRadius: 1.5,
                }}
              >
                <Table size="small" stickyHeader>
                  <TableHead>
                    <TableRow>
                      <TableCell>{t('prunePreview.lostPath')}</TableCell>
                      <TableCell align="right">{t('prunePreview.lostSize')}</TableCell>
                      <TableCell>{t('prunePreview.lostHeldBy')}</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {rows.map((f) => (
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
                        <TableCell align="right" sx={{ fontWeight: 600, color: 'warning.main' }}>
                          {f.size != null ? formatBytes(f.size) : '–'}
                        </TableCell>
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
                    {rows.length === 0 && (
                      <TableRow>
                        <TableCell colSpan={3} sx={{ color: 'text.secondary' }}>
                          {t('prunePreview.lostNoMatch')}
                        </TableCell>
                      </TableRow>
                    )}
                  </TableBody>
                </Table>
              </Box>
              {totalCount > top.length && (
                <Typography
                  variant="caption"
                  color="text.secondary"
                  sx={{ display: 'block', mt: 1 }}
                >
                  {t('prunePreview.lostMore', { count: totalCount - top.length })}
                </Typography>
              )}
            </>
          )}
        </>
      )}
    </Box>
  )
}

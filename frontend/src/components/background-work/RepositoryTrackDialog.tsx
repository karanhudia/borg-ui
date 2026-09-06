import { useState } from 'react'
import {
  Alert,
  Box,
  Typography,
  Button,
  Stack,
  DialogContent,
  DialogActions,
  Link as MuiLink,
  useTheme,
} from '@mui/material'
import { AlertTriangle, CheckCircle2, RotateCw, Scissors } from 'lucide-react'
import { Link as RouterLink } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useQuery } from '@tanstack/react-query'
import { format } from 'date-fns'
import ResponsiveDialog from '../shared/ResponsiveDialog'
import CategoryToken from '../CategoryToken'
import RebuildStagePicker from './RebuildStagePicker'
import { REBUILD_STAGES } from './repositoryTrack'
import { archivesAPI, operationsAPI } from '../../services/api'
import { usePlan } from '../../hooks/usePlan'
import { parseBackendDate } from '../../utils/dateUtils'
import type { HubArchive, OperationItem, RebuildStage } from '../../types/operations'

interface RepositoryTrackDialogProps {
  open: boolean
  onClose: () => void
  repositoryId: number
  repositoryName: string
  operations: OperationItem[]
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <Typography
      variant="overline"
      sx={{ display: 'block', color: 'text.secondary', letterSpacing: 0.6, mb: 1 }}
    >
      {children}
    </Typography>
  )
}

function ArchiveList({
  title,
  icon,
  color,
  archives,
  detail,
}: {
  title: string
  icon: React.ReactNode
  color: string
  archives: HubArchive[]
  detail: (archive: HubArchive) => string
}) {
  return (
    <Box>
      <Typography
        variant="subtitle2"
        sx={{ display: 'flex', alignItems: 'center', gap: 0.75, color, mb: 0.5 }}
      >
        {icon}
        {title}
      </Typography>
      <Stack spacing={0.5}>
        {archives.map((archive) => (
          <Box
            key={archive.id}
            sx={{ display: 'flex', alignItems: 'baseline', gap: 1.5, minWidth: 0 }}
          >
            <Typography variant="body2" noWrap sx={{ flex: 1, minWidth: 0 }}>
              {archive.name}
            </Typography>
            <Typography variant="caption" sx={{ color: 'text.secondary', flexShrink: 0 }}>
              {format(parseBackendDate(archive.start), 'PP')}
            </Typography>
            <Typography
              variant="caption"
              sx={{ color: 'text.secondary', flexShrink: 0, fontVariantNumeric: 'tabular-nums' }}
            >
              {detail(archive)}
            </Typography>
          </Box>
        ))}
      </Stack>
    </Box>
  )
}

// One repository's derived data up close: the run in progress, the
// archives whose file history needs attention, and the rebuild choice as
// the three stage cards. A bottom sheet under the md breakpoint, a wide
// dialog above it.
export default function RepositoryTrackDialog({
  open,
  onClose,
  repositoryId,
  repositoryName,
  operations,
}: RepositoryTrackDialogProps) {
  const { t } = useTranslation()
  const theme = useTheme()
  const [stage, setStage] = useState<RebuildStage>('archives')
  const [submitting, setSubmitting] = useState(false)
  const [failed, setFailed] = useState(false)
  const { can } = usePlan()
  const historyLocked = !can('archive_history')

  const { data: detail } = useQuery({
    queryKey: ['operations-repository-detail', repositoryId],
    queryFn: () => operationsAPI.getRepositoryDetail(repositoryId).then((r) => r.data),
    enabled: open,
  })

  const handleRebuild = async () => {
    setSubmitting(true)
    setFailed(false)
    try {
      await archivesAPI.rebuild(repositoryId, stage)
      onClose()
    } catch {
      // A rebuild can be refused (repository permissions, or the
      // `archive_history` plan gate), and closing on failure would read as
      // success. Keep the dialog open and say so.
      setFailed(true)
    } finally {
      setSubmitting(false)
    }
  }

  const problems =
    detail != null && (detail.failed_archives.length > 0 || detail.truncated_archives.length > 0)

  const startIndex = REBUILD_STAGES.indexOf(stage)
  const rebuilt = REBUILD_STAGES.slice(startIndex).filter(
    (s) => !(s === 'history' && historyLocked)
  )
  // "Everything" only when every stage really runs; on Community the
  // history stage is locked, so the list is spelled out instead.
  const summary =
    rebuilt.length === REBUILD_STAGES.length
      ? t('operations.background.rebuildSummaryAll', { repository: repositoryName })
      : t('operations.background.rebuildSummary', {
          repository: repositoryName,
          stages: rebuilt
            .map((s) => t(`operations.background.stages.${s}.title`).toLowerCase())
            .join(t('operations.background.stageJoin')),
        })

  const footer = (
    <DialogActions sx={{ px: 3, py: 2 }}>
      <Button onClick={onClose}>{t('common.buttons.cancel')}</Button>
      <Button
        variant="contained"
        disableElevation
        disabled={submitting}
        startIcon={<RotateCw size={16} />}
        onClick={handleRebuild}
      >
        {t('operations.background.rebuildAction')}
      </Button>
    </DialogActions>
  )

  return (
    <ResponsiveDialog open={open} onClose={onClose} maxWidth="md" fullWidth footer={footer}>
      <DialogContent sx={{ pt: 3 }}>
        <Stack direction="row" spacing={2} sx={{ alignItems: 'baseline', mb: 2 }}>
          <Typography variant="h6" sx={{ flex: 1, minWidth: 0 }} noWrap>
            {repositoryName}
          </Typography>
          <MuiLink
            component={RouterLink}
            to={`/activity?repository_id=${repositoryId}&category=index`}
            variant="body2"
            sx={{ flexShrink: 0 }}
          >
            {t('operations.background.hub.viewIndexRuns')}
          </MuiLink>
        </Stack>

        <Stack spacing={3}>
          {operations.length > 0 && (
            <Box>
              <SectionTitle>{t('operations.background.currentRun')}</SectionTitle>
              <Stack spacing={1}>
                {operations.map((op) => (
                  <Box key={op.id} sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                    <CategoryToken category={op.category} />
                    <Typography variant="body2">{t(`operations.kind.${op.kind}`)}</Typography>
                    <Typography variant="caption" color="text.secondary" sx={{ ml: 'auto' }}>
                      {t(`operations.status.${op.status}`)}
                    </Typography>
                  </Box>
                ))}
              </Stack>
            </Box>
          )}

          {detail && (
            <Box>
              <SectionTitle>{t('operations.background.stage.history')}</SectionTitle>
              <Box sx={{ p: 2, borderRadius: 2, border: `1px solid ${theme.palette.divider}` }}>
                {problems ? (
                  <Stack spacing={2}>
                    {detail.failed_archives.length > 0 && (
                      <ArchiveList
                        title={t('operations.background.hub.detailFailedTitle')}
                        icon={<AlertTriangle size={14} />}
                        color={theme.palette.error.main}
                        archives={detail.failed_archives}
                        detail={(a) =>
                          t('operations.background.hub.detailAttempts', {
                            count: a.history_attempts,
                          })
                        }
                      />
                    )}
                    {detail.truncated_archives.length > 0 && (
                      <ArchiveList
                        title={t('operations.background.hub.detailTruncatedTitle')}
                        icon={<Scissors size={14} />}
                        color={theme.palette.warning.main}
                        archives={detail.truncated_archives}
                        detail={(a) =>
                          t('operations.background.hub.historyRows', {
                            count: a.history_rows ?? 0,
                          })
                        }
                      />
                    )}
                    <Typography variant="caption" sx={{ color: 'text.secondary' }}>
                      {t('operations.background.hub.detailHint')}
                    </Typography>
                  </Stack>
                ) : (
                  <Typography
                    variant="body2"
                    sx={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 0.75,
                      color: theme.palette.success.main,
                    }}
                  >
                    <CheckCircle2 size={14} />
                    {t('operations.background.hub.detailAllIndexed')}
                  </Typography>
                )}
              </Box>
            </Box>
          )}

          <Box>
            <SectionTitle>{t('operations.background.rebuildTitle')}</SectionTitle>
            <Typography variant="body2" sx={{ color: 'text.secondary', mb: 1.5 }}>
              {t('operations.background.rebuildMenuHint')}
            </Typography>
            <RebuildStagePicker value={stage} onChange={setStage} historyLocked={historyLocked} />
            <Typography variant="body2" sx={{ color: 'text.secondary', mt: 1.5 }}>
              {summary}
            </Typography>
            {failed && (
              <Alert severity="error" sx={{ mt: 1.5 }}>
                {t('operations.background.rebuildFailed')}
              </Alert>
            )}
          </Box>
        </Stack>
      </DialogContent>
    </ResponsiveDialog>
  )
}

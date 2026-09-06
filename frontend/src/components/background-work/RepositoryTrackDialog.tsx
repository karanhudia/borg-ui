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
import { AlertTriangle, CheckCircle2, Scissors } from 'lucide-react'
import { Link as RouterLink } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useQuery } from '@tanstack/react-query'
import { format } from 'date-fns'
import ResponsiveDialog from '../shared/ResponsiveDialog'
import RichSelect from '../shared/RichSelect'
import CategoryToken from '../CategoryToken'
import { archivesAPI, operationsAPI } from '../../services/api'
import { parseBackendDate } from '../../utils/dateUtils'
import type { HubArchive, OperationItem, RebuildStage } from '../../types/operations'

interface RepositoryTrackDialogProps {
  open: boolean
  onClose: () => void
  repositoryId: number
  repositoryName: string
  operations: OperationItem[]
}

const REBUILD_STAGES: RebuildStage[] = ['stats', 'archives', 'history']

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

export default function RepositoryTrackDialog({
  open,
  onClose,
  repositoryId,
  repositoryName,
  operations,
}: RepositoryTrackDialogProps) {
  const { t } = useTranslation()
  const theme = useTheme()
  const [stage, setStage] = useState<RebuildStage>('stats')
  const [submitting, setSubmitting] = useState(false)
  const [failed, setFailed] = useState(false)

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

  return (
    <ResponsiveDialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogContent sx={{ pt: 3 }}>
        <Stack direction="row" spacing={2} sx={{ alignItems: 'baseline', mb: 1 }}>
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
        {operations.length > 0 && (
          <Stack spacing={1.5} sx={{ py: 1 }}>
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
        )}

        {detail && (
          <Box
            sx={{
              mt: 1.5,
              p: 2,
              borderRadius: 2,
              border: `1px solid ${theme.palette.divider}`,
            }}
          >
            {problems ? (
              <Stack spacing={2}>
                {detail.failed_archives.length > 0 && (
                  <ArchiveList
                    title={t('operations.background.hub.detailFailedTitle')}
                    icon={<AlertTriangle size={14} />}
                    color={theme.palette.error.main}
                    archives={detail.failed_archives}
                    detail={(a) =>
                      t('operations.background.hub.detailAttempts', { count: a.history_attempts })
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
                      t('operations.background.hub.historyRows', { count: a.history_rows ?? 0 })
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
        )}

        {failed && (
          <Alert severity="error" sx={{ mt: 1 }}>
            {t('operations.background.rebuildFailed')}
          </Alert>
        )}
        <Box sx={{ display: 'flex', alignItems: 'flex-end', gap: 1, pt: 2 }}>
          <RichSelect
            value={stage}
            onChange={(value) => setStage(value as RebuildStage)}
            label={t('operations.background.rebuildFrom')}
            options={REBUILD_STAGES.map((s) => ({
              value: s,
              primary: t(`operations.background.rebuildStage.${s}`),
            }))}
          />
        </Box>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>{t('common.buttons.cancel')}</Button>
        <Button variant="outlined" disabled={submitting} onClick={handleRebuild}>
          {t('operations.background.rebuildFrom')}
        </Button>
      </DialogActions>
    </ResponsiveDialog>
  )
}

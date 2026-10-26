import { useState } from 'react'
import { Box, Chip, Tooltip, Typography, alpha } from '@mui/material'
import { AlertTriangle } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import type { Repository } from '../types'
import { formatDateTimeFull } from '../utils/dateUtils'
import ErrorDetailsDialog from './ErrorDetailsDialog'

type SyncWarning = NonNullable<Repository['archive_sync_warning']>

/** A compact status beside the version; diagnostics are disclosed on demand. */
export default function RepositorySyncWarning({ warning }: { warning: SyncWarning }) {
  const { t } = useTranslation()
  const [detailsOpen, setDetailsOpen] = useState(false)
  const lastSync = warning.last_success_at
    ? t('repositoryCard.archiveSyncWarning.lastSuccess', {
        when: formatDateTimeFull(warning.last_success_at),
      })
    : t('repositoryCard.archiveSyncWarning.neverSynced')

  return (
    <>
      <Tooltip
        arrow
        describeChild
        title={
          <Box>
            <Typography variant="caption" sx={{ display: 'block' }}>
              {t('repositoryCard.archiveSyncWarning.description')}
            </Typography>
            <Typography variant="caption" sx={{ display: 'block', mt: 0.25 }}>
              {lastSync}
            </Typography>
          </Box>
        }
      >
        <Chip
          component="button"
          type="button"
          size="small"
          icon={<AlertTriangle size={12} />}
          label={t('repositoryCard.archiveSyncWarning.label')}
          aria-label={`${t('repositoryCard.archiveSyncWarning.title')}: ${t('repositoryCard.archiveSyncWarning.viewDetails')}`}
          aria-haspopup="dialog"
          aria-expanded={detailsOpen}
          onClick={() => setDetailsOpen(true)}
          sx={(theme) => ({
            height: 20,
            maxWidth: 156,
            border: 0,
            borderRadius: 1,
            fontSize: '0.64rem',
            fontWeight: 600,
            color: theme.palette.warning.main,
            bgcolor: alpha(theme.palette.warning.main, 0.09),
            '& .MuiChip-label': { px: 0.75 },
            '& .MuiChip-icon': { color: 'inherit', ml: 0.75, mr: -0.125 },
            '&:hover': { bgcolor: alpha(theme.palette.warning.main, 0.16) },
            '&.Mui-focusVisible': {
              outline: `2px solid ${theme.palette.warning.main}`,
              outlineOffset: 2,
            },
          })}
        />
      </Tooltip>
      <ErrorDetailsDialog
        open={detailsOpen}
        onClose={() => setDetailsOpen(false)}
        job={{
          id: warning.operation_id,
          status: 'failed',
          error_message: [
            t('repositoryCard.archiveSyncWarning.description'),
            lastSync,
            '',
            warning.error_message,
          ].join('\n'),
        }}
      />
    </>
  )
}

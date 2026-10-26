import { useState } from 'react'
import { Alert, Box, Button, Typography } from '@mui/material'
import { useTranslation } from 'react-i18next'
import type { Repository } from '../types'
import { formatDateTimeFull } from '../utils/dateUtils'
import ErrorDetailsDialog from './ErrorDetailsDialog'

type SyncWarning = NonNullable<Repository['archive_sync_warning']>

/** A standing warning; the backend leaves transient failures in Activity. */
export default function RepositorySyncWarning({ warning }: { warning: SyncWarning }) {
  const { t } = useTranslation()
  const [detailsOpen, setDetailsOpen] = useState(false)

  return (
    <>
      <Alert
        severity="warning"
        variant="outlined"
        sx={{ mb: 1.5, '& .MuiAlert-message': { minWidth: 0, width: '100%' } }}
      >
        <Box sx={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 1 }}>
          <Box sx={{ flex: '1 1 220px', minWidth: 0 }}>
            <Typography variant="body2" sx={{ fontWeight: 600 }}>
              {t('repositoryCard.archiveSyncWarning.title')}
            </Typography>
            <Typography variant="body2">
              {t('repositoryCard.archiveSyncWarning.description')}
            </Typography>
            <Typography variant="caption" sx={{ display: 'block', mt: 0.5 }}>
              {warning.last_success_at
                ? t('repositoryCard.archiveSyncWarning.lastSuccess', {
                    when: formatDateTimeFull(warning.last_success_at),
                  })
                : t('repositoryCard.archiveSyncWarning.neverSynced')}
            </Typography>
          </Box>
          <Button size="small" color="inherit" onClick={() => setDetailsOpen(true)}>
            {t('repositoryCard.archiveSyncWarning.viewDetails')}
          </Button>
        </Box>
      </Alert>
      <ErrorDetailsDialog
        open={detailsOpen}
        onClose={() => setDetailsOpen(false)}
        job={{
          id: warning.operation_id,
          status: 'failed',
          error_message:
            warning.error_message || t('repositoryCard.archiveSyncWarning.description'),
        }}
      />
    </>
  )
}

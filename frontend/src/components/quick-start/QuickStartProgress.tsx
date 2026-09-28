import { Alert, Box, CircularProgress, Stack, Typography } from '@mui/material'
import { CheckCircle2, Circle, XCircle } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import type { QuickStartAction } from './quickStartActions'
import type { QuickStartActionStatus } from './useQuickStartRunner'

interface QuickStartProgressProps {
  actions: QuickStartAction[]
  statuses: Partial<Record<QuickStartAction, QuickStartActionStatus>>
  error: string | null
  finished: boolean
}

function StatusIcon({ status }: { status: QuickStartActionStatus }) {
  switch (status) {
    case 'running':
      return <CircularProgress size={18} thickness={5} />
    case 'done':
      return (
        <Box sx={{ color: 'success.main', display: 'flex' }}>
          <CheckCircle2 size={20} />
        </Box>
      )
    case 'failed':
      return (
        <Box sx={{ color: 'error.main', display: 'flex' }}>
          <XCircle size={20} />
        </Box>
      )
    default:
      return (
        <Box sx={{ color: 'text.disabled', display: 'flex' }}>
          <Circle size={20} />
        </Box>
      )
  }
}

export default function QuickStartProgress({
  actions,
  statuses,
  error,
  finished,
}: QuickStartProgressProps) {
  const { t } = useTranslation()
  return (
    <Stack spacing={2.5}>
      <Typography variant="h6" component="h3">
        {finished ? t('quickStart.progress.doneTitle') : t('quickStart.progress.title')}
      </Typography>
      <Stack component="ol" spacing={1.5} aria-live="polite" sx={{ listStyle: 'none', p: 0, m: 0 }}>
        {actions.map((action) => {
          const status = statuses[action] ?? 'pending'
          return (
            <Stack
              component="li"
              key={action}
              aria-label={`${t(`quickStart.progress.actions.${action}`)}: ${t(`quickStart.progress.status.${status}`)}`}
              direction="row"
              spacing={1.5}
              sx={{ alignItems: 'center' }}
            >
              <Box sx={{ width: 20, display: 'flex', justifyContent: 'center' }}>
                <StatusIcon status={status} />
              </Box>
              <Typography
                variant="body2"
                sx={{ color: status === 'pending' ? 'text.secondary' : 'text.primary' }}
              >
                {t(`quickStart.progress.actions.${action}`)}
              </Typography>
            </Stack>
          )
        })}
      </Stack>
      {error && (
        <Alert severity="error" role="alert">
          <Typography variant="body2" sx={{ fontWeight: 600 }}>
            {t('quickStart.progress.failed')}
          </Typography>
          {error}
        </Alert>
      )}
      {finished && (
        <Alert severity="success" variant="outlined">
          {t('quickStart.progress.doneHint')}
        </Alert>
      )}
    </Stack>
  )
}

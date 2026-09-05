import { Alert, Box, Button, Stack, Tooltip, Typography } from '@mui/material'
import { Pause, Play } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useAuthorization } from '../hooks/useAuthorization'
import PipelineBoard from './background-work/PipelineBoard'
import { operationsAPI } from '../services/api'

const QUEUE_KEY = ['operations-queue'] as const

export default function BackgroundWorkTab() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  // The pause, resume, and limits routes are admin-only (app/api/operations.py),
  // while the tab itself is visible to operators, so operators read the board
  // without controls that would 403.
  const { globalRoleRank, currentGlobalRole } = useAuthorization()
  const canManage =
    (globalRoleRank?.get(currentGlobalRole ?? '') ?? 0) >=
    (globalRoleRank?.get('admin') ?? Infinity)
  const { data } = useQuery({
    queryKey: QUEUE_KEY,
    queryFn: () => operationsAPI.getQueue().then((r) => r.data),
  })

  const pauseMutation = useMutation({
    mutationFn: () => operationsAPI.pause(),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: QUEUE_KEY }),
  })
  const resumeMutation = useMutation({
    mutationFn: () => operationsAPI.resume(),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: QUEUE_KEY }),
  })

  const paused = data?.paused ?? false
  const busy = pauseMutation.isPending || resumeMutation.isPending

  return (
    <Box>
      <Stack
        direction="row"
        spacing={2}
        sx={{ alignItems: 'flex-start', justifyContent: 'space-between', mb: 3 }}
      >
        <Box>
          <Typography variant="h6">{t('operations.background.title')}</Typography>
          <Typography variant="body2" sx={{ color: 'text.secondary' }}>
            {t('operations.background.subtitle')}
          </Typography>
        </Box>
        {!paused && (
          <Tooltip title={canManage ? '' : t('operations.background.pauseAdminOnly')}>
            <span>
              <Button
                size="small"
                variant="outlined"
                disabled={!canManage || busy}
                startIcon={<Pause size={14} />}
                onClick={() => pauseMutation.mutate()}
              >
                {t('operations.background.pause')}
              </Button>
            </span>
          </Tooltip>
        )}
      </Stack>
      {paused && (
        <Alert
          severity="warning"
          sx={{ mb: 2 }}
          action={
            canManage ? (
              <Button
                color="inherit"
                size="small"
                disabled={busy}
                startIcon={<Play size={14} />}
                onClick={() => resumeMutation.mutate()}
              >
                {t('operations.background.resume')}
              </Button>
            ) : undefined
          }
        >
          {t('operations.background.pausedBanner')}
        </Alert>
      )}
      {(pauseMutation.isError || resumeMutation.isError) && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {t('operations.background.pauseFailed')}
        </Alert>
      )}
      <PipelineBoard canManage={canManage} />
    </Box>
  )
}

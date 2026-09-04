import { useState } from 'react'
import { Alert, Box, Button, Stack, Tooltip, Typography } from '@mui/material'
import { Pause, Play } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useAuthorization } from '../hooks/useAuthorization'
import PipelineBoard from './background-work/PipelineBoard'
import RebuildMenu from './background-work/RebuildMenu'
import { operationsAPI } from '../services/api'
import type { RebuildStage } from '../types/operations'

const QUEUE_KEY = ['operations-queue'] as const

export default function BackgroundWorkTab() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  // The pause and resume routes are admin-only (app/api/operations.py), while
  // the tab itself is visible to operators, so operators read the board
  // without the lane control rather than getting a button that 403s.
  const { globalRoleRank, currentGlobalRole } = useAuthorization()
  const canPause =
    (globalRoleRank?.get(currentGlobalRole ?? '') ?? 0) >=
    (globalRoleRank?.get('admin') ?? Infinity)
  const { data } = useQuery({
    queryKey: QUEUE_KEY,
    queryFn: () => operationsAPI.getQueue().then((r) => r.data),
  })
  const [pendingStage, setPendingStage] = useState<RebuildStage | null>(null)

  const pauseMutation = useMutation({
    mutationFn: () => operationsAPI.pause(),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: QUEUE_KEY }),
  })
  const resumeMutation = useMutation({
    mutationFn: () => operationsAPI.resume(),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: QUEUE_KEY }),
  })

  const paused = data?.paused ?? false

  return (
    <Box>
      <Stack direction="row" spacing={1.5} sx={{ alignItems: 'center', mb: 2 }}>
        <Typography variant="h6" sx={{ mr: 'auto' }}>
          {t('operations.background.title')}
        </Typography>
        <Tooltip title={canPause ? '' : t('operations.background.pauseAdminOnly')}>
          <span>
            <Button
              size="small"
              variant="outlined"
              disabled={!canPause || pauseMutation.isPending || resumeMutation.isPending}
              startIcon={paused ? <Play size={14} /> : <Pause size={14} />}
              onClick={() => (paused ? resumeMutation.mutate() : pauseMutation.mutate())}
            >
              {paused ? t('operations.background.resume') : t('operations.background.pause')}
            </Button>
          </span>
        </Tooltip>
        <RebuildMenu onSelect={setPendingStage} />
      </Stack>
      {(pauseMutation.isError || resumeMutation.isError) && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {t('operations.background.pauseFailed')}
        </Alert>
      )}
      <PipelineBoard />
      {pendingStage && (
        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>
          {t('operations.background.rebuildNeedsRepository')}
        </Typography>
      )}
    </Box>
  )
}

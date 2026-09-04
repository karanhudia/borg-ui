import { useCallback, useMemo } from 'react'
import { Box, Stack, Typography } from '@mui/material'
import { ListChecks } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import PipelineStageColumn from './PipelineStageColumn'
import ForegroundLaneRow from './ForegroundLaneRow'
import EmptyStateCard from '../EmptyStateCard'
import { operationsAPI } from '../../services/api'
import { useOperationEvents } from '../../hooks/useOperationEvents'
import type { OperationItem, OperationProgressEvent, QueueResponse } from '../../types/operations'

const QUEUE_KEY = ['operations-queue'] as const

const STAGE_KINDS: Array<{ key: string; labelKey: string; kind: OperationItem['kind'] }> = [
  { key: 'connect', labelKey: 'operations.background.stage.connect', kind: 'import_connect' },
  { key: 'stats', labelKey: 'operations.background.stage.stats', kind: 'stats' },
  { key: 'archives', labelKey: 'operations.background.stage.archives', kind: 'archive_sync' },
  { key: 'history', labelKey: 'operations.background.stage.history', kind: 'history_index' },
]

const TERMINAL_STATUSES = new Set([
  'completed',
  'completed_with_warnings',
  'failed',
  'cancelled',
  'skipped',
])
const FOREGROUND_CATEGORIES = new Set(['backup', 'restore', 'maintenance'])

export default function PipelineBoard() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const { data, isLoading } = useQuery({
    queryKey: QUEUE_KEY,
    queryFn: () => operationsAPI.getQueue().then((r) => r.data),
    refetchInterval: 15000,
  })

  const onUpdated = useCallback(
    (updated: OperationItem) => {
      queryClient.setQueryData<QueueResponse | undefined>(QUEUE_KEY, (current) => {
        if (!current) return current
        return {
          ...current,
          repositories: current.repositories.map((repo) => ({
            ...repo,
            operations: repo.operations.some((op) => op.id === updated.id)
              ? repo.operations.map((op) => (op.id === updated.id ? updated : op))
              : repo.repository_id === updated.repository_id
                ? [...repo.operations, updated]
                : repo.operations,
          })),
        }
      })
    },
    [queryClient]
  )

  const onProgress = useCallback(
    (progress: OperationProgressEvent['data']) => {
      queryClient.setQueryData<QueueResponse | undefined>(QUEUE_KEY, (current) => {
        if (!current) return current
        return {
          ...current,
          repositories: current.repositories.map((repo) => ({
            ...repo,
            operations: repo.operations.map((op) =>
              op.id === progress.id ? { ...op, ...progress } : op
            ),
          })),
        }
      })
    },
    [queryClient]
  )

  useOperationEvents(onUpdated, onProgress)

  const allOperations = useMemo(
    () => data?.repositories.flatMap((repo) => repo.operations) ?? [],
    [data]
  )

  const foreground = allOperations.find(
    (op) => FOREGROUND_CATEGORIES.has(op.category) && op.status === 'running'
  )

  const readyOperations = allOperations.filter((op) => TERMINAL_STATUSES.has(op.status))

  const handleRetry = useCallback((_operationId: number) => {
    // Retry is a rebuild-from-stage action owned by RebuildMenu (Task 8); a
    // per-card retry re-enqueues the same kind at manual priority via the
    // rebuild route, wired in Task 9 where the repository id is available
    // from the queue row.
  }, [])

  if (!isLoading && allOperations.length === 0) {
    return (
      <EmptyStateCard
        icon={<ListChecks size={48} />}
        title={t('operations.background.emptyTitle')}
        description={t('operations.background.emptyDescription')}
      />
    )
  }

  return (
    <Box>
      {foreground && (
        <Box sx={{ mb: 2 }}>
          <ForegroundLaneRow operation={foreground} />
        </Box>
      )}
      <Stack direction="row" spacing={3} sx={{ overflowX: 'auto', pb: 1 }}>
        {STAGE_KINDS.map((stage) => (
          <PipelineStageColumn
            key={stage.key}
            stage={{
              key: stage.key,
              label: t(stage.labelKey),
              operations: allOperations.filter(
                (op) => op.kind === stage.kind && !TERMINAL_STATUSES.has(op.status)
              ),
            }}
            workerControl={
              stage.key === 'history' && data ? (
                <Typography
                  variant="caption"
                  color="text.secondary"
                  sx={{ display: 'block', mt: 1 }}
                >
                  {t('operations.background.workers', { count: data.limits.index_workers })}
                </Typography>
              ) : undefined
            }
            onRetry={handleRetry}
          />
        ))}
        <PipelineStageColumn
          stage={{
            key: 'ready',
            label: t('operations.background.stage.ready'),
            operations: readyOperations,
          }}
        />
      </Stack>
    </Box>
  )
}

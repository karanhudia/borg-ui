import { useCallback, useMemo, useState } from 'react'
import { Alert, Box, Stack, Typography } from '@mui/material'
import { ListChecks } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import PipelineStageColumn from './PipelineStageColumn'
import ForegroundLaneRow from './ForegroundLaneRow'
import RepositoryTrackDialog from './RepositoryTrackDialog'
import EmptyStateCard from '../EmptyStateCard'
import { retryStageFor } from './retryStage'
import { archivesAPI, operationsAPI } from '../../services/api'
import { useOperationEvents } from '../../hooks/useOperationEvents'
import type {
  OperationItem,
  OperationProgressEvent,
  QueueResponse,
  RebuildStage,
} from '../../types/operations'

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
  const [trackRepository, setTrackRepository] = useState<{ id: number; name: string } | null>(null)
  const { data, isLoading, isError } = useQuery({
    queryKey: QUEUE_KEY,
    queryFn: () => operationsAPI.getQueue().then((r) => r.data),
    refetchInterval: 15000,
  })

  const onUpdated = useCallback(
    (updated: OperationItem) => {
      queryClient.setQueryData<QueueResponse | undefined>(QUEUE_KEY, (current) => {
        if (!current) return current
        const known = current.repositories.some(
          (repo) =>
            repo.repository_id === updated.repository_id ||
            repo.operations.some((op) => op.id === updated.id)
        )
        const repositories = current.repositories.map((repo) => ({
          ...repo,
          operations: repo.operations.some((op) => op.id === updated.id)
            ? repo.operations.map((op) => (op.id === updated.id ? updated : op))
            : repo.repository_id === updated.repository_id
              ? [...repo.operations, updated]
              : repo.operations,
        }))
        // The first operation for a repository the cache has never seen would
        // otherwise stay invisible until the next refetch.
        return {
          ...current,
          repositories: known
            ? repositories
            : [
                ...repositories,
                {
                  repository_id: updated.repository_id,
                  repository_name: updated.repository ?? 'System',
                  lane_busy: false,
                  operations: [updated],
                },
              ],
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

  const retryMutation = useMutation({
    mutationFn: ({ repositoryId, stage }: { repositoryId: number; stage: RebuildStage }) =>
      archivesAPI.rebuild(repositoryId, stage),
    onSettled: () => queryClient.invalidateQueries({ queryKey: QUEUE_KEY }),
  })

  const handleRetry = useCallback(
    (operation: OperationItem) => {
      const stage = retryStageFor(operation)
      if (!stage || operation.repository_id == null) return
      retryMutation.mutate({ repositoryId: operation.repository_id, stage })
    },
    [retryMutation]
  )

  const handleOpen = useCallback((operation: OperationItem) => {
    if (operation.repository_id == null) return
    setTrackRepository({
      id: operation.repository_id,
      name: operation.repository ?? String(operation.repository_id),
    })
  }, [])

  if (isError) {
    return <Alert severity="error">{t('operations.background.queueFailed')}</Alert>
  }

  if (!isLoading && data && allOperations.length === 0) {
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
            onOpen={handleOpen}
          />
        ))}
        <PipelineStageColumn
          stage={{
            key: 'ready',
            label: t('operations.background.stage.ready'),
            operations: readyOperations,
          }}
          // Failed rows are terminal, so they land here rather than in a
          // stage column - this is the only place the retry control renders.
          onRetry={handleRetry}
          onOpen={handleOpen}
        />
      </Stack>
      {trackRepository && (
        <RepositoryTrackDialog
          open
          onClose={() => setTrackRepository(null)}
          repositoryId={trackRepository.id}
          repositoryName={trackRepository.name}
          operations={allOperations.filter((op) => op.repository_id === trackRepository.id)}
        />
      )}
    </Box>
  )
}

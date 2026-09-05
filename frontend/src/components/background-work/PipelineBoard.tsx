import { useCallback, useMemo, useState } from 'react'
import {
  Alert,
  Box,
  Button,
  IconButton,
  Stack,
  Tooltip,
  Typography,
  alpha,
  useTheme,
} from '@mui/material'
import { ListChecks, Minus, Plus, RotateCw } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { formatDistanceToNow } from 'date-fns'
import RepositoryRow from './RepositoryRow'
import RepositoryTrackDialog from './RepositoryTrackDialog'
import EmptyStateCard from '../EmptyStateCard'
import RichSelect from '../shared/RichSelect'
import { usePlan } from '../../hooks/usePlan'
import {
  STAGE_ORDER,
  TRACK_GRID_COLUMNS,
  deriveTrack,
  REBUILD_STAGE_FOR,
  type StageState,
} from './repositoryTrack'
import { activityAPI, archivesAPI, operationsAPI, repositoriesAPI } from '../../services/api'
import { useOperationEvents } from '../../hooks/useOperationEvents'
import { parseBackendDate } from '../../utils/dateUtils'
import type {
  OperationItem,
  OperationProgressEvent,
  QueueResponse,
  RebuildStage,
} from '../../types/operations'
import type { Repository } from '@/types'

const QUEUE_KEY = ['operations-queue'] as const
const MIN_WORKERS = 1
const MAX_WORKERS = 32

interface PipelineBoardProps {
  // Worker limits are admin-only on the API, like pause. Everyone else
  // reads the count without a control that would 403.
  canManage: boolean
}

function WorkerStepper({
  count,
  canManage,
  onChange,
}: {
  count: number
  canManage: boolean
  onChange: (next: number) => void
}) {
  const { t } = useTranslation()
  const label = t('operations.background.workers', { count })
  if (!canManage) {
    return (
      <Typography variant="caption" sx={{ color: 'text.secondary' }}>
        {label}
      </Typography>
    )
  }
  return (
    <Box sx={{ display: 'inline-flex', alignItems: 'center', gap: 0.25 }}>
      <Tooltip title={t('operations.background.workersDecrease')}>
        <span>
          <IconButton
            size="small"
            aria-label={t('operations.background.workersDecrease')}
            disabled={count <= MIN_WORKERS}
            onClick={() => onChange(count - 1)}
            sx={{ p: 0.25 }}
          >
            <Minus size={12} />
          </IconButton>
        </span>
      </Tooltip>
      <Typography
        variant="caption"
        sx={{ color: 'text.secondary', minWidth: 64, textAlign: 'center' }}
      >
        {label}
      </Typography>
      <Tooltip title={t('operations.background.workersIncrease')}>
        <span>
          <IconButton
            size="small"
            aria-label={t('operations.background.workersIncrease')}
            disabled={count >= MAX_WORKERS}
            onClick={() => onChange(count + 1)}
            sx={{ p: 0.25 }}
          >
            <Plus size={12} />
          </IconButton>
        </span>
      </Tooltip>
    </Box>
  )
}

const REBUILD_STAGES: RebuildStage[] = ['stats', 'archives', 'history']

function EmptyBoard({
  onRebuild,
}: {
  onRebuild: (repositoryId: number, stage: RebuildStage) => void
}) {
  const { t } = useTranslation()
  const theme = useTheme()
  const { can } = usePlan()
  const [repositoryId, setRepositoryId] = useState<string>('')
  const [stage, setStage] = useState<RebuildStage>('stats')

  const { data: lastReconcile, isFetched } = useQuery({
    queryKey: ['operations-last-reconcile'],
    queryFn: () =>
      activityAPI
        .list({ trigger: ['reconcile'], limit: 1 })
        .then(
          (r) =>
            (r.data as Array<{ completed_at: string | null; started_at?: string | null }>)[0] ??
            null
        ),
  })
  const { data: repositoriesData } = useQuery({
    queryKey: ['repositories'],
    queryFn: repositoriesAPI.getRepositories,
  })
  const repositories: Repository[] = repositoriesData?.data?.repositories ?? []
  const selectedId = repositoryId ? Number(repositoryId) : repositories[0]?.id

  const reconcileAt = lastReconcile?.completed_at ?? lastReconcile?.started_at ?? null
  const reconcileText = !isFetched
    ? null
    : reconcileAt
      ? t('operations.background.lastReconcile', {
          ago: formatDistanceToNow(parseBackendDate(reconcileAt), { addSuffix: true }),
        })
      : t('operations.background.lastReconcileNever')

  const historyLocked = !can('archive_history')

  return (
    <Stack spacing={2}>
      <EmptyStateCard
        icon={<ListChecks size={48} />}
        title={t('operations.background.emptyTitle')}
        description={t('operations.background.emptyDescription')}
        secondaryDescription={reconcileText}
      />
      {repositories.length > 0 && (
        <Box
          sx={{
            border: `1px solid ${theme.palette.divider}`,
            borderRadius: 2,
            bgcolor: 'background.paper',
            p: 2.5,
            display: 'grid',
            gridTemplateColumns: { xs: '1fr', md: 'minmax(220px, 1fr) 2fr' },
            gap: 3,
            alignItems: 'center',
          }}
        >
          <Box>
            <Stack direction="row" spacing={1} sx={{ alignItems: 'center', mb: 0.5 }}>
              <RotateCw size={16} />
              <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
                {t('operations.background.rebuildTitle')}
              </Typography>
            </Stack>
            <Typography variant="body2" sx={{ color: 'text.secondary' }}>
              {t('operations.background.rebuildDescription')}
            </Typography>
          </Box>
          <Stack
            direction={{ xs: 'column', sm: 'row' }}
            spacing={1.5}
            sx={{ alignItems: { sm: 'center' } }}
          >
            <Box sx={{ flex: 1, minWidth: 0 }}>
              <RichSelect
                value={String(selectedId ?? '')}
                onChange={setRepositoryId}
                label={t('operations.background.rebuildRepository')}
                options={repositories.map((repo) => ({
                  value: String(repo.id),
                  primary: repo.name,
                  secondary: repo.path,
                }))}
              />
            </Box>
            <Box sx={{ width: { sm: 200 } }}>
              <RichSelect
                value={stage}
                onChange={(value) => setStage(value as RebuildStage)}
                label={t('operations.background.rebuildStageLabel')}
                options={REBUILD_STAGES.map((value) => ({
                  value,
                  primary: t(`operations.background.rebuildStage.${value}`),
                  secondary:
                    value === 'history' && historyLocked
                      ? t('operations.background.proOnly')
                      : undefined,
                  disabled: value === 'history' && historyLocked,
                }))}
              />
            </Box>
            <Button
              variant="contained"
              disableElevation
              sx={{ height: 56, px: 3, flexShrink: 0 }}
              onClick={() => selectedId != null && onRebuild(selectedId, stage)}
            >
              {t('operations.background.rebuildAction')}
            </Button>
          </Stack>
        </Box>
      )}
    </Stack>
  )
}

export default function PipelineBoard({ canManage }: PipelineBoardProps) {
  const { t } = useTranslation()
  const theme = useTheme()
  const queryClient = useQueryClient()
  const [trackRepository, setTrackRepository] = useState<{ id: number; name: string } | null>(null)
  const [rebuildFailed, setRebuildFailed] = useState(false)
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

  const tracks = useMemo(
    () =>
      data
        ? data.repositories
            .filter((repo) => repo.operations.length > 0)
            .map((repo) => deriveTrack(repo, data.limits, data.paused))
        : [],
    [data]
  )

  const rebuildMutation = useMutation({
    mutationFn: ({ repositoryId, stage }: { repositoryId: number; stage: RebuildStage }) =>
      archivesAPI.rebuild(repositoryId, stage),
    onMutate: () => setRebuildFailed(false),
    onError: () => setRebuildFailed(true),
    onSettled: () => queryClient.invalidateQueries({ queryKey: QUEUE_KEY }),
  })

  const limitsMutation = useMutation({
    mutationFn: (workers: number) => operationsAPI.updateLimits(workers),
    onSettled: () => queryClient.invalidateQueries({ queryKey: QUEUE_KEY }),
  })

  const handleRetry = useCallback(
    (repositoryId: number | null, stage: StageState) => {
      const rebuildStage = REBUILD_STAGE_FOR[stage.key]
      if (!rebuildStage || repositoryId == null) return
      rebuildMutation.mutate({ repositoryId, stage: rebuildStage })
    },
    [rebuildMutation]
  )

  if (isError) {
    return <Alert severity="error">{t('operations.background.queueFailed')}</Alert>
  }

  if (!isLoading && data && tracks.length === 0) {
    return (
      <Box>
        {rebuildFailed && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {t('operations.background.rebuildFailed')}
          </Alert>
        )}
        <EmptyBoard
          onRebuild={(repositoryId, stage) => rebuildMutation.mutate({ repositoryId, stage })}
        />
      </Box>
    )
  }

  return (
    <Box>
      {rebuildFailed && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {t('operations.background.rebuildFailed')}
        </Alert>
      )}
      {limitsMutation.isError && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {t('operations.background.workersFailed')}
        </Alert>
      )}
      <Box
        sx={{
          border: `1px solid ${theme.palette.divider}`,
          borderRadius: 2,
          px: 2.5,
          bgcolor: 'background.paper',
        }}
      >
        <Box
          sx={{
            display: { xs: 'none', md: 'grid' },
            gridTemplateColumns: TRACK_GRID_COLUMNS,
            columnGap: 2,
            alignItems: 'end',
            py: 1.5,
            borderBottom: `1px solid ${theme.palette.divider}`,
            bgcolor: alpha(theme.palette.text.primary, 0.02),
            mx: -2.5,
            px: 2.5,
            borderTopLeftRadius: 8,
            borderTopRightRadius: 8,
          }}
        >
          <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 600 }}>
            {t('operations.background.repositoryColumn')}
          </Typography>
          {STAGE_ORDER.map((key) => (
            <Box key={key} sx={{ display: 'flex', flexDirection: 'column', gap: 0.25 }}>
              <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 600 }}>
                {t(`operations.background.stage.${key}`)}
              </Typography>
              {key === 'history' && data && (
                <WorkerStepper
                  count={data.limits.index_workers}
                  canManage={canManage}
                  onChange={(next) => limitsMutation.mutate(next)}
                />
              )}
            </Box>
          ))}
          <span />
        </Box>
        {tracks.map((track) => (
          <RepositoryRow
            key={track.repositoryId ?? track.repositoryName}
            track={track}
            onOpen={() =>
              track.repositoryId != null &&
              setTrackRepository({ id: track.repositoryId, name: track.repositoryName })
            }
            onRetry={(stage) => handleRetry(track.repositoryId, stage)}
            onRebuild={(stage) =>
              track.repositoryId != null &&
              rebuildMutation.mutate({ repositoryId: track.repositoryId, stage })
            }
          />
        ))}
      </Box>
      {trackRepository && (
        <RepositoryTrackDialog
          open
          onClose={() => setTrackRepository(null)}
          repositoryId={trackRepository.id}
          repositoryName={trackRepository.name}
          operations={
            data?.repositories.find((repo) => repo.repository_id === trackRepository.id)
              ?.operations ?? []
          }
        />
      )}
    </Box>
  )
}

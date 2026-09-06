import { useCallback, useMemo, useState } from 'react'
import { Alert, Box, Button, IconButton, Stack, Tooltip, Typography, useTheme } from '@mui/material'
import { HardDrive, Minus, Plus, SearchX } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import RepositoryHubRow from './RepositoryHubRow'
import RepositoryTrackDialog from './RepositoryTrackDialog'
import EmptyStateCard from '../EmptyStateCard'
import HubSummary from './HubSummary'
import HubToolbar from './HubToolbar'
import {
  DEFAULT_TOOLBAR,
  applyToolbar,
  attentionCounts,
  mergeRows,
  type HubToolbarState,
} from './hubRows'
import { usePlan } from '../../hooks/usePlan'
import {
  HUB_GRID_COLUMNS,
  deriveTrack,
  REBUILD_STAGES,
  REBUILD_STAGE_FOR,
  type StageState,
} from './repositoryTrack'
import { archivesAPI, operationsAPI } from '../../services/api'
import { useOperationEvents } from '../../hooks/useOperationEvents'
import type {
  OperationItem,
  OperationProgressEvent,
  QueueResponse,
  RebuildStage,
} from '../../types/operations'

const QUEUE_KEY = ['operations-queue'] as const
const HUB_KEY = ['operations-repositories'] as const
const MIN_WORKERS = 1
const MAX_WORKERS = 32
// Rows rendered before a "show more" step in. Each row carries a stage
// track and a menu, so a few hundred at once would make the tab sluggish.
const WINDOW_SIZE = 50

interface PipelineBoardProps {
  // Worker limits, pause, and reconcile are admin-only on the API. Everyone
  // else reads the board without controls that would 403.
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

export default function PipelineBoard({ canManage }: PipelineBoardProps) {
  const { t } = useTranslation()
  const theme = useTheme()
  const queryClient = useQueryClient()
  const { can } = usePlan()
  const [trackRepository, setTrackRepository] = useState<{ id: number; name: string } | null>(null)
  const [rebuildFailed, setRebuildFailed] = useState(false)
  const [reconcileResult, setReconcileResult] = useState<number | null>(null)
  const [toolbar, setToolbarState] = useState<HubToolbarState>(DEFAULT_TOOLBAR)
  const [windowSize, setWindowSize] = useState(WINDOW_SIZE)
  // Any toolbar change starts the window over: the rows it revealed were
  // for a different list.
  const setToolbar = (next: HubToolbarState) => {
    setToolbarState(next)
    setWindowSize(WINDOW_SIZE)
  }

  const queue = useQuery({
    queryKey: QUEUE_KEY,
    queryFn: () => operationsAPI.getQueue().then((r) => r.data),
    refetchInterval: 15000,
  })
  const hub = useQuery({
    queryKey: HUB_KEY,
    queryFn: () => operationsAPI.getRepositories().then((r) => r.data),
    refetchInterval: 30000,
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
      // A finished index stage changes the numbers at rest, so refresh
      // the hub once the queue has settled rather than on every progress
      // tick.
      if (updated.category === 'index' && updated.status !== 'running') {
        queryClient.invalidateQueries({ queryKey: HUB_KEY })
      }
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
      queue.data
        ? queue.data.repositories
            .filter((repo) => repo.operations.length > 0)
            .map((repo) => deriveTrack(repo, queue.data.limits, queue.data.paused))
        : [],
    [queue.data]
  )
  const rows = useMemo(() => mergeRows(hub.data?.repositories ?? [], tracks), [hub.data, tracks])
  const attention = useMemo(() => attentionCounts(rows), [rows])
  const matched = useMemo(() => applyToolbar(rows, toolbar), [rows, toolbar])
  const visible = matched.slice(0, windowSize)

  const invalidateBoard = () => {
    queryClient.invalidateQueries({ queryKey: QUEUE_KEY })
    queryClient.invalidateQueries({ queryKey: HUB_KEY })
  }

  const rebuildMutation = useMutation({
    mutationFn: ({ repositoryId, stage }: { repositoryId: number; stage: RebuildStage }) =>
      archivesAPI.rebuild(repositoryId, stage),
    onMutate: () => setRebuildFailed(false),
    onError: () => setRebuildFailed(true),
    onSettled: invalidateBoard,
  })

  const limitsMutation = useMutation({
    mutationFn: (workers: number) => operationsAPI.updateLimits(workers),
    onSettled: () => queryClient.invalidateQueries({ queryKey: QUEUE_KEY }),
  })

  const reconcileMutation = useMutation({
    mutationFn: () => operationsAPI.reconcileNow().then((r) => r.data),
    onMutate: () => setReconcileResult(null),
    onSuccess: (data) => setReconcileResult(data.repositories),
    onSettled: invalidateBoard,
  })

  const handleRetry = useCallback(
    (repositoryId: number | null, stage: StageState) => {
      const rebuildStage = REBUILD_STAGE_FOR[stage.key]
      if (!rebuildStage || repositoryId == null) return
      rebuildMutation.mutate({ repositoryId, stage: rebuildStage })
    },
    [rebuildMutation]
  )

  if (queue.isError) {
    return <Alert severity="error">{t('operations.background.queueFailed')}</Alert>
  }
  if (hub.isError) {
    return <Alert severity="error">{t('operations.background.hub.loadFailed')}</Alert>
  }
  if (!hub.data || !queue.data) {
    return null
  }

  const historyAvailable = hub.data.history_available && can('archive_history')
  const messages = (
    <>
      {rebuildFailed && (
        <Alert severity="error" onClose={() => setRebuildFailed(false)}>
          {t('operations.background.rebuildFailed')}
        </Alert>
      )}
      {limitsMutation.isError && (
        <Alert severity="error">{t('operations.background.workersFailed')}</Alert>
      )}
      {reconcileMutation.isError && (
        <Alert severity="error">{t('operations.background.hub.reconcileFailed')}</Alert>
      )}
      {reconcileResult != null && (
        <Alert
          severity={reconcileResult > 0 ? 'success' : 'info'}
          onClose={() => setReconcileResult(null)}
        >
          {reconcileResult > 0
            ? t('operations.background.hub.reconcileStarted', { count: reconcileResult })
            : t('operations.background.hub.reconcileNone')}
        </Alert>
      )}
    </>
  )

  if (rows.length === 0) {
    return (
      <Stack spacing={2}>
        {messages}
        <EmptyStateCard
          icon={<HardDrive size={48} />}
          title={t('operations.background.hub.noRepositoriesTitle')}
          description={t('operations.background.hub.noRepositoriesDescription')}
        />
      </Stack>
    )
  }

  // Header cells match DataTable's, so the hub reads as one of the
  // product's tables rather than a page of its own.
  const columnHeader = (label: string, extra?: React.ReactNode, key?: string) => (
    <Box key={key} sx={{ display: 'flex', flexDirection: 'column', gap: 0.25 }}>
      <Typography
        component="span"
        sx={{
          color: 'text.disabled',
          fontWeight: 700,
          fontSize: '0.7rem',
          textTransform: 'uppercase',
          letterSpacing: '0.05em',
          lineHeight: 1.6,
        }}
      >
        {label}
      </Typography>
      {extra}
    </Box>
  )

  return (
    <Stack spacing={2}>
      <HubSummary
        totals={hub.data.totals}
        attention={attention}
        onAttention={(reason) => setToolbar({ ...toolbar, attention: reason })}
        lastReconcileAt={hub.data.last_reconcile_at}
        reconcileIntervalMinutes={hub.data.reconcile_interval_minutes}
        canManage={canManage}
        reconciling={reconcileMutation.isPending}
        onReconcile={() => reconcileMutation.mutate()}
      />
      {messages}
      <HubToolbar
        state={toolbar}
        onChange={setToolbar}
        shown={visible.length}
        total={matched.length}
      />
      {matched.length === 0 ? (
        <EmptyStateCard
          icon={<SearchX size={48} />}
          title={t('operations.background.hub.noMatchTitle')}
          description={t('operations.background.hub.noMatchDescription')}
        />
      ) : (
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
              gridTemplateColumns: HUB_GRID_COLUMNS,
              columnGap: 2,
              alignItems: 'end',
              py: 1.25,
              borderBottom: `1px solid ${theme.palette.divider}`,
              bgcolor: 'background.default',
              mx: -2.5,
              px: 2.5,
              borderTopLeftRadius: 8,
              borderTopRightRadius: 8,
            }}
          >
            {columnHeader(t('operations.background.repositoryColumn'))}
            {REBUILD_STAGES.map((stage) =>
              columnHeader(
                t(`operations.background.stage.${stage}`),
                // History is the only stage with a pool of workers to size.
                stage === 'history' ? (
                  <WorkerStepper
                    count={queue.data.limits.index_workers}
                    canManage={canManage}
                    onChange={(next) => limitsMutation.mutate(next)}
                  />
                ) : undefined,
                stage
              )
            )}
            <span />
          </Box>
          {visible.map((row) => (
            <RepositoryHubRow
              key={row.key}
              repository={row.repository}
              track={row.track}
              historyAvailable={historyAvailable}
              totalHistoryRows={hub.data.totals.history_rows}
              onOpen={() => {
                const id = row.repository?.repository_id ?? row.track?.repositoryId ?? null
                const name = row.repository?.repository_name ?? row.track?.repositoryName ?? ''
                if (id != null) setTrackRepository({ id, name })
              }}
              onRetry={(stage) =>
                handleRetry(row.repository?.repository_id ?? row.track?.repositoryId ?? null, stage)
              }
            />
          ))}
          {matched.length > visible.length && (
            <Box sx={{ display: 'flex', justifyContent: 'center', py: 1.5 }}>
              <Button
                size="small"
                variant="text"
                onClick={() => setWindowSize((size) => size + WINDOW_SIZE)}
              >
                {t('operations.background.hub.showMore', {
                  count: Math.min(WINDOW_SIZE, matched.length - visible.length),
                })}
              </Button>
            </Box>
          )}
        </Box>
      )}
      {trackRepository && (
        <RepositoryTrackDialog
          open
          onClose={() => setTrackRepository(null)}
          repositoryId={trackRepository.id}
          repositoryName={trackRepository.name}
          operations={
            queue.data.repositories.find((repo) => repo.repository_id === trackRepository.id)
              ?.operations ?? []
          }
        />
      )}
    </Stack>
  )
}

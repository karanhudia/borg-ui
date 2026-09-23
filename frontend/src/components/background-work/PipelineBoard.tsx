import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Alert, Box, Button, IconButton, Stack, Tooltip, Typography, useTheme } from '@mui/material'
import { HardDrive, Minus, Plus, SearchX } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import RepositoryHubRow from './RepositoryHubRow'
import RepositoryTrackDialog from './RepositoryTrackDialog'
import EmptyStateCard from '../EmptyStateCard'
import HubSummary from './HubSummary'
import HubToolbar from './HubToolbar'
import StageStrip from './StageStrip'
import {
  DEFAULT_TOOLBAR,
  applyToolbar,
  attentionCounts,
  mergeRows,
  stageCounts,
  type HubToolbarState,
} from './hubRows'
import { usePlan } from '../../hooks/usePlan'
import {
  HUB_GRID_COLUMNS,
  deriveTrack,
  REBUILD_STAGE_FOR,
  type StageState,
} from './repositoryTrack'
import { archivesAPI, operationsAPI } from '../../services/api'
import { getApiErrorDetail } from '../../utils/apiErrors'
import { translateBackendKey } from '../../utils/translateBackendKey'
import { useOperationEvents } from '../../hooks/useOperationEvents'
import type {
  OperationItem,
  OperationProgressEvent,
  PausableStage,
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
  const [rebuildFailed, setRebuildFailed] = useState<string | null>(null)
  const [reconcileResult, setReconcileResult] = useState<number | null>(null)
  const [toolbar, setToolbarState] = useState<HubToolbarState>(DEFAULT_TOOLBAR)
  const [windowSize, setWindowSize] = useState(WINDOW_SIZE)
  // Any toolbar change starts the window over: the rows it revealed were
  // for a different list.
  const setToolbar = (next: HubToolbarState) => {
    setToolbarState(next)
    setWindowSize(WINDOW_SIZE)
  }

  const refetchAfterEvents = useRef(false)
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

  // Do not race optimistic events against a response whose snapshot time is
  // unknown. Let active requests finish, then coalesce intervening events into
  // one fresh read. Progress bursts cannot starve a slow initial request.
  useEffect(() => {
    if (!queue.isFetching && refetchAfterEvents.current) {
      refetchAfterEvents.current = false
      queryClient.invalidateQueries({ queryKey: QUEUE_KEY }, { cancelRefetch: false })
    }
  }, [queue.isFetching, queryClient])

  const onUpdated = useCallback(
    (updated: OperationItem) => {
      if (updated.category === 'index' && updated.status !== 'running') {
        queryClient.invalidateQueries({ queryKey: HUB_KEY })
      }
      if (queryClient.isFetching({ queryKey: QUEUE_KEY }) > 0) {
        refetchAfterEvents.current = true
        return
      }
      const cached = queryClient.getQueryData<QueueResponse>(QUEUE_KEY)
      const started =
        updated.status === 'running' &&
        !cached?.repositories.some((repository) =>
          repository.operations.some(
            (operation) => operation.id === updated.id && operation.status === 'running'
          )
        )
      const applyUpdate = (current: QueueResponse): QueueResponse => {
        const known = current.repositories.some(
          (repo) =>
            repo.repository_id === updated.repository_id ||
            repo.operations.some((op) => op.id === updated.id)
        )
        // Only the operations change here; `lane_busy` and `index_holder_ids`
        // keep their fetched values, and the track reads them against the
        // operations at hand (see deriveTrack).
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
                  index_holder_ids: [],
                  operations: [updated],
                },
              ],
        }
      }
      queryClient.setQueryData<QueueResponse | undefined>(QUEUE_KEY, (current) =>
        current ? applyUpdate(current) : current
      )
      // A newly running operation can take either the exclusive lane or the
      // shared index slot. Fetch both authoritative flags and the holder;
      // subsequent running/progress events only update the cached rows.
      if (started) queryClient.invalidateQueries({ queryKey: QUEUE_KEY })
    },
    [queryClient]
  )

  const onProgress = useCallback(
    (progress: OperationProgressEvent['data']) => {
      // The active response will supply progress. Unlike status transitions,
      // progress ticks must not sustain a chain of follow-up requests.
      if (queryClient.isFetching({ queryKey: QUEUE_KEY }) > 0) {
        return
      }
      const applyProgress = (current: QueueResponse): QueueResponse => {
        return {
          ...current,
          repositories: current.repositories.map((repo) => ({
            ...repo,
            operations: repo.operations.map((op) =>
              op.id === progress.id ? { ...op, ...progress } : op
            ),
          })),
        }
      }
      queryClient.setQueryData<QueueResponse | undefined>(QUEUE_KEY, (current) =>
        current ? applyProgress(current) : current
      )
    },
    [queryClient]
  )

  useOperationEvents(onUpdated, onProgress)

  const tracks = useMemo(
    () =>
      queue.data
        ? queue.data.repositories
            .filter((repo) => repo.operations.length > 0)
            .map((repo) => deriveTrack(repo, queue.data.limits, queue.data.paused_stages))
        : [],
    [queue.data]
  )
  const rows = useMemo(() => mergeRows(hub.data?.repositories ?? [], tracks), [hub.data, tracks])
  const attention = useMemo(() => attentionCounts(rows), [rows])
  const counts = useMemo(() => stageCounts(rows), [rows])
  const matched = useMemo(() => applyToolbar(rows, toolbar), [rows, toolbar])
  const visible = matched.slice(0, windowSize)

  const invalidateBoard = () => {
    queryClient.invalidateQueries({ queryKey: QUEUE_KEY })
    queryClient.invalidateQueries({ queryKey: HUB_KEY })
  }

  const rebuildMutation = useMutation({
    mutationFn: ({ repositoryId, stage }: { repositoryId: number; stage: RebuildStage }) =>
      archivesAPI.rebuild(repositoryId, stage),
    onMutate: () => setRebuildFailed(null),
    // A rebuild refused while the repository's history is still being built
    // says which run holds it (#1079); anything else keeps the generic line.
    onError: (error) =>
      setRebuildFailed(
        translateBackendKey(getApiErrorDetail(error), 'operations.background.rebuildFailed')
      ),
    onSettled: invalidateBoard,
  })

  const stageMutation = useMutation({
    mutationFn: ({ stage, paused }: { stage: PausableStage; paused: boolean }) =>
      paused ? operationsAPI.pauseStage(stage) : operationsAPI.resumeStage(stage),
    onSettled: () => queryClient.invalidateQueries({ queryKey: QUEUE_KEY }),
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

  const trackHubRepository =
    trackRepository == null
      ? undefined
      : hub.data?.repositories.find((repo) => repo.repository_id === trackRepository.id)
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
        <Alert severity="error" onClose={() => setRebuildFailed(null)}>
          {rebuildFailed}
        </Alert>
      )}
      {stageMutation.isError && (
        <Alert severity="error">{t('operations.background.pauseFailed')}</Alert>
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
  const columnHeader = (label: string) => (
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
      <StageStrip
        counts={counts}
        selected={toolbar.stage ?? null}
        onSelect={(stage) => setToolbar({ ...toolbar, stage })}
        pausedStages={queue.data.paused_stages}
        canManage={canManage}
        onTogglePause={(stage, paused) => stageMutation.mutate({ stage, paused })}
        historyExtra={
          <WorkerStepper
            count={queue.data.limits.index_workers}
            canManage={canManage}
            onChange={(next) => limitsMutation.mutate(next)}
          />
        }
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
            // The header and the rows bleed past the padding with their own
            // backgrounds; clipping keeps the rounded corners visible.
            overflow: 'hidden',
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
            }}
          >
            {columnHeader(t('operations.background.repositoryColumn'))}
            {columnHeader(t('operations.background.currentStageColumn'))}
            {columnHeader(t('operations.background.lastUpdatedColumn'))}
            <span />
          </Box>
          {visible.map((row) => (
            <RepositoryHubRow
              key={row.key}
              repository={row.repository}
              track={row.track}
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
          repository={trackHubRepository}
          historyAvailable={historyAvailable}
          totalHistoryRows={hub.data.totals.history_rows}
          historyCapability={trackHubRepository?.history_capability}
          indexMode={trackHubRepository?.index_mode}
          history={trackHubRepository?.history}
          operations={
            queue.data.repositories.find((repo) => repo.repository_id === trackRepository.id)
              ?.operations ?? []
          }
        />
      )}
    </Stack>
  )
}

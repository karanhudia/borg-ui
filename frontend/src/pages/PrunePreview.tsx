import { useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  useLocation,
  useNavigate,
  useParams,
  useSearchParams,
  Link as RouterLink,
} from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'react-hot-toast'
import {
  Alert,
  Box,
  Breadcrumbs,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  Divider,
  Link,
  Paper,
  Skeleton,
  Stack,
  Typography,
  alpha,
  useTheme,
} from '@mui/material'
import { formatRelativeTime } from '../utils/dateUtils'
import { operationsAPI, repositoriesAPI } from '../services/api'
import PlanGate from '../components/shared/PlanGate'
import ArchiveSeriesHeatmap from '../components/archives/ArchiveSeriesHeatmap'
import PruneRetentionFields from '../components/prune/PruneRetentionFields'
import { DEFAULT_RETENTION } from '../components/prune/defaultRetention'
import PrunePreviewNumbers from '../components/prune/PrunePreviewNumbers'
import PruneCandidatesRanked from '../components/prune/PruneCandidatesRanked'
import PruneLostFilesPanel from '../components/prune/PruneLostFilesPanel'
import { PruneComparedPolicies } from '../components/prune/PruneComparedPolicies'
import { sameRetention } from '../components/prune/formatRetention'
import { dayVerdict, previewToHeatmap, sizeIntensity } from '../components/prune/previewHeatmap'
import type { PruneRetention, PrunePreviewResponse, PruneComparisonRow } from '../types/archives'

const toForm = (r: PruneComparisonRow['retention']): PruneRetention | null =>
  r ? { ...r, keep_within: r.keep_within ?? '' } : null

interface LocationState {
  retention?: PruneRetention
}

export default function PrunePreview() {
  const { t } = useTranslation()
  const theme = useTheme()
  const navigate = useNavigate()
  const location = useLocation()
  const { repositoryId: repositoryIdParam } = useParams()
  const repositoryId = Number(repositoryIdParam)

  const stateRetention = (location.state as LocationState | null)?.retention

  const { data: repositoriesData } = useQuery({
    queryKey: ['repositories'],
    queryFn: repositoriesAPI.getRepositories,
  })
  const repository = useMemo(
    () => repositoriesData?.data?.repositories?.find((r: { id: number }) => r.id === repositoryId),
    [repositoriesData, repositoryId]
  )

  const {
    data: defaultsData,
    isError: defaultsFailed,
    refetch: refetchDefaults,
  } = useQuery({
    queryKey: ['prune-retention-defaults', repositoryId],
    queryFn: () => repositoriesAPI.pruneRetentionDefaults(repositoryId).then((res) => res.data),
    enabled: !stateRetention && Number.isFinite(repositoryId),
  })
  const defaultRetention = useMemo<PruneRetention | null>(
    () =>
      defaultsData
        ? {
            keep_hourly: defaultsData.keep_hourly,
            keep_daily: defaultsData.keep_daily,
            keep_weekly: defaultsData.keep_weekly,
            keep_monthly: defaultsData.keep_monthly,
            keep_quarterly: defaultsData.keep_quarterly,
            keep_yearly: defaultsData.keep_yearly,
            keep_within: defaultsData.keep_within ?? '',
          }
        : null,
    [defaultsData]
  )
  const source = stateRetention || !defaultsData ? null : defaultsData

  const [searchParams] = useSearchParams()
  const candidateKey = searchParams.get('candidate')
  const queryClient = useQueryClient()
  // The refresh's operation id; polled until the operation ends, whatever
  // way it ends, so a skipped or failed comparison does not leave the page
  // "Comparing" for good.
  const [pendingOpId, setPendingOpId] = useState<number | null>(null)
  const comparisonQuery = useQuery({
    queryKey: ['prune-comparison', repositoryId],
    queryFn: () => repositoriesAPI.pruneComparison(repositoryId).then((res) => res.data),
    enabled: Number.isFinite(repositoryId),
  })
  const comparison = comparisonQuery.data ?? null
  const pendingOp = useQuery({
    queryKey: ['operation', pendingOpId],
    queryFn: () => operationsAPI.get(pendingOpId as number).then((res) => res.data),
    enabled: pendingOpId !== null,
    refetchInterval: 3000,
  })
  const pendingStatus = pendingOp.data?.status
  useEffect(() => {
    if (pendingOpId === null) return
    const ended = pendingStatus !== undefined && !['queued', 'running'].includes(pendingStatus)
    if (ended || pendingOp.isError) {
      setPendingOpId(null)
      queryClient.invalidateQueries({ queryKey: ['prune-comparison', repositoryId] })
    }
  }, [pendingOpId, pendingStatus, pendingOp.isError, queryClient, repositoryId])
  const refreshMutation = useMutation({
    mutationFn: () => repositoriesAPI.pruneComparisonRefresh(repositoryId),
    onSuccess: (res) => setPendingOpId(res.data.operation_id),
    onError: () => toast.error(t('prunePreview.compare.refreshFailed')),
  })
  const candidateRetention = useMemo(
    () =>
      candidateKey && comparison
        ? toForm(comparison.candidates.find((c) => c.key === candidateKey)?.retention ?? null)
        : null,
    [candidateKey, comparison]
  )

  const [retention, setRetention] = useState<PruneRetention>(stateRetention ?? DEFAULT_RETENTION)
  // The retention the shown preview was computed with. "Run prune now"
  // posts this, never the form, so an edit without a refresh cannot prune
  // with rules nobody previewed.
  const [previewedRetention, setPreviewedRetention] = useState<PruneRetention | null>(null)
  const [preview, setPreview] = useState<PrunePreviewResponse | null>(null)
  const [error, setError] = useState<{ status: number; key: string; log?: string } | null>(null)
  const [refreshedAt, setRefreshedAt] = useState<Date | null>(null)
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [logOpen, setLogOpen] = useState(false)

  const previewMutation = useMutation({
    mutationFn: (form: PruneRetention) => repositoriesAPI.prunePreview(repositoryId, form),
    onSuccess: (res, form) => {
      setPreview(res.data)
      setPreviewedRetention(form)
      setError(null)
      setRefreshedAt(new Date())
    },
    onError: (err: unknown) => {
      const e = err as {
        response?: {
          status: number
          data?: { detail?: { key: string; params?: { log?: string } } }
        }
      }
      const status = e.response?.status ?? 500
      const key = e.response?.data?.detail?.key ?? 'prunePreview.dryRunFailed'
      const log = e.response?.data?.detail?.params?.log
      setError({ status, key, log })
    },
  })

  const runPruneMutation = useMutation({
    mutationFn: (form: PruneRetention) =>
      repositoriesAPI.pruneRepository(repositoryId, { ...form, dry_run: false }),
    onSuccess: () => {
      toast.success(t('repositories.toasts.pruneStarted'))
      navigate(`/activity?repository_id=${repositoryId}`)
    },
    onError: () => {
      toast.error(t('repositories.toasts.pruneFailed'))
    },
  })

  // First preview, once per repository, with the retention the form is
  // prefilled with: the dialog's form when it sent us here, else the
  // loaded defaults. Reading the form state here would see the value from
  // before the defaults landed.
  const ranForRepoRef = useRef<number | null>(null)
  useEffect(() => {
    if (ranForRepoRef.current === repositoryId) return
    if (!Number.isFinite(repositoryId)) return
    if (candidateKey && !candidateRetention && comparisonQuery.isFetching) return
    const initial = stateRetention ?? candidateRetention ?? defaultRetention
    if (!initial) return
    ranForRepoRef.current = repositoryId
    setRetention(initial)
    previewMutation.mutate(initial)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    defaultRetention,
    stateRetention,
    repositoryId,
    candidateRetention,
    comparisonQuery.isFetching,
    candidateKey,
  ])

  // Until the prefill is known the form shows placeholder values that
  // nothing should preview or prune with.
  const ready = Boolean(stateRetention ?? defaultRetention)
  const dirty =
    previewedRetention !== null && JSON.stringify(retention) !== JSON.stringify(previewedRetention)

  const archives = useMemo(() => preview?.archives ?? [], [preview])
  const heatmapData = useMemo(() => previewToHeatmap(archives), [archives])
  const verdictOf = useMemo(() => dayVerdict(archives), [archives])
  const intensityOf = useMemo(() => sizeIntensity(archives), [archives])
  const byId = useMemo(() => new Map(archives.map((a) => [a.id, a])), [archives])

  const deletedCount = preview?.deleted_count ?? 0
  const keptCount = preview?.kept_count ?? 0

  const selectedKey = useMemo(() => {
    if (!previewedRetention || !comparison) return null
    return (
      comparison.candidates.find((c) => sameRetention(c.retention, previewedRetention))?.key ?? null
    )
  }, [comparison, previewedRetention])
  const editing =
    preview && previewedRetention && selectedKey === null
      ? {
          retention: previewedRetention,
          kept_count: preview.kept_count,
          deleted_count: preview.deleted_count,
          freed_at_least: preview.freed_at_least,
        }
      : null

  return (
    <Box sx={{ p: 3 }}>
      <Breadcrumbs sx={{ mb: 2 }}>
        <Link component={RouterLink} to="/repositories" underline="hover">
          {t('prunePreview.crumbRepositories')}
        </Link>
        <Typography color="text.secondary">{repository?.name ?? repositoryId}</Typography>
        <Typography color="text.primary">{t('prunePreview.title')}</Typography>
      </Breadcrumbs>

      <Box sx={{ display: 'flex', flexDirection: { xs: 'column', md: 'row' }, gap: 3 }}>
        <Paper variant="outlined" sx={{ p: 2, width: { xs: '100%', md: 300 }, flexShrink: 0 }}>
          <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 1 }}>
            {t('prunePreview.retention')}
          </Typography>
          {source && (
            <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1 }}>
              {source.source === 'plan'
                ? t('prunePreview.prefilledPlan', { name: source.plan_name })
                : source.source === 'last_prune'
                  ? t('prunePreview.prefilledLastPrune')
                  : t('prunePreview.prefilledDefault')}
            </Typography>
          )}
          {defaultsFailed && !stateRetention && (
            <Alert
              severity="error"
              sx={{ mb: 1 }}
              action={
                <Button size="small" color="inherit" onClick={() => refetchDefaults()}>
                  {t('prunePreview.retry')}
                </Button>
              }
            >
              {t('prunePreview.defaultsFailed')}
            </Alert>
          )}
          <PruneRetentionFields
            value={retention}
            onChange={setRetention}
            disabled={!ready || previewMutation.isPending}
          />
          {error?.key === 'backend.errors.prune.noKeepRule' && (
            <Alert severity="error" sx={{ mt: 1 }}>
              {t('prunePreview.noKeepRule')}
            </Alert>
          )}
          <Stack direction="row" spacing={1} sx={{ mt: 2 }}>
            <Button
              size="small"
              disabled={!ready}
              onClick={() => setRetention(stateRetention ?? defaultRetention ?? DEFAULT_RETENTION)}
            >
              {t('prunePreview.reset')}
            </Button>
            <Button
              size="small"
              variant="contained"
              disabled={!ready || previewMutation.isPending}
              onClick={() => previewMutation.mutate(retention)}
            >
              {t('prunePreview.refresh')}
            </Button>
          </Stack>
          {refreshedAt && (
            <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>
              {t('prunePreview.refreshedAt', {
                when: formatRelativeTime(refreshedAt.toISOString()),
              })}
            </Typography>
          )}
        </Paper>

        <Stack spacing={3} sx={{ flex: 1, minWidth: 0 }}>
          {error && error.key !== 'backend.errors.prune.noKeepRule' && (
            <Alert severity="error">
              {error.status === 502
                ? t('prunePreview.dryRunFailed')
                : t('prunePreview.previewFailed', { status: error.status })}
              {error.log && (
                <Box component="pre" sx={{ mt: 1, fontSize: '0.75rem', overflowX: 'auto' }}>
                  {error.log}
                </Box>
              )}
            </Alert>
          )}

          <PruneComparedPolicies
            comparison={comparison}
            editing={editing}
            selectedKey={selectedKey}
            pending={pendingOpId !== null}
            refreshDisabled={!ready || previewMutation.isPending}
            onSelect={(row) => {
              const form = toForm(row.retention)
              if (!form) return
              setRetention(form)
              previewMutation.mutate(form)
            }}
            onRefresh={() => refreshMutation.mutate()}
          />

          {previewMutation.isPending && !preview ? (
            <Stack spacing={1.5}>
              <Skeleton variant="rounded" height={100} />
              <Skeleton variant="rounded" height={200} />
            </Stack>
          ) : preview ? (
            <Box sx={{ opacity: previewMutation.isPending ? 0.6 : 1 }}>
              <PrunePreviewNumbers
                deletedCount={deletedCount}
                keptCount={keptCount}
                freedAtLeast={preview.freed_at_least}
                footprintBefore={preview.footprint_before}
                footprintAfterAtMost={preview.footprint_after_at_most}
              />

              <Paper variant="outlined" sx={{ p: 2, mt: 3 }}>
                <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 1.5 }}>
                  {t('prunePreview.heatmapTitle')}
                </Typography>
                <ArchiveSeriesHeatmap
                  data={heatmapData}
                  onSelectDay={(day) => {
                    const id = day.archive_ids[0]
                    if (id != null) navigate(`/archives/${repositoryId}/${id}`)
                  }}
                  onSelectArchive={(id) => navigate(`/archives/${repositoryId}/${id}`)}
                  cellColor={(day) => {
                    const v = verdictOf(day)
                    const intensity = intensityOf(day)
                    if (v === 'kept') return alpha(theme.palette.success.main, intensity)
                    if (v === 'deleted') return alpha(theme.palette.error.main, intensity)
                    if (v === 'mixed') return theme.palette.warning.main
                    return undefined
                  }}
                  cellLabel={(day) => {
                    const names = day.archive_ids
                      .map((id) => byId.get(id))
                      .filter(Boolean)
                      .map((a) =>
                        a!.verdict === 'kept'
                          ? t('prunePreview.cellKept', { name: a!.name, rule: a!.rule })
                          : t('prunePreview.cellDeleted', { name: a!.name })
                      )
                    return names.join(', ') || undefined
                  }}
                />
                <Stack direction="row" spacing={2} sx={{ mt: 1 }}>
                  <Typography variant="caption" color="success.main">
                    {t('prunePreview.legendKept')}
                  </Typography>
                  <Typography variant="caption" color="error.main">
                    {t('prunePreview.legendDeleted')}
                  </Typography>
                  <Typography variant="caption" color="warning.main">
                    {t('prunePreview.legendMixed')}
                  </Typography>
                </Stack>
              </Paper>

              <Paper variant="outlined" sx={{ p: 2, mt: 3 }}>
                <PruneCandidatesRanked
                  archives={archives}
                  partialMeasure={preview.partial_measure}
                  onOpen={(id) => navigate(`/archives/${repositoryId}/${id}`)}
                />
              </Paper>

              <Paper variant="outlined" sx={{ p: 2, mt: 3 }}>
                <PlanGate
                  feature="archive_history"
                  surface="prune_preview"
                  operation="view_lost_files"
                >
                  <PruneLostFilesPanel repositoryId={repositoryId} lost={preview.lost_files} />
                </PlanGate>
              </Paper>

              <Stack spacing={1} sx={{ mt: 3 }}>
                {preview.lost_files.incomplete && (
                  <Alert severity="warning">
                    {t('prunePreview.warnIncomplete', {
                      count: preview.lost_files.unindexed_archive_ids?.length ?? 0,
                    })}
                  </Alert>
                )}
                <Alert severity="info">{t('prunePreview.warnLowerBound')}</Alert>
                <Alert severity="info">{t('prunePreview.warnCrossSeries')}</Alert>
                {preview.partial_measure && (
                  <Alert severity="warning">
                    {t('prunePreview.remeasuredPartial', { cap: 50, count: deletedCount })}
                  </Alert>
                )}
              </Stack>

              <Divider sx={{ my: 2 }} />

              <Button size="small" onClick={() => setLogOpen((v) => !v)}>
                {t('prunePreview.showLog', { deleted: deletedCount, kept: keptCount })}
              </Button>
              {logOpen && (
                <Box
                  component="pre"
                  sx={{
                    mt: 1,
                    p: 1.5,
                    bgcolor: 'action.hover',
                    borderRadius: 1,
                    fontSize: '0.75rem',
                    overflowX: 'auto',
                  }}
                >
                  {preview.log}
                </Box>
              )}

              <Stack direction="row" spacing={1.5} sx={{ mt: 2 }}>
                <Button onClick={() => navigate(-1)}>{t('prunePreview.cancel')}</Button>
                <Button
                  variant="contained"
                  color="error"
                  onClick={() => setConfirmOpen(true)}
                  disabled={
                    deletedCount === 0 || dirty || previewMutation.isPending || error !== null
                  }
                >
                  {t('prunePreview.runNow', { count: deletedCount })}
                </Button>
              </Stack>
            </Box>
          ) : null}
        </Stack>
      </Box>

      <Dialog open={confirmOpen} onClose={() => setConfirmOpen(false)}>
        <DialogTitle>{t('prunePreview.confirmTitle', { count: deletedCount })}</DialogTitle>
        <DialogContent>
          <DialogContentText>{t('prunePreview.confirmBody')}</DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setConfirmOpen(false)}>{t('prunePreview.cancel')}</Button>
          <Button
            variant="contained"
            color="error"
            onClick={() => {
              setConfirmOpen(false)
              if (previewedRetention) runPruneMutation.mutate(previewedRetention)
            }}
          >
            {t('prunePreview.confirm')}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}

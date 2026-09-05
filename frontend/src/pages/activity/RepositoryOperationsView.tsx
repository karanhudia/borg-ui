import { useMemo, useState } from 'react'
import { Link as RouterLink } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import type { TFunction } from 'i18next'
import { useQuery } from '@tanstack/react-query'
import {
  Alert,
  Box,
  IconButton,
  Link,
  Stack,
  Tooltip,
  Typography,
  alpha,
  useTheme,
} from '@mui/material'
import { AlertCircle, ArrowLeft, FileText, RefreshCw } from 'lucide-react'
import { isToday, isYesterday } from 'date-fns'
import { activityAPI, repositoriesAPI } from '../../services/api'
import CategoryFilter from '../../components/activity/CategoryFilter'
import RunChainRow from '../../components/activity/RunChainRow'
import RunStatusIcon from '../../components/activity/RunStatusIcon'
import CategoryToken from '../../components/CategoryToken'
import TriggerSelect from '../../components/activity/TriggerSelect'
import RepositoryScopeSelect from '../../components/activity/RepositoryScopeSelect'
import LogViewerDialog from '../../components/LogViewerDialog'
import ErrorDetailsDialog from '../../components/ErrorDetailsDialog'
import EmptyStateCard from '../../components/EmptyStateCard'
import { formatDurationSeconds, parseBackendDate } from '../../utils/dateUtils'
import type { ActivityItem } from '../Activity'
import type { OperationCategory } from '../../types/operations'
import type { Repository } from '@/types'

interface RepositoryOperationsViewProps {
  repositoryId: number
}

function runTime(item: ActivityItem): Date | null {
  const raw = item.started_at ?? item.completed_at
  return raw ? parseBackendDate(raw) : null
}

function dayKey(date: Date | null): string {
  if (!date) return 'unknown'
  return `${date.getFullYear()}-${date.getMonth()}-${date.getDate()}`
}

function triggerSource(item: ActivityItem, t: TFunction): string {
  if (item.backup_plan_name)
    return t('activity.repositoryView.triggerSource.plan', { name: item.backup_plan_name })
  if (item.schedule_name)
    return t('activity.repositoryView.triggerSource.schedule', { name: item.schedule_name })
  const trigger = item.trigger ?? (item.triggered_by === 'schedule' ? 'schedule' : 'manual')
  return t(`activity.triggers.${trigger}`)
}

function duration(item: ActivityItem): string | null {
  if (!item.started_at || !item.completed_at) return null
  const seconds = Math.round(
    (parseBackendDate(item.completed_at).getTime() - parseBackendDate(item.started_at).getTime()) /
      1000
  )
  return formatDurationSeconds(Math.max(seconds, 0))
}

function RunRow({
  item,
  onLogs,
  onError,
}: {
  item: ActivityItem
  onLogs: (item: ActivityItem) => void
  onError: (item: ActivityItem) => void
}) {
  const { t } = useTranslation()
  const theme = useTheme()
  const time = runTime(item)
  const kind = item.kind ?? item.type
  const hasLogs = item.has_logs === true || !!item.log_file_path || item.status === 'running'
  const hasError = item.status === 'failed' && !!item.error_message
  const elapsed = duration(item)

  return (
    <Box
      data-testid="run-row"
      sx={{
        display: 'grid',
        gridTemplateColumns: {
          xs: 'auto auto minmax(0, 1fr) auto',
          md: '76px 20px minmax(180px, 1fr) minmax(0, 1.2fr) 90px 72px',
        },
        columnGap: 1.5,
        alignItems: 'start',
        py: 1.25,
        px: 1,
        borderRadius: 1.5,
        '&:hover': { bgcolor: alpha(theme.palette.text.primary, 0.03) },
      }}
    >
      <Typography
        variant="body2"
        noWrap
        sx={{ color: 'text.secondary', fontVariantNumeric: 'tabular-nums', pt: 0.25 }}
      >
        {time ? time.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : ''}
      </Typography>
      <Box sx={{ pt: 0.5 }}>
        <RunStatusIcon status={item.status} />
      </Box>
      <Box sx={{ minWidth: 0 }}>
        <Stack direction="row" spacing={1} sx={{ alignItems: 'center', flexWrap: 'wrap' }}>
          {item.category && <CategoryToken category={item.category} />}
          <Typography variant="body2" sx={{ fontWeight: 600 }}>
            {t(`operations.kind.${kind}`, { defaultValue: kind })}
          </Typography>
          <Typography variant="body2" sx={{ color: 'text.secondary' }}>
            {triggerSource(item, t)}
          </Typography>
        </Stack>
        <RunChainRow
          layout="stacked"
          operation={{
            id: item.id,
            kind: kind ?? '',
            status: item.status,
            followups: (item.followups ?? []).map((followup) => ({
              id: followup.id,
              kind: followup.kind ?? followup.type,
              status: followup.status,
              progress_current: followup.progress_current,
              progress_total: followup.progress_total,
            })),
          }}
        />
      </Box>
      <Typography
        variant="body2"
        noWrap
        sx={{ color: 'text.secondary', display: { xs: 'none', md: 'block' }, pt: 0.25 }}
        title={item.archive_name ?? undefined}
      >
        {item.archive_name ?? ''}
      </Typography>
      <Typography
        variant="body2"
        sx={{
          color: 'text.secondary',
          display: { xs: 'none', md: 'block' },
          pt: 0.25,
          fontVariantNumeric: 'tabular-nums',
        }}
      >
        {item.status === 'running' ? t('operations.status.running') : (elapsed ?? '')}
      </Typography>
      <Stack direction="row" spacing={0} sx={{ justifyContent: 'flex-end' }}>
        {hasError && (
          <Tooltip title={t('activity.repositoryView.errorDetails')}>
            <IconButton
              size="small"
              color="error"
              aria-label={t('activity.repositoryView.errorDetails')}
              onClick={() => onError(item)}
            >
              <AlertCircle size={16} />
            </IconButton>
          </Tooltip>
        )}
        {hasLogs && (
          <Tooltip title={t('activity.repositoryView.logs')}>
            <IconButton
              size="small"
              aria-label={t('activity.repositoryView.logs')}
              onClick={() => onLogs(item)}
            >
              <FileText size={16} />
            </IconButton>
          </Tooltip>
        )}
      </Stack>
    </Box>
  )
}

export default function RepositoryOperationsView({ repositoryId }: RepositoryOperationsViewProps) {
  const { t } = useTranslation()
  const [categoryFilter, setCategoryFilter] = useState<OperationCategory[]>([])
  const [triggerFilter, setTriggerFilter] = useState<string>('all')
  const [logJob, setLogJob] = useState<ActivityItem | null>(null)
  const [errorJob, setErrorJob] = useState<ActivityItem | null>(null)

  const { data: repositoriesData } = useQuery({
    queryKey: ['repositories'],
    queryFn: repositoriesAPI.getRepositories,
  })
  const repository: Repository | undefined = (repositoriesData?.data?.repositories ?? []).find(
    (repo: Repository) => repo.id === repositoryId
  )

  const {
    data: activities,
    isLoading,
    isError,
    refetch,
  } = useQuery({
    queryKey: ['activity', 'repository', repositoryId, categoryFilter, triggerFilter],
    queryFn: async () => {
      // The activity union has no repository parameter yet (spec 16), so the
      // page filters the newest 200 runs by repository on the client.
      const params: Record<string, unknown> = { limit: 200 }
      if (categoryFilter.length > 0) params.category = categoryFilter
      if (triggerFilter !== 'all') params.trigger = [triggerFilter]
      const response = await activityAPI.list(params)
      return response.data as ActivityItem[]
    },
    refetchInterval: 3000,
  })

  // Legacy job rows (backup, check, prune) carry the repository path and
  // name but no id, so match on any of the three.
  const runs = useMemo(
    () =>
      (activities ?? []).filter(
        (item) =>
          item.repository_id === repositoryId ||
          (repository != null &&
            ((item.repository_path != null && item.repository_path === repository.path) ||
              item.repository === repository.name))
      ),
    [activities, repository, repositoryId]
  )

  const groups = useMemo(() => {
    const byDay = new Map<string, { date: Date | null; items: ActivityItem[] }>()
    for (const item of runs) {
      const date = runTime(item)
      const key = dayKey(date)
      const group = byDay.get(key) ?? { date, items: [] }
      group.items.push(item)
      byDay.set(key, group)
    }
    return [...byDay.values()].sort((a, b) => (b.date?.getTime() ?? 0) - (a.date?.getTime() ?? 0))
  }, [runs])

  const dayLabel = (date: Date | null) => {
    if (!date) return ''
    if (isToday(date)) return t('activity.repositoryView.today')
    if (isYesterday(date)) return t('activity.repositoryView.yesterday')
    return date.toLocaleDateString([], { weekday: 'long', day: 'numeric', month: 'long' })
  }

  return (
    <Box>
      <Link
        component={RouterLink}
        to="/activity"
        underline="hover"
        sx={{ display: 'inline-flex', alignItems: 'center', gap: 0.5, mb: 1.5 }}
      >
        <ArrowLeft size={14} />
        {t('activity.repositoryView.back')}
      </Link>
      <Box
        sx={{
          display: 'flex',
          alignItems: 'flex-start',
          justifyContent: 'space-between',
          gap: 2,
          mb: 3,
        }}
      >
        <Box sx={{ minWidth: 0 }}>
          <Typography variant="h4" component="h1" sx={{ wordBreak: 'break-word' }}>
            {repository?.name ?? String(repositoryId)}
          </Typography>
          <Typography variant="body2" sx={{ color: 'text.secondary' }}>
            {t('activity.repositoryView.subtitle')}
          </Typography>
        </Box>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexShrink: 0 }}>
          <Box sx={{ width: { xs: 220, sm: 320 } }}>
            <RepositoryScopeSelect value={repositoryId} />
          </Box>
          <IconButton onClick={() => refetch()} aria-label={t('activity.actions.refresh')}>
            <RefreshCw size={20} />
          </IconButton>
        </Box>
      </Box>

      <Stack
        direction="row"
        spacing={1.5}
        useFlexGap
        sx={{ flexWrap: 'wrap', alignItems: 'center', mb: 3 }}
      >
        <CategoryFilter value={categoryFilter} onChange={setCategoryFilter} />
        <TriggerSelect value={triggerFilter} onChange={setTriggerFilter} />
      </Stack>

      {isError ? (
        <Alert severity="error">{t('activity.repositoryView.loadFailed')}</Alert>
      ) : !isLoading && groups.length === 0 ? (
        <EmptyStateCard
          icon={<FileText size={48} />}
          title={t('activity.empty.title')}
          description={t('activity.repositoryView.empty')}
        />
      ) : (
        <Stack spacing={3}>
          {groups.map((group) => (
            <Box key={dayKey(group.date)}>
              <Typography variant="subtitle2" sx={{ color: 'text.secondary', mb: 0.5, px: 1 }}>
                {dayLabel(group.date)}
              </Typography>
              <Box sx={{ borderTop: 1, borderColor: 'divider' }}>
                {group.items.map((item) => (
                  <RunRow
                    key={item.activity_key ?? `${item.type}-${item.id}`}
                    item={item}
                    onLogs={setLogJob}
                    onError={setErrorJob}
                  />
                ))}
              </Box>
            </Box>
          ))}
        </Stack>
      )}

      <LogViewerDialog job={logJob} open={Boolean(logJob)} onClose={() => setLogJob(null)} />
      <ErrorDetailsDialog
        job={errorJob}
        open={Boolean(errorJob)}
        onClose={() => setErrorJob(null)}
        onViewLogs={(job) => {
          setErrorJob(null)
          setLogJob(job)
        }}
      />
    </Box>
  )
}

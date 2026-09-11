import { useMemo, useState } from 'react'
import {
  Box,
  Chip,
  LinearProgress,
  Typography,
  alpha,
  keyframes,
  useTheme,
  type Theme,
} from '@mui/material'
import { Terminal } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import type { ActivityItem } from '../Activity'
import RepositoryCell from '../../components/RepositoryCell'
import RowActions, { type ActionButton } from '../../components/RowActions'
import { RunChainSummary } from '../../components/activity/RunChainRow'
import {
  chainOpensByDefault,
  hookLabel,
  nodeLabel,
  nodeProgress,
  stepSeconds,
} from '../../components/activity/runChainText'
import { buildFlow, type FlowNode } from '../../components/activity/runChainLanes'
import RunStatusIcon from '../../components/activity/RunStatusIcon'
import StatusBadge from '../../components/StatusBadge'
import { CATEGORY_ICONS, categoryColor } from '../../components/categoryStyle'
import { getSkipReasonLabel, getTransportLabel } from '../../components/jobs/jobLabels'
import { formatDurationSeconds, formatElapsedTime, parseBackendDate } from '../../utils/dateUtils'
import type { OperationCategory } from '../../types/operations'
import { ACTIVE_STATUSES, runChain, runDuration, runTime, runTitle } from './runs'
import { ENTRY_COLUMNS, metaGridSx } from './entryGrid'

const pulse = keyframes`
  0% { box-shadow: 0 0 0 0 var(--pulse-color); }
  70% { box-shadow: 0 0 0 8px transparent; }
  100% { box-shadow: 0 0 0 0 transparent; }
`

const enter = keyframes`
  from { opacity: 0; transform: translateY(4px); }
  to { opacity: 1; transform: none; }
`

function statusColor(theme: Theme, status: string): string {
  return (
    {
      completed: theme.palette.success.main,
      completed_with_warnings: theme.palette.warning.main,
      needs_backup: theme.palette.warning.main,
      running: theme.palette.primary.main,
      failed: theme.palette.error.main,
    }[status] ?? alpha(theme.palette.text.primary, 0.25)
  )
}

// The dot on the rail. Hollow while queued, pulsing while running; a step
// under a run is a smaller dot than the run itself.
function StatusNode({ status, small = false }: { status: string; small?: boolean }) {
  const theme = useTheme()
  const color = statusColor(theme, status)
  const running = status === 'running'
  const queued = status === 'pending' || status === 'queued'
  const size = small ? 7 : 10
  return (
    <Box
      aria-hidden
      sx={{
        width: size,
        height: size,
        borderRadius: '50%',
        bgcolor: queued ? 'background.paper' : color,
        border: queued ? `2px solid ${color}` : 'none',
        boxSizing: 'border-box',
        position: 'relative',
        zIndex: 1,
        boxShadow: `0 0 0 3px ${theme.palette.background.default}`,
        '--pulse-color': alpha(color, 0.45),
        ...(running && {
          animation: `${pulse} 1.6s ease-out infinite`,
          '@media (prefers-reduced-motion: reduce)': { animation: 'none' },
        }),
      }}
    />
  )
}

// What ran, as a category-coloured token. A hook script says which hook
// it was, not just "Script".
function KindToken({ item }: { item: ActivityItem }) {
  const { t } = useTranslation()
  const theme = useTheme()
  const category = (item.category ?? null) as OperationCategory | null
  const script = item.type === 'script_execution'
  // A script row, plan-level or per-backup, carries the same terminal
  // glyph as the hook rows under a backup, so scripts read alike everywhere.
  const Icon = script ? Terminal : category ? CATEGORY_ICONS[category] : null
  const color = category ? categoryColor(theme, category) : theme.palette.text.secondary
  const label = script && item.hook_type ? hookLabel(item.hook_type, t) : runTitle(item, t)
  return (
    <Box
      data-testid="run-kind"
      sx={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 0.625,
        px: 1,
        height: 24,
        borderRadius: 999,
        bgcolor: alpha(color, 0.12),
        color,
        fontSize: '0.75rem',
        fontWeight: 600,
        whiteSpace: 'nowrap',
        flexShrink: 0,
      }}
    >
      {Icon && <Icon size={12} />}
      {label}
    </Box>
  )
}

const timeSx = {
  color: 'text.secondary',
  fontVariantNumeric: 'tabular-nums',
  textAlign: 'right',
  pr: 0.5,
} as const

// One step of the run, on the same rail and time column as the runs
// themselves, so the journey reads as a timeline: when each hook, stage,
// and refresh step started, and how long it took.
function StepRow({ node }: { node: FlowNode }) {
  const { t } = useTranslation()
  const { op, role } = node
  const started = op.started_at ? parseBackendDate(op.started_at) : null
  const elapsed = stepSeconds(op)
  const progress = nodeProgress(op)
  const running = op.status === 'running'
  const muted = op.status === 'skipped' || op.status === 'cancelled'
  const hook = role === 'hook'
  return (
    <Box
      data-testid="run-step"
      data-role={role}
      data-status={op.status}
      sx={{
        display: 'grid',
        gridTemplateColumns: ENTRY_COLUMNS,
        columnGap: 1,
        alignItems: 'center',
        minHeight: 26,
        pr: 1,
      }}
    >
      <Typography variant="caption" sx={{ ...timeSx, fontSize: '0.6875rem' }}>
        {started
          ? started.toLocaleTimeString([], {
              hour: '2-digit',
              minute: '2-digit',
              second: '2-digit',
            })
          : ''}
      </Typography>
      <Box sx={{ display: 'flex', justifyContent: 'center' }}>
        <StatusNode status={op.status} small />
      </Box>
      <Box
        sx={{
          display: 'flex',
          alignItems: 'center',
          gap: 0.75,
          minWidth: 0,
          color: muted ? 'text.disabled' : op.status === 'failed' ? 'error.main' : 'text.primary',
        }}
      >
        {hook ? (
          <Terminal size={12} style={{ flexShrink: 0, opacity: 0.7 }} />
        ) : (
          <RunStatusIcon status={op.status} size={12} />
        )}
        <Typography
          variant="caption"
          noWrap
          sx={{ fontWeight: role === 'step' ? 500 : 600, lineHeight: 1.2 }}
        >
          {nodeLabel(node, t)}
        </Typography>
        {hook && op.name && (
          <Typography variant="caption" noWrap sx={{ color: 'text.secondary', lineHeight: 1.2 }}>
            {op.name}
          </Typography>
        )}
        {(progress || (elapsed != null && elapsed >= 1)) && (
          <Typography
            variant="caption"
            sx={{
              color: running ? 'primary.main' : 'text.secondary',
              fontVariantNumeric: 'tabular-nums',
              lineHeight: 1.2,
            }}
          >
            {progress ?? formatDurationSeconds(elapsed)}
          </Typography>
        )}
        {running && op.progress_message && (
          <Typography variant="caption" noWrap sx={{ color: 'text.secondary', lineHeight: 1.2 }}>
            {op.progress_message}
          </Typography>
        )}
      </Box>
    </Box>
  )
}

interface RunEntryProps {
  item: ActivityItem
  actions: ActionButton<ActivityItem>[]
  // The pinned repository view already names the repository in its
  // header, so entries there lead with what ran instead.
  showRepository: boolean
}

export default function RunEntry({ item, actions, showRepository }: RunEntryProps) {
  const { t } = useTranslation()
  const theme = useTheme()
  const time = runTime(item)
  const running = item.status === 'running'
  const active = ACTIVE_STATUSES.has(item.status)
  // The badge already says "Running", so a live row shows elapsed time only.
  const duration = running
    ? formatElapsedTime(item.started_at).replace(/^Running for /, '')
    : runDuration(item)
  const transport = getTransportLabel(item.execution_mode, item.route_strategy, t)
  const skipReason = getSkipReasonLabel(item, t)
  const percent = item.progress_percent ?? null
  const chain = useMemo(() => ({ ...runChain(item), label: runTitle(item, t) }), [item, t])
  const steps = useMemo(() => chain.followups ?? [], [chain])
  const flow = useMemo(() => buildFlow(chain, steps), [chain, steps])
  const [open, setOpen] = useState<boolean | null>(null)
  const expanded = open ?? chainOpensByDefault(steps)
  const isScript = item.type === 'script_execution' || item.type === 'package'
  const subject = isScript ? item.package_name || item.archive_name : item.archive_name

  return (
    <Box
      role="listitem"
      data-testid="run-entry"
      data-status={item.status}
      sx={{
        position: 'relative',
        py: 1.25,
        borderRadius: 2,
        animation: `${enter} 240ms ease-out both`,
        '@media (prefers-reduced-motion: reduce)': { animation: 'none' },
        '&:hover': { bgcolor: alpha(theme.palette.text.primary, 0.025) },
        '&:hover .run-actions': { opacity: 1 },
      }}
    >
      <Box sx={{ display: 'grid', gridTemplateColumns: ENTRY_COLUMNS, columnGap: 1, pr: 1 }}>
        <Typography variant="body2" sx={{ ...timeSx, pt: '3px', lineHeight: '18px' }}>
          {time ? time.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : ''}
        </Typography>

        <Box sx={{ display: 'flex', justifyContent: 'center', pt: '7px' }}>
          <StatusNode status={item.status} />
        </Box>

        <Box sx={{ minWidth: 0 }}>
          <Box
            sx={{
              display: 'flex',
              flexWrap: 'wrap',
              alignItems: 'center',
              columnGap: 1,
              rowGap: 0.75,
            }}
          >
            {showRepository ? (
              <Box sx={{ minWidth: 0, flex: '1 1 200px', maxWidth: 360 }}>
                {isScript || !item.repository_path ? (
                  <Typography variant="body2" sx={{ fontWeight: 600 }} noWrap>
                    {subject || item.repository || t('common.unknown')}
                  </Typography>
                ) : (
                  <RepositoryCell
                    repositoryName={item.repository || item.repository_path}
                    repositoryPath={item.repository_path}
                    withIcon={false}
                  />
                )}
              </Box>
            ) : (
              <KindToken item={item} />
            )}
            {!showRepository && subject && (
              <Typography
                variant="body2"
                noWrap
                title={subject}
                sx={{ fontWeight: 600, flex: '0 1 auto', minWidth: 0, maxWidth: 320 }}
              >
                {subject}
              </Typography>
            )}
            {showRepository && <KindToken item={item} />}
            <Box sx={metaGridSx(actions.length)}>
              <Box sx={{ minWidth: 0 }}>
                <StatusBadge status={item.status} tooltip={skipReason || undefined} />
              </Box>
              <Box sx={{ minWidth: 0 }}>
                {transport && <Chip size="small" variant="outlined" label={transport} />}
              </Box>
              <Typography
                variant="body2"
                sx={{
                  color: 'text.secondary',
                  fontVariantNumeric: 'tabular-nums',
                  textAlign: 'right',
                }}
              >
                {duration ?? ''}
              </Typography>
              <Box
                className="run-actions"
                sx={{
                  display: 'flex',
                  justifyContent: 'flex-end',
                  opacity: { xs: 1, md: 0.55 },
                  transition: 'opacity 140ms ease',
                  '&:focus-within': { opacity: 1 },
                }}
              >
                <RowActions row={item} actions={actions} iconOpacity={1} />
              </Box>
            </Box>
          </Box>

          {active && (
            <Box sx={{ mt: 1, maxWidth: 520 }}>
              <LinearProgress
                variant={running && percent != null ? 'determinate' : 'indeterminate'}
                value={percent ?? undefined}
                sx={{
                  height: 4,
                  borderRadius: 999,
                  bgcolor: alpha(theme.palette.primary.main, 0.12),
                  '@media (prefers-reduced-motion: reduce)': {
                    '& .MuiLinearProgress-bar': { animation: 'none' },
                  },
                }}
              />
              {(item.progress_message || percent != null) && (
                <Typography
                  variant="caption"
                  sx={{ color: 'text.secondary', display: 'block', mt: 0.5 }}
                >
                  {[percent != null ? `${Math.round(percent)}%` : null, item.progress_message]
                    .filter(Boolean)
                    .join(' · ')}
                </Typography>
              )}
            </Box>
          )}

          {steps.length > 0 && (
            <Box sx={{ mt: 0.75 }}>
              <RunChainSummary
                steps={steps}
                expanded={expanded}
                onToggle={() => setOpen(!expanded)}
              />
            </Box>
          )}
        </Box>
      </Box>

      {steps.length > 0 && expanded && (
        <Box data-testid="run-steps" sx={{ mt: 0.5 }}>
          {flow.map((node, index) => (
            <StepRow key={`${node.role}-${node.op.id ?? index}`} node={node} />
          ))}
        </Box>
      )}
    </Box>
  )
}

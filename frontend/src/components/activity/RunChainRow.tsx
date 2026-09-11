import { useMemo, useState } from 'react'
import { Box, ButtonBase, Typography, alpha, keyframes, useTheme } from '@mui/material'
import { ChevronDown, ChevronRight, Terminal } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import RunStatusIcon from './RunStatusIcon'
import { buildFlow, isHook, type FlowNode } from './runChainLanes'
import {
  ACTIVE,
  chainOpensByDefault,
  chainSeconds,
  nodeLabel,
  nodeProgress,
  stepSeconds,
  useStepStatusColor,
} from './runChainText'
import { formatDurationSeconds } from '../../utils/dateUtils'

export interface RunChainOperation {
  id?: number | string
  kind: string
  // Activity type; `script_execution` marks a hook script that ran around
  // the operation rather than a step of its chain.
  type?: string | null
  status: string
  // Which operation this step ran after. Steps a stage (prune, compact)
  // enqueued for itself ride under that stage; anything else rides under
  // the run's root. Missing on legacy rows, which all fall under the root.
  trigger?: string | null
  depends_on_id?: number | null
  started_at?: string | null
  completed_at?: string | null
  progress_current?: number | null
  progress_total?: number | null
  progress_message?: string | null
  // Hook scripts: which hook, and the script's name.
  hook_type?: string | null
  name?: string | null
  // A ready-made title for the node; otherwise the kind's own label.
  label?: string | null
  followups?: RunChainOperation[]
}

const pulse = keyframes`
  0%, 100% { opacity: 1; }
  50% { opacity: 0.35; }
`

function StatusBar({ steps }: { steps: RunChainOperation[] }) {
  const color = useStepStatusColor()
  return (
    <Box aria-hidden sx={{ display: 'flex', gap: '2px', alignItems: 'center', flexShrink: 0 }}>
      {steps.map((step, index) => (
        <Box
          key={step.id ?? index}
          sx={{
            width: 9,
            height: 5,
            borderRadius: 999,
            bgcolor: color(step.status),
            ...(step.status === 'running' && { animation: `${pulse} 1.2s ease-in-out infinite` }),
          }}
        />
      ))}
    </Box>
  )
}

interface RunChainSummaryProps {
  steps: RunChainOperation[]
  expanded: boolean
  onToggle: () => void
}

// The one-line strip that folds a chain: a segment per step coloured by
// status, the count, a verdict, and how long the steps took.
export function RunChainSummary({ steps, expanded, onToggle }: RunChainSummaryProps) {
  const { t } = useTranslation()
  const allSucceeded = !chainOpensByDefault(steps)
  const failed = steps.filter((step) => step.status === 'failed').length
  const active = steps.filter((step) => ACTIVE.has(step.status)).length
  const total = chainSeconds(steps.filter((step) => !isHook(step)))
  const summary = allSucceeded
    ? t('activity.runChain.allSucceeded')
    : [
        failed > 0 && t('activity.runChain.failed', { count: failed }),
        active > 0 && t('activity.runChain.active', { count: active }),
      ]
        .filter(Boolean)
        .join(' · ')
  const Chevron = expanded ? ChevronDown : ChevronRight
  return (
    <ButtonBase
      onClick={onToggle}
      aria-expanded={expanded}
      sx={{
        display: 'flex',
        alignItems: 'center',
        gap: 1,
        flexWrap: 'wrap',
        rowGap: 0.5,
        borderRadius: 1,
        px: 0.5,
        py: 0.25,
        mx: -0.5,
        color: 'text.secondary',
        '&:hover': { bgcolor: (theme) => alpha(theme.palette.text.primary, 0.04) },
      }}
    >
      <Chevron size={14} aria-hidden />
      <StatusBar steps={steps} />
      <Typography
        variant="caption"
        sx={{ fontWeight: 600, color: 'text.primary', lineHeight: 1, whiteSpace: 'nowrap' }}
      >
        {t('activity.followupsCollapsed', { count: steps.length })}
      </Typography>
      <Typography variant="caption" sx={{ lineHeight: 1, whiteSpace: 'nowrap' }}>
        {summary}
        {total != null && total >= 1 && ` · ${formatDurationSeconds(total)}`}
      </Typography>
    </ButtonBase>
  )
}

function Node({ node }: { node: FlowNode }) {
  const { t } = useTranslation()
  const theme = useTheme()
  const { op, role } = node
  const elapsed = stepSeconds(op)
  const running = op.status === 'running'
  const failed = op.status === 'failed'
  const muted = op.status === 'skipped' || op.status === 'cancelled'
  const progress = nodeProgress(op)
  const hook = role === 'hook'
  const filled = role !== 'step'
  const tint = failed
    ? theme.palette.error.main
    : running
      ? theme.palette.primary.main
      : theme.palette.text.primary
  return (
    <Box
      data-testid={role === 'root' ? 'run-chain-root' : 'run-chain-followup'}
      data-role={role}
      data-status={op.status}
      sx={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 0.625,
        px: 0.875,
        height: 24,
        borderRadius: 999,
        border: 1,
        borderColor: running
          ? alpha(theme.palette.primary.main, 0.4)
          : filled
            ? 'transparent'
            : theme.palette.divider,
        bgcolor: running
          ? alpha(theme.palette.primary.main, 0.08)
          : filled
            ? alpha(tint, failed ? 0.1 : 0.07)
            : 'transparent',
        color: muted ? 'text.disabled' : failed ? 'error.main' : 'text.primary',
        whiteSpace: 'nowrap',
      }}
    >
      {hook ? (
        <Terminal size={12} style={{ flexShrink: 0, opacity: 0.7 }} />
      ) : (
        <RunStatusIcon status={op.status} size={12} />
      )}
      <Typography
        variant="caption"
        sx={{ lineHeight: 1, fontWeight: filled || running ? 600 : 500 }}
      >
        {nodeLabel(node, t)}
      </Typography>
      {hook && op.name && (
        <Typography variant="caption" sx={{ lineHeight: 1, color: 'text.secondary' }}>
          {op.name}
        </Typography>
      )}
      {hook && <RunStatusIcon status={op.status} size={12} />}
      {(progress || (elapsed != null && elapsed >= 1)) && (
        <Typography
          variant="caption"
          sx={{
            lineHeight: 1,
            color: running ? 'primary.main' : 'text.secondary',
            fontVariantNumeric: 'tabular-nums',
          }}
        >
          {progress ?? formatDurationSeconds(elapsed)}
        </Typography>
      )}
    </Box>
  )
}

interface RunChainRowProps {
  operation: RunChainOperation
}

// The chain under a table row: the summary strip, and when open the run as
// one left-to-right flow. The Activity timeline uses the same summary but
// lays the steps out vertically on its own rail (see RunEntry).
export default function RunChainRow({ operation }: RunChainRowProps) {
  const followups = operation.followups
  const steps = useMemo(() => followups ?? [], [followups])
  const flow = useMemo(() => buildFlow(operation, steps), [operation, steps])
  const [open, setOpen] = useState<boolean | null>(null)
  const expanded = open ?? chainOpensByDefault(steps)

  if (steps.length === 0) return null

  return (
    <Box sx={{ pt: 0.25, pb: 0.25 }}>
      <RunChainSummary steps={steps} expanded={expanded} onToggle={() => setOpen(!expanded)} />
      {expanded && (
        <Box
          data-testid="run-chain-flow"
          sx={{ mt: 1, display: 'flex', alignItems: 'center', flexWrap: 'wrap', rowGap: 0.75 }}
        >
          {flow.map((node, index) => (
            <Box
              key={`${node.role}-${node.op.id ?? index}`}
              sx={{ display: 'flex', alignItems: 'center' }}
            >
              {index > 0 && (
                <Box aria-hidden sx={{ width: 14, borderTop: 1, borderColor: 'divider' }} />
              )}
              <Node node={node} />
            </Box>
          ))}
        </Box>
      )}
    </Box>
  )
}

import { alpha, useTheme } from '@mui/material'
import type { TFunction } from 'i18next'
import type { RunChainOperation } from './RunChainRow'
import type { FlowNode } from './runChainLanes'
import { parseBackendDate } from '../../utils/dateUtils'

export const SUCCEEDED = new Set(['completed', 'completed_with_warnings', 'skipped'])
export const ACTIVE = new Set(['running', 'pending', 'queued'])

export function stepSeconds(step: RunChainOperation): number | null {
  if (!step.started_at || !step.completed_at) return null
  const ms =
    parseBackendDate(step.completed_at).getTime() - parseBackendDate(step.started_at).getTime()
  return Math.max(Math.round(ms / 1000), 0)
}

// Elapsed from the first step that started to the last that finished. Null
// while any step still runs, so the header never shows a stale total.
export function chainSeconds(steps: RunChainOperation[]): number | null {
  let start = Infinity
  let end = -Infinity
  for (const step of steps) {
    if (!step.started_at) continue
    if (!step.completed_at) return null
    start = Math.min(start, parseBackendDate(step.started_at).getTime())
    end = Math.max(end, parseBackendDate(step.completed_at).getTime())
  }
  return Number.isFinite(start) && Number.isFinite(end)
    ? Math.max(Math.round((end - start) / 1000), 0)
    : null
}

// A finished, healthy chain folds away; anything still moving or broken
// stays open so the row says what is happening without a click.
export function chainOpensByDefault(steps: RunChainOperation[]): boolean {
  return !steps.every((step) => SUCCEEDED.has(step.status))
}

const HOOK_LABEL_KEYS: Record<string, string> = {
  'pre-backup': 'activity.hook.pre',
  'post-backup': 'activity.hook.post',
  'source-pre-backup': 'activity.hook.sourcePre',
  'source-post-backup': 'activity.hook.sourcePost',
}

export function hookLabel(hookType: string | null | undefined, t: TFunction) {
  return t(HOOK_LABEL_KEYS[hookType ?? ''] ?? 'activity.hook.other', {
    defaultValue: hookType ?? '',
  })
}

function capitalize(value: string): string {
  return value ? value.charAt(0).toUpperCase() + value.slice(1) : value
}

export function nodeLabel(node: FlowNode, t: TFunction): string {
  const { op, role } = node
  if (role === 'hook') return hookLabel(op.hook_type, t)
  return op.label ?? capitalize(t(`operations.kind.${op.kind}`, { defaultValue: op.kind }))
}

export function nodeProgress(op: RunChainOperation): string | null {
  return op.status === 'running' && op.progress_current != null && op.progress_total != null
    ? `${op.progress_current}/${op.progress_total}`
    : null
}

export function useStepStatusColor() {
  const theme = useTheme()
  return (status: string): string =>
    ({
      completed: theme.palette.success.main,
      completed_with_warnings: theme.palette.warning.main,
      running: theme.palette.primary.main,
      failed: theme.palette.error.main,
    })[status] ?? alpha(theme.palette.text.primary, 0.18)
}

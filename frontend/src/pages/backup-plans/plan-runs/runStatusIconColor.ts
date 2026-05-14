import { isActiveRun } from '../runStatus'

export function runStatusIconColor(status?: string): string {
  if (status === 'completed') return 'success.main'
  if (status === 'completed_with_warnings' || status === 'partial' || status === 'skipped')
    return 'warning.main'
  if (status === 'failed' || status === 'cancelled') return 'error.main'
  if (isActiveRun(status)) return 'primary.main'
  return 'text.disabled'
}

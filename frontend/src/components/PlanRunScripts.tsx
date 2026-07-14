import { Box, Button, Chip, Stack, Typography } from '@mui/material'
import { Eye, FileText } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import type { BackupPlanRun, BackupPlanScriptExecution } from '../types'
import { canViewScriptLogs, type BackupPlanRunLogJob } from './planRunScriptLogs'

export type { BackupPlanRunLogJob } from './planRunScriptLogs'

function scriptStatusColor(
  status?: string
): 'default' | 'primary' | 'success' | 'warning' | 'error' {
  if (status === 'completed') return 'success'
  if (status === 'completed_with_warnings' || status === 'warning') return 'warning'
  if (status === 'failed' || status === 'cancelled' || status === 'canceled') return 'error'
  if (status === 'running' || status === 'pending') return 'primary'
  return 'default'
}

function formatScriptStatus(status?: string): string {
  if (!status) return ''
  return status
    .split('_')
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ')
}

export function ScriptExecutionRow({
  execution,
  onViewLogs,
}: {
  execution: BackupPlanScriptExecution
  onViewLogs: (job: BackupPlanRunLogJob) => void
}) {
  const { t } = useTranslation()
  const hookLabel =
    execution.hook_type === 'pre-backup'
      ? t('backupPlans.runsDialog.prePlanScript')
      : execution.hook_type === 'post-backup'
        ? t('backupPlans.runsDialog.postPlanScript')
        : execution.hook_type || t('backupPlans.runsDialog.planScript')
  const statusLabel = t(`backupPlans.statuses.${execution.status}`, {
    defaultValue: formatScriptStatus(execution.status),
  })

  return (
    <Box
      sx={{
        border: 1,
        borderColor: 'divider',
        borderRadius: 1,
        p: 1.5,
        bgcolor: 'background.paper',
      }}
    >
      <Stack
        direction={{ xs: 'column', sm: 'row' }}
        spacing={1}
        alignItems={{ xs: 'flex-start', sm: 'center' }}
        justifyContent="space-between"
      >
        <Stack direction="row" spacing={1} alignItems="center" sx={{ minWidth: 0 }}>
          <Box sx={{ color: 'text.secondary', display: 'flex', flexShrink: 0 }}>
            <FileText size={16} />
          </Box>
          <Box sx={{ minWidth: 0 }}>
            <Typography variant="subtitle2" noWrap>
              {hookLabel}: {execution.script_name}
            </Typography>
            <Stack direction="row" spacing={1.5} flexWrap="wrap" useFlexGap>
              {execution.exit_code !== null && execution.exit_code !== undefined && (
                <Typography variant="caption" color="text.secondary">
                  {t('backupPlans.runsDialog.exitCode', { code: execution.exit_code })}
                </Typography>
              )}
              {execution.execution_time !== null && execution.execution_time !== undefined && (
                <Typography variant="caption" color="text.secondary">
                  {t('backupPlans.runsDialog.scriptDuration', {
                    seconds: execution.execution_time.toFixed(2),
                  })}
                </Typography>
              )}
            </Stack>
          </Box>
        </Stack>
        <Stack direction="row" spacing={1} alignItems="center">
          <Chip size="small" label={statusLabel} color={scriptStatusColor(execution.status)} />
          {canViewScriptLogs(execution) && (
            <Button
              size="small"
              variant="text"
              startIcon={<Eye size={14} />}
              onClick={() =>
                onViewLogs({
                  id: execution.id,
                  status: execution.status,
                  type: 'script_execution',
                  has_logs: execution.has_logs,
                })
              }
            >
              {t('backupPlans.runsDialog.viewLogs')}
            </Button>
          )}
        </Stack>
      </Stack>
      {execution.error_message && (
        <Typography variant="caption" color="error" sx={{ mt: 1, display: 'block' }}>
          {execution.error_message}
        </Typography>
      )}
    </Box>
  )
}

// The "Plan scripts" section of a run: lists each pre/post hook execution with
// its status and a log link. Renders nothing when the run has no hooks.
export function PlanRunScriptsSection({
  run,
  onViewLogs,
  title,
}: {
  run: BackupPlanRun
  onViewLogs: (job: BackupPlanRunLogJob) => void
  title?: string
}) {
  const { t } = useTranslation()
  const executions = run.script_executions
  if (!executions || executions.length === 0) return null
  return (
    <Stack spacing={1.25}>
      <Typography variant="subtitle2" fontWeight={700}>
        {title ?? t('backupPlans.runsDialog.planScripts')}
      </Typography>
      {executions.map((execution) => (
        <ScriptExecutionRow key={execution.id} execution={execution} onViewLogs={onViewLogs} />
      ))}
    </Stack>
  )
}

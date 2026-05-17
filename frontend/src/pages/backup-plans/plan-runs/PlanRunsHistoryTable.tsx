import {
  alpha,
  Box,
  IconButton,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Tooltip,
  Typography,
} from '@mui/material'
import { Ban, Eye } from 'lucide-react'
import type { TFunction } from 'i18next'

import { type BackupPlanRunLogJob } from '../../../components/BackupPlanRunsPanel'
import { formatDateTimeFull, formatRelativeTime, formatTimeRange } from '../../../utils/dateUtils'
import type { BackupPlanRun } from '../../../types'
import { formatRunStatus, isActiveRun } from '../runStatus'
import { findFirstLogJobForRun } from './findFirstLogJobForRun'
import { RunStatusLeadIcon } from './RunStatusLeadIcon'
import { runStatusIconColor } from './runStatusIconColor'

interface PlanRunsHistoryTableProps {
  runs: BackupPlanRun[]
  cancelling: number | null
  onViewLogs: (job: BackupPlanRunLogJob) => void
  onCancel: (runId: number) => void
  t: TFunction
}

export function PlanRunsHistoryTable({
  runs,
  cancelling,
  onViewLogs,
  onCancel,
  t,
}: PlanRunsHistoryTableProps) {
  const formatStatusLabel = (status?: string) =>
    status
      ? t(`backupPlans.statuses.${status}`, { defaultValue: formatRunStatus(status) })
      : t('backupPlans.statuses.unknown')

  if (runs.length === 0) {
    return (
      <Box sx={{ px: 3, py: 2 }}>
        <Typography variant="caption" color="text.disabled">
          {t('backupPlans.runsTable.empty', { defaultValue: 'No past runs yet.' })}
        </Typography>
      </Box>
    )
  }

  return (
    <TableContainer>
      <Table size="small">
        <TableHead>
          <TableRow>
            <TableCell sx={{ width: 64, fontSize: '0.7rem' }}>
              {t('backupPlans.runsTable.columns.run', { defaultValue: 'Run' })}
            </TableCell>
            <TableCell sx={{ fontSize: '0.7rem' }}>
              {t('backupPlans.runsTable.columns.started', { defaultValue: 'Started' })}
            </TableCell>
            <TableCell sx={{ fontSize: '0.7rem' }}>
              {t('backupPlans.runsTable.columns.status', { defaultValue: 'Status' })}
            </TableCell>
            <TableCell sx={{ fontSize: '0.7rem' }}>
              {t('backupPlans.runsTable.columns.duration', { defaultValue: 'Duration' })}
            </TableCell>
            <TableCell align="right" sx={{ width: 80, fontSize: '0.7rem' }}>
              {t('backupPlans.runsTable.columns.actions', { defaultValue: 'Actions' })}
            </TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {runs.map((run) => {
            const startedAt = run.started_at || run.created_at
            const logJob = findFirstLogJobForRun(run)
            const active = isActiveRun(run.status)

            return (
              <TableRow key={run.id} hover>
                <TableCell
                  sx={{
                    fontFamily: '"JetBrains Mono","Fira Code",ui-monospace,monospace',
                    fontSize: '0.78rem',
                    color: 'text.secondary',
                  }}
                >
                  #{run.id}
                </TableCell>
                <TableCell>
                  {startedAt ? (
                    <Tooltip title={formatDateTimeFull(startedAt)} arrow>
                      <Typography
                        variant="body2"
                        color="text.secondary"
                        sx={{ cursor: 'help', display: 'inline-block' }}
                      >
                        {formatRelativeTime(startedAt)}
                      </Typography>
                    </Tooltip>
                  ) : (
                    <Typography variant="body2" color="text.disabled">
                      —
                    </Typography>
                  )}
                </TableCell>
                <TableCell>
                  <Stack direction="row" spacing={0.5} alignItems="center">
                    <Box
                      sx={{
                        display: 'flex',
                        color: runStatusIconColor(run.status),
                        lineHeight: 0,
                      }}
                    >
                      <RunStatusLeadIcon status={run.status} />
                    </Box>
                    <Typography variant="body2">{formatStatusLabel(run.status)}</Typography>
                  </Stack>
                </TableCell>
                <TableCell>
                  <Typography
                    variant="body2"
                    color="text.secondary"
                    sx={{
                      fontFamily: '"JetBrains Mono","Fira Code",ui-monospace,monospace',
                      fontSize: '0.78rem',
                    }}
                  >
                    {formatTimeRange(run.started_at, run.completed_at, run.status)}
                  </Typography>
                </TableCell>
                <TableCell align="right">
                  <Stack direction="row" spacing={0.25} justifyContent="flex-end">
                    {logJob && (
                      <Tooltip
                        title={t('backupPlans.runsDialog.viewLogs', { defaultValue: 'View logs' })}
                        arrow
                      >
                        <IconButton
                          size="small"
                          onClick={() => onViewLogs(logJob)}
                          aria-label={t('backupPlans.runsDialog.viewLogs', {
                            defaultValue: 'View logs',
                          })}
                          sx={{
                            width: 28,
                            height: 28,
                            color: 'info.main',
                            '&:hover': {
                              bgcolor: (theme) => alpha(theme.palette.info.main, 0.12),
                            },
                          }}
                        >
                          <Eye size={15} />
                        </IconButton>
                      </Tooltip>
                    )}
                    {active && (
                      <Tooltip
                        title={t('backupPlans.runsPanel.cancelRun', {
                          defaultValue: 'Cancel run',
                        })}
                        arrow
                      >
                        <IconButton
                          size="small"
                          onClick={() => onCancel(run.id)}
                          disabled={cancelling === run.id}
                          aria-label={t('backupPlans.runsPanel.cancelRun', {
                            defaultValue: 'Cancel run',
                          })}
                          sx={{
                            width: 28,
                            height: 28,
                            color: 'warning.main',
                            '&:hover': {
                              bgcolor: (theme) => alpha(theme.palette.warning.main, 0.12),
                            },
                          }}
                        >
                          <Ban size={15} />
                        </IconButton>
                      </Tooltip>
                    )}
                  </Stack>
                </TableCell>
              </TableRow>
            )
          })}
        </TableBody>
      </Table>
    </TableContainer>
  )
}

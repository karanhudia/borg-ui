import { Box, Button, Typography, alpha, useTheme } from '@mui/material'
import { useTranslation } from 'react-i18next'
import { HardDrive, Plus, Pencil } from 'lucide-react'
import { formatCronHuman } from '../utils/dateUtils'

export interface RepoScheduleRowProps {
  repositoryId: number
  repositoryName: string
  repositoryPath?: string | null
  checkCron: string | null
  checkTimezone?: string | null
  checkEnabled?: boolean
  restoreCron: string | null
  restoreTimezone?: string | null
  restoreEnabled?: boolean
  onEditCheck: (repoId: number) => void
  onEditRestore: (repoId: number) => void
  canManage: boolean
}

type EventKind = 'check' | 'restore'

interface ScheduleLineProps {
  kind: EventKind
  label: string
  cron: string | null
  timezone?: string | null
  enabled: boolean
  onClick: () => void
  canManage: boolean
  setLabel: string
  editLabel: string
  pausedLabel: string
}

function ScheduleLine({
  kind,
  label,
  cron,
  timezone,
  enabled,
  onClick,
  canManage,
  setLabel,
  editLabel,
  pausedLabel,
}: ScheduleLineProps) {
  const theme = useTheme()
  const isDark = theme.palette.mode === 'dark'
  const accent = kind === 'check' ? theme.palette.warning.main : theme.palette.info.main
  const hasSchedule = Boolean(cron)
  // A schedule that has a cron but is toggled off is shown muted with a
  // "Paused" indicator so it's clear the row exists but isn't running.
  const isPaused = hasSchedule && !enabled

  return (
    <Box
      sx={{
        display: 'flex',
        alignItems: 'center',
        gap: 1,
        py: 0.5,
        minWidth: 0,
      }}
    >
      <Box
        sx={{
          width: 7,
          height: 7,
          borderRadius: '50%',
          bgcolor: hasSchedule && !isPaused ? accent : 'transparent',
          border: hasSchedule && !isPaused ? 'none' : '1px dashed',
          borderColor: isPaused
            ? alpha(accent, 0.5)
            : isDark
              ? alpha('#fff', 0.25)
              : alpha('#000', 0.25),
          flexShrink: 0,
        }}
      />
      <Typography
        variant="caption"
        sx={{
          fontWeight: 700,
          textTransform: 'uppercase',
          letterSpacing: '0.04em',
          fontSize: '0.65rem',
          color: hasSchedule && !isPaused ? accent : 'text.secondary',
          width: 56,
          flexShrink: 0,
        }}
      >
        {label}
      </Typography>
      {hasSchedule ? (
        <Typography
          variant="body2"
          sx={{
            flex: 1,
            minWidth: 0,
            color: isPaused ? 'text.disabled' : 'text.primary',
            textDecoration: isPaused ? 'line-through' : 'none',
          }}
          noWrap
        >
          {formatCronHuman(cron as string)}
          {isPaused && (
            <Typography
              component="span"
              variant="caption"
              sx={{
                ml: 0.75,
                color: accent,
                fontWeight: 700,
                textTransform: 'uppercase',
                letterSpacing: '0.04em',
                textDecoration: 'none',
              }}
            >
              {pausedLabel}
            </Typography>
          )}
          {!isPaused && timezone && (
            <Typography component="span" variant="caption" color="text.secondary" sx={{ ml: 0.75 }}>
              {timezone}
            </Typography>
          )}
        </Typography>
      ) : (
        <Typography
          variant="body2"
          sx={{ flex: 1, minWidth: 0, fontStyle: 'italic' }}
          color="text.disabled"
          noWrap
        >
          {setLabel}
        </Typography>
      )}
      {canManage && (
        <Button
          size="small"
          variant="text"
          startIcon={hasSchedule ? <Pencil size={13} /> : <Plus size={13} />}
          onClick={onClick}
          sx={{
            fontSize: '0.7rem',
            fontWeight: 600,
            py: 0.25,
            px: 1,
            minWidth: 'auto',
            color: hasSchedule ? 'text.secondary' : accent,
            '&:hover': {
              bgcolor: alpha(accent, isDark ? 0.12 : 0.08),
              color: accent,
            },
          }}
        >
          {hasSchedule ? editLabel : setLabel}
        </Button>
      )}
    </Box>
  )
}

const RepoScheduleRow: React.FC<RepoScheduleRowProps> = ({
  repositoryId,
  repositoryName,
  repositoryPath,
  checkCron,
  checkTimezone,
  checkEnabled = true,
  restoreCron,
  restoreTimezone,
  restoreEnabled = true,
  onEditCheck,
  onEditRestore,
  canManage,
}) => {
  const { t } = useTranslation()
  const theme = useTheme()
  const isDark = theme.palette.mode === 'dark'

  return (
    <Box
      sx={{
        py: 1,
        pl: 1,
        pr: 0.5,
        borderTop: '1px solid',
        borderColor: isDark ? alpha('#fff', 0.06) : alpha('#000', 0.06),
        '&:first-of-type': { borderTop: 'none' },
      }}
    >
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75, mb: 0.25 }}>
        <HardDrive size={14} style={{ flexShrink: 0, color: theme.palette.text.secondary }} />
        <Typography variant="body2" fontWeight={600} noWrap sx={{ minWidth: 0, flex: 1 }}>
          {repositoryName}
        </Typography>
        {repositoryPath && repositoryPath !== repositoryName && (
          <Typography
            variant="caption"
            color="text.disabled"
            noWrap
            sx={{
              fontFamily: 'monospace',
              fontSize: '0.65rem',
              minWidth: 0,
              maxWidth: { xs: 120, sm: 240 },
            }}
          >
            {repositoryPath}
          </Typography>
        )}
      </Box>
      <Box sx={{ pl: 2.5 }}>
        <ScheduleLine
          kind="check"
          label={t('schedule.byPlan.check', { defaultValue: 'Check' })}
          cron={checkCron}
          timezone={checkTimezone}
          enabled={checkEnabled}
          onClick={() => onEditCheck(repositoryId)}
          canManage={canManage}
          setLabel={t('schedule.byPlan.setSchedule', { defaultValue: 'Set schedule' })}
          editLabel={t('schedule.byPlan.edit', { defaultValue: 'Edit' })}
          pausedLabel={t('schedule.byPlan.paused', { defaultValue: 'Paused' })}
        />
        <ScheduleLine
          kind="restore"
          label={t('schedule.byPlan.restore', { defaultValue: 'Restore' })}
          cron={restoreCron}
          timezone={restoreTimezone}
          enabled={restoreEnabled}
          onClick={() => onEditRestore(repositoryId)}
          canManage={canManage}
          setLabel={t('schedule.byPlan.setSchedule', { defaultValue: 'Set schedule' })}
          editLabel={t('schedule.byPlan.edit', { defaultValue: 'Edit' })}
          pausedLabel={t('schedule.byPlan.paused', { defaultValue: 'Paused' })}
        />
      </Box>
    </Box>
  )
}

export default RepoScheduleRow

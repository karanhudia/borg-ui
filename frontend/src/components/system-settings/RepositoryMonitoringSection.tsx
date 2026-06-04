import {
  Alert,
  Box,
  Button,
  CircularProgress,
  Divider,
  Stack,
  TextField,
  Typography,
} from '@mui/material'
import { RefreshCw } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import {
  MAX_DASHBOARD_HEALTH_THRESHOLD_DAYS,
  MAX_SCHEDULE_CONCURRENCY,
  MAX_STATS_REFRESH,
} from './constants'

interface RepositoryMonitoringSectionProps {
  statsRefreshInterval: number
  maxConcurrentScheduledBackups: number
  maxConcurrentScheduledChecks: number
  dashboardBackupWarningDays: number
  dashboardBackupCriticalDays: number
  dashboardCheckWarningDays: number
  dashboardCheckCriticalDays: number
  dashboardCompactWarningDays: number
  dashboardCompactCriticalDays: number
  dashboardRestoreCheckWarningDays: number
  dashboardRestoreCheckCriticalDays: number
  dashboardObserveFreshnessWarningDays: number
  dashboardObserveFreshnessCriticalDays: number
  isRefreshingStats: boolean
  lastStatsRefresh?: string
  setStatsRefreshInterval: (value: number) => void
  setMaxConcurrentScheduledBackups: (value: number) => void
  setMaxConcurrentScheduledChecks: (value: number) => void
  setDashboardBackupWarningDays: (value: number) => void
  setDashboardBackupCriticalDays: (value: number) => void
  setDashboardCheckWarningDays: (value: number) => void
  setDashboardCheckCriticalDays: (value: number) => void
  setDashboardCompactWarningDays: (value: number) => void
  setDashboardCompactCriticalDays: (value: number) => void
  setDashboardRestoreCheckWarningDays: (value: number) => void
  setDashboardRestoreCheckCriticalDays: (value: number) => void
  setDashboardObserveFreshnessWarningDays: (value: number) => void
  setDashboardObserveFreshnessCriticalDays: (value: number) => void
  onRefreshStats: () => void
}

const RepositoryMonitoringSection: React.FC<RepositoryMonitoringSectionProps> = ({
  statsRefreshInterval,
  maxConcurrentScheduledBackups,
  maxConcurrentScheduledChecks,
  dashboardBackupWarningDays,
  dashboardBackupCriticalDays,
  dashboardCheckWarningDays,
  dashboardCheckCriticalDays,
  dashboardCompactWarningDays,
  dashboardCompactCriticalDays,
  dashboardRestoreCheckWarningDays,
  dashboardRestoreCheckCriticalDays,
  dashboardObserveFreshnessWarningDays,
  dashboardObserveFreshnessCriticalDays,
  isRefreshingStats,
  lastStatsRefresh,
  setStatsRefreshInterval,
  setMaxConcurrentScheduledBackups,
  setMaxConcurrentScheduledChecks,
  setDashboardBackupWarningDays,
  setDashboardBackupCriticalDays,
  setDashboardCheckWarningDays,
  setDashboardCheckCriticalDays,
  setDashboardCompactWarningDays,
  setDashboardCompactCriticalDays,
  setDashboardRestoreCheckWarningDays,
  setDashboardRestoreCheckCriticalDays,
  setDashboardObserveFreshnessWarningDays,
  setDashboardObserveFreshnessCriticalDays,
  onRefreshStats,
}) => {
  const { t } = useTranslation()
  const thresholdInputProps = {
    min: 1,
    max: MAX_DASHBOARD_HEALTH_THRESHOLD_DAYS,
    step: 1,
  }
  const getThresholdError = (value: number, pairedValue?: number, isWarning = false) =>
    value < 1 ||
    value > MAX_DASHBOARD_HEALTH_THRESHOLD_DAYS ||
    (isWarning && pairedValue !== undefined && value > pairedValue)
  const thresholdRangeHelper = t('systemSettings.dashboardHealthThresholdRangeHelper', {
    max: MAX_DASHBOARD_HEALTH_THRESHOLD_DAYS,
  })
  const thresholdFields = [
    {
      label: t('systemSettings.dashboardBackupWarningDaysLabel'),
      value: dashboardBackupWarningDays,
      setValue: setDashboardBackupWarningDays,
      error: getThresholdError(dashboardBackupWarningDays, dashboardBackupCriticalDays, true),
    },
    {
      label: t('systemSettings.dashboardBackupCriticalDaysLabel'),
      value: dashboardBackupCriticalDays,
      setValue: setDashboardBackupCriticalDays,
      error: getThresholdError(dashboardBackupCriticalDays),
    },
    {
      label: t('systemSettings.dashboardObserveFreshnessWarningDaysLabel'),
      value: dashboardObserveFreshnessWarningDays,
      setValue: setDashboardObserveFreshnessWarningDays,
      error: getThresholdError(
        dashboardObserveFreshnessWarningDays,
        dashboardObserveFreshnessCriticalDays,
        true
      ),
    },
    {
      label: t('systemSettings.dashboardObserveFreshnessCriticalDaysLabel'),
      value: dashboardObserveFreshnessCriticalDays,
      setValue: setDashboardObserveFreshnessCriticalDays,
      error: getThresholdError(dashboardObserveFreshnessCriticalDays),
    },
    {
      label: t('systemSettings.dashboardCheckWarningDaysLabel'),
      value: dashboardCheckWarningDays,
      setValue: setDashboardCheckWarningDays,
      error: getThresholdError(dashboardCheckWarningDays, dashboardCheckCriticalDays, true),
    },
    {
      label: t('systemSettings.dashboardCheckCriticalDaysLabel'),
      value: dashboardCheckCriticalDays,
      setValue: setDashboardCheckCriticalDays,
      error: getThresholdError(dashboardCheckCriticalDays),
    },
    {
      label: t('systemSettings.dashboardCompactWarningDaysLabel'),
      value: dashboardCompactWarningDays,
      setValue: setDashboardCompactWarningDays,
      error: getThresholdError(dashboardCompactWarningDays, dashboardCompactCriticalDays, true),
    },
    {
      label: t('systemSettings.dashboardCompactCriticalDaysLabel'),
      value: dashboardCompactCriticalDays,
      setValue: setDashboardCompactCriticalDays,
      error: getThresholdError(dashboardCompactCriticalDays),
    },
    {
      label: t('systemSettings.dashboardRestoreCheckWarningDaysLabel'),
      value: dashboardRestoreCheckWarningDays,
      setValue: setDashboardRestoreCheckWarningDays,
      error: getThresholdError(
        dashboardRestoreCheckWarningDays,
        dashboardRestoreCheckCriticalDays,
        true
      ),
    },
    {
      label: t('systemSettings.dashboardRestoreCheckCriticalDaysLabel'),
      value: dashboardRestoreCheckCriticalDays,
      setValue: setDashboardRestoreCheckCriticalDays,
      error: getThresholdError(dashboardRestoreCheckCriticalDays),
    },
  ]

  return (
    <Stack spacing={2.5}>
      <Box
        sx={{
          display: 'grid',
          gridTemplateColumns: { xs: '1fr', md: 'minmax(280px, 340px) auto' },
          gap: 2,
          alignItems: 'start',
        }}
      >
        <TextField
          label={t('systemSettings.statsRefreshIntervalLabel')}
          type="number"
          value={statsRefreshInterval}
          onChange={(e) => setStatsRefreshInterval(Number(e.target.value))}
          inputProps={{ min: 0, max: MAX_STATS_REFRESH, step: 15 }}
          error={statsRefreshInterval < 0 || statsRefreshInterval > MAX_STATS_REFRESH}
          helperText={
            statsRefreshInterval === 0
              ? t('systemSettings.statsRefreshDisabled')
              : statsRefreshInterval < 0 || statsRefreshInterval > MAX_STATS_REFRESH
                ? t('systemSettings.statsRefreshRangeError', { max: MAX_STATS_REFRESH })
                : t('systemSettings.statsRefreshIntervalHelper', {
                    interval: statsRefreshInterval,
                  })
          }
        />
        <Button
          variant="outlined"
          onClick={onRefreshStats}
          disabled={isRefreshingStats}
          startIcon={isRefreshingStats ? <CircularProgress size={16} /> : <RefreshCw size={16} />}
          sx={{ justifySelf: { xs: 'stretch', md: 'start' }, height: 40 }}
        >
          {isRefreshingStats ? t('systemSettings.refreshing') : t('systemSettings.refreshNow')}
        </Button>
      </Box>

      <Box
        sx={{
          display: 'grid',
          gridTemplateColumns: { xs: '1fr', md: 'repeat(2, minmax(240px, 320px))' },
          gap: 2,
        }}
      >
        <TextField
          label={t('systemSettings.maxConcurrentScheduledBackupsLabel')}
          type="number"
          value={maxConcurrentScheduledBackups}
          onChange={(e) => setMaxConcurrentScheduledBackups(Number(e.target.value))}
          inputProps={{ min: 0, max: MAX_SCHEDULE_CONCURRENCY, step: 1 }}
          error={
            maxConcurrentScheduledBackups < 0 ||
            maxConcurrentScheduledBackups > MAX_SCHEDULE_CONCURRENCY
          }
          helperText={t('systemSettings.maxConcurrentScheduledBackupsHelper')}
        />

        <TextField
          label={t('systemSettings.maxConcurrentScheduledChecksLabel')}
          type="number"
          value={maxConcurrentScheduledChecks}
          onChange={(e) => setMaxConcurrentScheduledChecks(Number(e.target.value))}
          inputProps={{ min: 0, max: MAX_SCHEDULE_CONCURRENCY, step: 1 }}
          error={
            maxConcurrentScheduledChecks < 0 ||
            maxConcurrentScheduledChecks > MAX_SCHEDULE_CONCURRENCY
          }
          helperText={t('systemSettings.maxConcurrentScheduledChecksHelper')}
        />
      </Box>

      <Divider />

      <Stack spacing={1.5}>
        <Box>
          <Typography variant="subtitle1" fontWeight={700}>
            {t('systemSettings.dashboardHealthThresholdsTitle')}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {t('systemSettings.dashboardHealthThresholdsDescription')}
          </Typography>
        </Box>

        <Box
          sx={{
            display: 'grid',
            gridTemplateColumns: { xs: '1fr', sm: 'repeat(2, minmax(220px, 1fr))' },
            gap: 2,
          }}
        >
          {thresholdFields.map((field) => (
            <TextField
              key={field.label}
              label={field.label}
              type="number"
              value={field.value}
              onChange={(event) => field.setValue(Number(event.target.value))}
              inputProps={thresholdInputProps}
              error={field.error}
              helperText={
                field.error
                  ? t('systemSettings.dashboardHealthThresholdError')
                  : thresholdRangeHelper
              }
            />
          ))}
        </Box>
      </Stack>

      {lastStatsRefresh && (
        <Alert severity="info">
          <Typography variant="body2">
            {t('systemSettings.lastRefreshed')} {new Date(lastStatsRefresh).toLocaleString()}
          </Typography>
        </Alert>
      )}
    </Stack>
  )
}

export default RepositoryMonitoringSection

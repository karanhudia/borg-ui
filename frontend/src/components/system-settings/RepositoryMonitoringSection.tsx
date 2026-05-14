import { Alert, Box, Button, CircularProgress, Stack, TextField, Typography } from '@mui/material'
import { RefreshCw } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { MAX_SCHEDULE_CONCURRENCY, MAX_STATS_REFRESH } from './constants'

interface RepositoryMonitoringSectionProps {
  statsRefreshInterval: number
  maxConcurrentScheduledBackups: number
  maxConcurrentScheduledChecks: number
  isRefreshingStats: boolean
  lastStatsRefresh?: string
  setStatsRefreshInterval: (value: number) => void
  setMaxConcurrentScheduledBackups: (value: number) => void
  setMaxConcurrentScheduledChecks: (value: number) => void
  onRefreshStats: () => void
}

const RepositoryMonitoringSection: React.FC<RepositoryMonitoringSectionProps> = ({
  statsRefreshInterval,
  maxConcurrentScheduledBackups,
  maxConcurrentScheduledChecks,
  isRefreshingStats,
  lastStatsRefresh,
  setStatsRefreshInterval,
  setMaxConcurrentScheduledBackups,
  setMaxConcurrentScheduledChecks,
  onRefreshStats,
}) => {
  const { t } = useTranslation()

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

import React, { useEffect, useMemo, useState } from 'react'
import {
  Alert,
  Box,
  Button,
  Card,
  CircularProgress,
  Divider,
  FormControl,
  FormControlLabel,
  InputLabel,
  MenuItem,
  Select,
  Stack,
  Switch,
  TextField,
  Typography,
} from '@mui/material'
import { BellRing, FileText, Save, SearchCheck, Send } from 'lucide-react'
import { toast } from 'react-hot-toast'
import { useTranslation } from 'react-i18next'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { settingsAPI } from '../services/api'
import type { SystemSettings } from '../services/api'
import { useAnalytics } from '../hooks/useAnalytics'
import { usePlan } from '../hooks/usePlan'
import { translateBackendKey } from '../utils/translateBackendKey'
import PlanGate from './shared/PlanGate'
import SchedulePicker from './shared/SchedulePicker'
import { getBrowserTimeZone } from '../utils/dateUtils'

type ReportFrequency = 'daily' | 'weekly' | 'monthly'

const readBool = (value: unknown, fallback: boolean) =>
  typeof value === 'boolean' ? value : fallback

const readNumber = (value: unknown, fallback: number) =>
  typeof value === 'number' && Number.isFinite(value) ? value : fallback

const readString = (value: unknown, fallback: string) =>
  typeof value === 'string' && value.trim() ? value : fallback

const readFrequency = (value: unknown): ReportFrequency =>
  value === 'daily' || value === 'weekly' || value === 'monthly' ? value : 'weekly'

const MonitoringReportsTab: React.FC = () => {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const { trackSystem, EventAction } = useAnalytics()
  const { can } = usePlan()
  const canUseAlertingMonitoring = can('alerting_monitoring')
  const canUseBackupReports = can('backup_reports')

  const [monitoringEnabled, setMonitoringEnabled] = useState(false)
  const [staleAfterDays, setStaleAfterDays] = useState(3)
  const [intervalHours, setIntervalHours] = useState(24)
  const [cooldownHours, setCooldownHours] = useState(24)
  const [includeObserveRepos, setIncludeObserveRepos] = useState(true)
  const [reportsEnabled, setReportsEnabled] = useState(false)
  const [reportFrequency, setReportFrequency] = useState<ReportFrequency>('weekly')
  const [reportCronExpression, setReportCronExpression] = useState('0 8 * * 1')
  const [reportTimezone, setReportTimezone] = useState(getBrowserTimeZone())
  const [includeSummary, setIncludeSummary] = useState(true)
  const [includeStaleRepositories, setIncludeStaleRepositories] = useState(true)
  const [includeRecentActivity, setIncludeRecentActivity] = useState(true)

  const { data, isLoading } = useQuery({
    queryKey: ['systemSettings'],
    queryFn: async () => {
      const response = await settingsAPI.getSystemSettings()
      return response.data
    },
  })

  const settings = data?.settings as SystemSettings | undefined

  useEffect(() => {
    if (!settings) return
    setMonitoringEnabled(readBool(settings.backup_monitoring_enabled, false))
    setStaleAfterDays(readNumber(settings.backup_monitoring_stale_after_days, 3))
    setIntervalHours(readNumber(settings.backup_monitoring_interval_hours, 24))
    setCooldownHours(readNumber(settings.backup_monitoring_alert_cooldown_hours, 24))
    setIncludeObserveRepos(readBool(settings.backup_monitoring_include_observe_repos, true))
    setReportsEnabled(readBool(settings.backup_reports_enabled, false))
    setReportFrequency(readFrequency(settings.backup_reports_frequency))
    setReportCronExpression(readString(settings.backup_reports_cron_expression, '0 8 * * 1'))
    setReportTimezone(readString(settings.backup_reports_timezone, getBrowserTimeZone()))
    setIncludeSummary(readBool(settings.backup_reports_include_summary, true))
    setIncludeStaleRepositories(readBool(settings.backup_reports_include_stale_repositories, true))
    setIncludeRecentActivity(readBool(settings.backup_reports_include_recent_activity, true))
  }, [settings])

  const payload = useMemo<SystemSettings>(
    () => ({
      backup_monitoring_enabled: monitoringEnabled,
      backup_monitoring_stale_after_days: staleAfterDays,
      backup_monitoring_interval_hours: intervalHours,
      backup_monitoring_alert_cooldown_hours: cooldownHours,
      backup_monitoring_include_observe_repos: includeObserveRepos,
      backup_reports_enabled: reportsEnabled,
      backup_reports_frequency: reportFrequency,
      backup_reports_cron_expression: reportCronExpression,
      backup_reports_timezone: reportTimezone,
      backup_reports_include_summary: includeSummary,
      backup_reports_include_stale_repositories: includeStaleRepositories,
      backup_reports_include_recent_activity: includeRecentActivity,
    }),
    [
      monitoringEnabled,
      staleAfterDays,
      intervalHours,
      cooldownHours,
      includeObserveRepos,
      reportsEnabled,
      reportFrequency,
      reportCronExpression,
      reportTimezone,
      includeSummary,
      includeStaleRepositories,
      includeRecentActivity,
    ]
  )

  const validationError =
    staleAfterDays < 1 ||
    intervalHours < 1 ||
    cooldownHours < 0 ||
    !reportCronExpression.trim() ||
    !reportTimezone.trim()
  const saveBlockedByPlan = !canUseAlertingMonitoring || !canUseBackupReports

  const saveMutation = useMutation({
    mutationFn: () => settingsAPI.updateSystemSettings(payload),
    onSuccess: async () => {
      toast.success(t('monitoringReports.savedSuccessfully'))
      await queryClient.invalidateQueries({ queryKey: ['systemSettings'] })
      trackSystem(EventAction.EDIT, {
        section: 'monitoring_reports',
        monitoring_enabled: monitoringEnabled,
        reports_enabled: reportsEnabled,
        report_frequency: reportFrequency,
      })
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      toast.error(
        translateBackendKey(error.response?.data?.detail) || t('monitoringReports.failedToSave')
      )
    },
  })

  const runMonitoringMutation = useMutation({
    mutationFn: settingsAPI.runBackupMonitoring,
    onSuccess: (response) => {
      toast.success(
        t('monitoringReports.monitoringRunComplete', {
          count: response.data?.stale_count ?? 0,
        })
      )
      queryClient.invalidateQueries({ queryKey: ['systemSettings'] })
      trackSystem(EventAction.START, { section: 'monitoring_reports', operation: 'run_check' })
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      toast.error(
        translateBackendKey(error.response?.data?.detail) || t('monitoringReports.failedToRun')
      )
    },
  })

  const sendReportMutation = useMutation({
    mutationFn: settingsAPI.sendBackupReport,
    onSuccess: (response) => {
      toast.success(
        t('monitoringReports.reportSent', {
          count: response.data?.repository_count ?? 0,
        })
      )
      queryClient.invalidateQueries({ queryKey: ['systemSettings'] })
      trackSystem(EventAction.START, { section: 'monitoring_reports', operation: 'send_report' })
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      toast.error(
        translateBackendKey(error.response?.data?.detail) || t('monitoringReports.failedToSend')
      )
    },
  })

  if (isLoading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', minHeight: 360, pt: 8 }}>
        <CircularProgress />
      </Box>
    )
  }

  return (
    <Box>
      <Stack spacing={3}>
        <Box
          sx={{
            display: 'flex',
            flexDirection: { xs: 'column', sm: 'row' },
            justifyContent: 'space-between',
            alignItems: { xs: 'stretch', sm: 'center' },
            gap: 1.5,
          }}
        >
          <Box>
            <Typography variant="h5" component="h1" fontWeight={700} gutterBottom>
              {t('monitoringReports.title')}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              {t('monitoringReports.subtitle')}
            </Typography>
          </Box>
          <Button
            variant="contained"
            startIcon={saveMutation.isPending ? <CircularProgress size={16} /> : <Save size={16} />}
            onClick={() => saveMutation.mutate()}
            disabled={saveMutation.isPending || validationError || saveBlockedByPlan}
          >
            {saveMutation.isPending ? t('monitoringReports.saving') : t('systemSettings.save')}
          </Button>
        </Box>

        <Card variant="outlined" sx={{ p: 2.5, borderRadius: 2 }}>
          <Stack spacing={2.5}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              <BellRing size={18} />
              <Box>
                <Typography variant="subtitle1" fontWeight={700}>
                  {t('monitoringReports.alertsTitle')}
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  {t('monitoringReports.alertsDescription')}
                </Typography>
              </Box>
            </Box>

            <FormControlLabel
              disabled={!canUseAlertingMonitoring}
              control={
                <Switch
                  checked={monitoringEnabled}
                  disabled={!canUseAlertingMonitoring}
                  slotProps={{
                    input: {
                      role: 'switch',
                      'aria-label': t('monitoringReports.enableMonitoring'),
                    },
                  }}
                  onChange={(event) => setMonitoringEnabled(event.target.checked)}
                />
              }
              label={t('monitoringReports.enableMonitoring')}
            />

            <Box
              sx={{
                display: 'grid',
                gridTemplateColumns: { xs: '1fr', sm: 'repeat(3, minmax(180px, 1fr))' },
                gap: 2,
              }}
            >
              <TextField
                label={t('monitoringReports.staleAfterDays')}
                type="number"
                value={staleAfterDays}
                onChange={(event) => setStaleAfterDays(Number(event.target.value))}
                disabled={!canUseAlertingMonitoring}
                inputProps={{ min: 1, max: 3650, step: 1 }}
                error={staleAfterDays < 1}
                helperText={t('monitoringReports.staleAfterHelper')}
              />
              <TextField
                label={t('monitoringReports.checkIntervalHours')}
                type="number"
                value={intervalHours}
                onChange={(event) => setIntervalHours(Number(event.target.value))}
                disabled={!canUseAlertingMonitoring}
                inputProps={{ min: 1, max: 720, step: 1 }}
                error={intervalHours < 1}
                helperText={t('monitoringReports.checkIntervalHelper')}
              />
              <TextField
                label={t('monitoringReports.cooldownHours')}
                type="number"
                value={cooldownHours}
                onChange={(event) => setCooldownHours(Number(event.target.value))}
                disabled={!canUseAlertingMonitoring}
                inputProps={{ min: 0, max: 720, step: 1 }}
                error={cooldownHours < 0}
                helperText={t('monitoringReports.cooldownHelper')}
              />
            </Box>

            <FormControlLabel
              disabled={!canUseAlertingMonitoring}
              control={
                <Switch
                  checked={includeObserveRepos}
                  disabled={!canUseAlertingMonitoring}
                  onChange={(event) => setIncludeObserveRepos(event.target.checked)}
                />
              }
              label={t('monitoringReports.includeObserveRepos')}
            />

            <PlanGate
              feature="alerting_monitoring"
              disabled
              surface="monitoring_reports"
              operation="run_check"
            >
              <Button
                variant="outlined"
                startIcon={
                  runMonitoringMutation.isPending ? (
                    <CircularProgress size={16} />
                  ) : (
                    <SearchCheck size={16} />
                  )
                }
                onClick={() => runMonitoringMutation.mutate()}
                disabled={runMonitoringMutation.isPending || !canUseAlertingMonitoring}
                sx={{ alignSelf: 'flex-start' }}
              >
                {t('monitoringReports.runCheckNow')}
              </Button>
            </PlanGate>

            {(settings?.backup_monitoring_last_checked_at ||
              settings?.backup_monitoring_last_alert_sent_at) && (
              <Alert severity="info">
                {settings?.backup_monitoring_last_checked_at &&
                  `${t('monitoringReports.lastChecked')} ${new Date(
                    settings.backup_monitoring_last_checked_at
                  ).toLocaleString()}`}
                {settings?.backup_monitoring_last_alert_sent_at &&
                  ` ${t('monitoringReports.lastAlert')} ${new Date(
                    settings.backup_monitoring_last_alert_sent_at
                  ).toLocaleString()}`}
              </Alert>
            )}
          </Stack>
        </Card>

        <Card variant="outlined" sx={{ p: 2.5, borderRadius: 2 }}>
          <Stack spacing={2.5}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              <FileText size={18} />
              <Box>
                <Typography variant="subtitle1" fontWeight={700}>
                  {t('monitoringReports.reportsTitle')}
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  {t('monitoringReports.reportsDescription')}
                </Typography>
              </Box>
            </Box>

            <FormControlLabel
              disabled={!canUseBackupReports}
              control={
                  <Switch
                    checked={reportsEnabled}
                    disabled={!canUseBackupReports}
                    slotProps={{
                      input: {
                        role: 'switch',
                        'aria-label': t('monitoringReports.enableReports'),
                      },
                    }}
                    onChange={(event) => setReportsEnabled(event.target.checked)}
                  />
              }
              label={t('monitoringReports.enableReports')}
            />

            <Stack spacing={2}>
              <FormControl fullWidth disabled={!canUseBackupReports}>
                <InputLabel id="backup-report-frequency-label">
                  {t('monitoringReports.cadence')}
                </InputLabel>
                <Select
                  labelId="backup-report-frequency-label"
                  label={t('monitoringReports.cadence')}
                  value={reportFrequency}
                  onChange={(event) => setReportFrequency(event.target.value as ReportFrequency)}
                >
                  <MenuItem value="daily">{t('monitoringReports.frequencyDaily')}</MenuItem>
                  <MenuItem value="weekly">{t('monitoringReports.frequencyWeekly')}</MenuItem>
                  <MenuItem value="monthly">{t('monitoringReports.frequencyMonthly')}</MenuItem>
                </Select>
              </FormControl>

              <Typography variant="body2" color="text.secondary" sx={{ mt: -1 }}>
                {t('monitoringReports.cadenceHelper')}
              </Typography>

              <SchedulePicker
                cronExpression={reportCronExpression}
                timezone={reportTimezone}
                disabled={!canUseBackupReports}
                onChange={(updates) => {
                  if (updates.cronExpression !== undefined) {
                    setReportCronExpression(updates.cronExpression)
                  }
                  if (updates.timezone !== undefined) {
                    setReportTimezone(updates.timezone)
                  }
                }}
                cronLabel={t('monitoringReports.deliverySchedule')}
                cronHelperText={t('monitoringReports.deliveryScheduleHelper')}
                timezoneLabel={t('monitoringReports.deliveryTimezone')}
              />
            </Stack>

            <Divider />

            <Stack spacing={0.5}>
              <Typography variant="subtitle2" fontWeight={700}>
                {t('monitoringReports.reportContent')}
              </Typography>
              <FormControlLabel
                disabled={!canUseBackupReports}
                control={
                  <Switch
                    checked={includeSummary}
                    disabled={!canUseBackupReports}
                    onChange={(event) => setIncludeSummary(event.target.checked)}
                  />
                }
                label={t('monitoringReports.summary')}
              />
              <FormControlLabel
                disabled={!canUseBackupReports}
                control={
                  <Switch
                    checked={includeStaleRepositories}
                    disabled={!canUseBackupReports}
                    onChange={(event) => setIncludeStaleRepositories(event.target.checked)}
                  />
                }
                label={t('monitoringReports.staleRepositories')}
              />
              <FormControlLabel
                disabled={!canUseBackupReports}
                control={
                  <Switch
                    checked={includeRecentActivity}
                    disabled={!canUseBackupReports}
                    onChange={(event) => setIncludeRecentActivity(event.target.checked)}
                  />
                }
                label={t('monitoringReports.recentActivity')}
              />
            </Stack>

            <PlanGate
              feature="backup_reports"
              disabled
              surface="monitoring_reports"
              operation="send_report"
            >
              <Button
                variant="outlined"
                startIcon={
                  sendReportMutation.isPending ? (
                    <CircularProgress size={16} />
                  ) : (
                    <Send size={16} />
                  )
                }
                onClick={() => sendReportMutation.mutate()}
                disabled={sendReportMutation.isPending || !canUseBackupReports}
                sx={{ alignSelf: 'flex-start' }}
              >
                {t('monitoringReports.sendReportNow')}
              </Button>
            </PlanGate>

            {settings?.backup_reports_last_sent_at && (
              <Alert severity="info">
                {t('monitoringReports.lastReport')}{' '}
                {new Date(settings.backup_reports_last_sent_at).toLocaleString()}
              </Alert>
            )}
          </Stack>
        </Card>
      </Stack>
    </Box>
  )
}

export default MonitoringReportsTab

import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box } from '@mui/material'
import MonitoringReportsTab from './MonitoringReportsTab'
import { settingsAPI } from '../services/api'
import type { SystemSettings } from '../services/api'
import {
  communitySystemInfo,
  proSystemInfo,
} from '../services/remoteBackends/planStoryFixtures'

const sampleSettings: SystemSettings = {
  backup_monitoring_enabled: true,
  backup_monitoring_stale_after_days: 4,
  backup_monitoring_interval_hours: 12,
  backup_monitoring_alert_cooldown_hours: 24,
  backup_monitoring_include_observe_repos: true,
  backup_monitoring_last_checked_at: '2026-05-16T10:15:00.000Z',
  backup_monitoring_last_alert_sent_at: '2026-05-15T08:30:00.000Z',
  backup_reports_enabled: true,
  backup_reports_frequency: 'weekly',
  backup_reports_cron_expression: '15 9 * * 1',
  backup_reports_timezone: 'Asia/Kolkata',
  backup_reports_hour_utc: 9,
  backup_reports_weekday: 0,
  backup_reports_monthday: 1,
  backup_reports_include_summary: true,
  backup_reports_include_stale_repositories: true,
  backup_reports_include_recent_activity: true,
  backup_reports_last_sent_at: '2026-05-13T09:00:00.000Z',
}

settingsAPI.getSystemSettings = async () =>
  ({
    data: { settings: sampleSettings },
    status: 200,
    statusText: 'OK',
    headers: {},
    config: {},
  }) as Awaited<ReturnType<typeof settingsAPI.getSystemSettings>>

settingsAPI.updateSystemSettings = async () =>
  ({
    data: { settings: sampleSettings },
    status: 200,
    statusText: 'OK',
    headers: {},
    config: {},
  }) as Awaited<ReturnType<typeof settingsAPI.updateSystemSettings>>

settingsAPI.runBackupMonitoring = async () =>
  ({
    data: { stale_count: 2, alert_sent: true },
    status: 200,
    statusText: 'OK',
    headers: {},
    config: {},
  }) as Awaited<ReturnType<typeof settingsAPI.runBackupMonitoring>>

settingsAPI.sendBackupReport = async () =>
  ({
    data: { sent: true, repository_count: 6 },
    status: 200,
    statusText: 'OK',
    headers: {},
    config: {},
  }) as Awaited<ReturnType<typeof settingsAPI.sendBackupReport>>

const meta = {
  title: 'Components/MonitoringReportsTab',
  component: MonitoringReportsTab,
  parameters: {
    layout: 'fullscreen',
  },
} satisfies Meta<typeof MonitoringReportsTab>

export default meta

type Story = StoryObj<typeof meta>

export const Configured: Story = {
  parameters: {
    systemInfo: proSystemInfo,
  },
  render: () => (
    <Box sx={{ maxWidth: 1040, mx: 'auto', p: 3 }}>
      <MonitoringReportsTab />
    </Box>
  ),
}

export const CommunityLocked: Story = {
  parameters: {
    systemInfo: communitySystemInfo,
  },
  render: () => (
    <Box sx={{ maxWidth: 1040, mx: 'auto', p: 3 }}>
      <MonitoringReportsTab />
    </Box>
  ),
}

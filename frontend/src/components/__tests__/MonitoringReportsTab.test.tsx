import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fireEvent, screen, waitFor } from '@testing-library/react'
import { AxiosResponse } from 'axios'

import MonitoringReportsTab from '../MonitoringReportsTab'
import { settingsAPI } from '../../services/api'
import { renderWithProviders } from '../../test/test-utils'

const { usePlanMock } = vi.hoisted(() => ({
  usePlanMock: vi.fn(),
}))

vi.mock('../../services/api', () => ({
  settingsAPI: {
    getSystemSettings: vi.fn(),
    updateSystemSettings: vi.fn(),
    runBackupMonitoring: vi.fn(),
    sendBackupReport: vi.fn(),
  },
}))

vi.mock('react-hot-toast', async () => {
  const actual = await vi.importActual('react-hot-toast')
  return {
    ...actual,
    toast: {
      success: vi.fn(),
      error: vi.fn(),
    },
  }
})

vi.mock('../../hooks/usePlan', () => ({
  usePlan: usePlanMock,
}))

const systemSettings = {
  backup_monitoring_enabled: true,
  backup_monitoring_stale_after_days: 4,
  backup_monitoring_interval_hours: 12,
  backup_monitoring_alert_cooldown_hours: 24,
  backup_monitoring_include_observe_repos: true,
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
}

const response = (settings = systemSettings): AxiosResponse =>
  ({
    data: { settings },
    status: 200,
    statusText: 'OK',
    headers: {},
    config: {},
  }) as AxiosResponse

describe('MonitoringReportsTab', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    usePlanMock.mockReturnValue({
      plan: 'pro',
      features: {},
      isLoading: false,
      can: () => true,
    })
    vi.mocked(settingsAPI.getSystemSettings).mockResolvedValue(response())
    vi.mocked(settingsAPI.updateSystemSettings).mockResolvedValue(response())
    vi.mocked(settingsAPI.runBackupMonitoring).mockResolvedValue({
      data: { stale_count: 0, alert_sent: false },
    } as AxiosResponse)
    vi.mocked(settingsAPI.sendBackupReport).mockResolvedValue({
      data: { sent: true, repository_count: 1 },
    } as AxiosResponse)
  })

  it('saves report delivery cron expression and timezone', async () => {
    renderWithProviders(<MonitoringReportsTab />)

    const scheduleInput = await screen.findByRole('textbox', {
      name: /Delivery schedule/i,
    })
    await waitFor(() => {
      expect(scheduleInput).toHaveValue('15 9 * * 1')
    })
    const timezoneInput = screen.getByRole('combobox', { name: /Report timezone/i })
    expect((timezoneInput as HTMLInputElement).value).toMatch(/^Asia\/(Kolkata|Calcutta)$/)
    expect(screen.queryByLabelText(/Hour \(UTC\)/i)).not.toBeInTheDocument()

    fireEvent.change(scheduleInput, { target: { value: '30 18 * * 5' } })
    fireEvent.click(screen.getByRole('button', { name: /Save/i }))

    await waitFor(() => {
      expect(settingsAPI.updateSystemSettings).toHaveBeenCalledWith(
        expect.objectContaining({
          backup_reports_frequency: 'weekly',
          backup_reports_cron_expression: '30 18 * * 5',
          backup_reports_timezone: 'Asia/Kolkata',
        })
      )
    })
  }, 30000)

  it('gates monitoring and report actions when Pro features are unavailable', async () => {
    usePlanMock.mockReturnValue({
      plan: 'community',
      features: {},
      isLoading: false,
      can: (feature: string) =>
        feature !== 'alerting_monitoring' && feature !== 'backup_reports',
    })

    renderWithProviders(<MonitoringReportsTab />)

    expect(
      await screen.findByRole('switch', { name: /Enable stale-backup monitoring/i })
    ).toBeDisabled()
    expect(screen.getByRole('button', { name: /Run check now/i })).toBeDisabled()
    expect(screen.getByRole('switch', { name: /Enable backup reports/i })).toBeDisabled()
    expect(screen.getByRole('button', { name: /Send report now/i })).toBeDisabled()
  }, 30000)
})

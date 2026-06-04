import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { AxiosResponse } from 'axios'

import SystemSettingsTab from '../SystemSettingsTab'
import { authAPI, settingsAPI } from '@/services/api.ts'
import { renderWithProviders } from '../../test/test-utils'

vi.mock('../../services/api', () => ({
  settingsAPI: {
    getCacheStats: vi.fn(),
    getSystemSettings: vi.fn(),
    updateCacheSettings: vi.fn(),
    updateSystemSettings: vi.fn(),
    refreshAllStats: vi.fn(),
  },
  authAPI: {
    getAuthConfig: vi.fn(),
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

const defaultSystemSettings = {
  mount_timeout: 120,
  info_timeout: 600,
  list_timeout: 600,
  init_timeout: 300,
  backup_timeout: 3600,
  source_size_timeout: 3600,
  max_concurrent_scheduled_backups: 2,
  max_concurrent_scheduled_checks: 4,
  stats_refresh_interval_minutes: 60,
  dashboard_backup_warning_days: 3,
  dashboard_backup_critical_days: 7,
  dashboard_check_warning_days: 7,
  dashboard_check_critical_days: 30,
  dashboard_compact_warning_days: 30,
  dashboard_compact_critical_days: 60,
  dashboard_restore_check_warning_days: 14,
  dashboard_restore_check_critical_days: 30,
  dashboard_observe_freshness_warning_days: 2,
  dashboard_observe_freshness_critical_days: 7,
  metrics_enabled: false,
  metrics_require_auth: false,
}

const buildSystemSettingsResponse = (
  overrides: Partial<typeof defaultSystemSettings> = {}
): AxiosResponse =>
  ({
    data: {
      settings: {
        ...defaultSystemSettings,
        ...overrides,
      },
    },
  }) as AxiosResponse

describe('SystemSettingsTab', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(settingsAPI.getCacheStats).mockResolvedValue({
      data: {
        browse_max_items: 1_000_000,
        browse_max_memory_mb: 1024,
        cache_ttl_minutes: 120,
        cache_max_size_mb: 2048,
        redis_url: '',
      },
    } as AxiosResponse)
    vi.mocked(settingsAPI.getSystemSettings).mockResolvedValue(buildSystemSettingsResponse())
    vi.mocked(authAPI.getAuthConfig).mockResolvedValue({
      data: {
        proxy_auth_enabled: false,
        insecure_no_auth_enabled: false,
        authentication_required: true,
      },
    } as AxiosResponse)
    vi.mocked(settingsAPI.updateSystemSettings).mockResolvedValue({
      data: {},
    } as AxiosResponse)
  })

  it('renders scheduler concurrency controls', async () => {
    const user = userEvent.setup()
    renderWithProviders(<SystemSettingsTab />)

    await waitFor(() => {
      expect(screen.getByRole('tab', { name: 'Repository Monitoring' })).toBeInTheDocument()
    })

    await user.click(screen.getByRole('tab', { name: 'Repository Monitoring' }))

    expect(screen.getByLabelText('Max Concurrent Scheduled Backups')).toBeInTheDocument()
    expect(screen.getByLabelText('Max Concurrent Scheduled Checks')).toBeInTheDocument()
  })

  it('renders dashboard health threshold controls', async () => {
    const user = userEvent.setup()
    renderWithProviders(<SystemSettingsTab />)

    await waitFor(() => {
      expect(screen.getByRole('tab', { name: 'Repository Monitoring' })).toBeInTheDocument()
    })

    await user.click(screen.getByRole('tab', { name: 'Repository Monitoring' }))

    expect(screen.getByLabelText('Backup Warning Age (days)')).toBeInTheDocument()
    expect(screen.getByLabelText('Backup Critical Age (days)')).toBeInTheDocument()
    expect(screen.getByLabelText('Observe Warning Age (days)')).toBeInTheDocument()
    expect(screen.getByLabelText('Observe Critical Age (days)')).toBeInTheDocument()
    expect(screen.getByLabelText('Check Warning Age (days)')).toBeInTheDocument()
    expect(screen.getByLabelText('Check Critical Age (days)')).toBeInTheDocument()
    expect(screen.getByLabelText('Compact Warning Age (days)')).toBeInTheDocument()
    expect(screen.getByLabelText('Compact Critical Age (days)')).toBeInTheDocument()
    expect(screen.getByLabelText('Restore Check Warning Age (days)')).toBeInTheDocument()
    expect(screen.getByLabelText('Restore Check Critical Age (days)')).toBeInTheDocument()
  })

  it('saves scheduler concurrency limits with system settings', async () => {
    const user = userEvent.setup()
    renderWithProviders(<SystemSettingsTab />)

    await waitFor(() => {
      expect(screen.getByRole('tab', { name: 'Repository Monitoring' })).toBeInTheDocument()
    })

    await user.click(screen.getByRole('tab', { name: 'Repository Monitoring' }))

    const backupLimit = screen.getByLabelText('Max Concurrent Scheduled Backups')
    const checkLimit = screen.getByLabelText('Max Concurrent Scheduled Checks')

    await user.clear(backupLimit)
    await user.type(backupLimit, '3')
    await user.clear(checkLimit)
    await user.type(checkLimit, '5')

    await user.click(screen.getByRole('button', { name: /Save Settings/i }))

    await waitFor(() => {
      expect(settingsAPI.updateSystemSettings).toHaveBeenCalledWith(
        expect.objectContaining({
          max_concurrent_scheduled_backups: 3,
          max_concurrent_scheduled_checks: 5,
        })
      )
    })
  })

  it('saves dashboard health thresholds with system settings', async () => {
    const user = userEvent.setup()
    vi.mocked(settingsAPI.getSystemSettings)
      .mockResolvedValueOnce(buildSystemSettingsResponse())
      .mockResolvedValueOnce(
        buildSystemSettingsResponse({
          dashboard_backup_warning_days: 15,
          dashboard_backup_critical_days: 32,
        })
      )
    vi.mocked(settingsAPI.updateSystemSettings).mockResolvedValue({
      data: {
        settings: {
          dashboard_backup_warning_days: 99,
          dashboard_backup_critical_days: 100,
        },
      },
    } as AxiosResponse)
    renderWithProviders(<SystemSettingsTab />)

    await waitFor(() => {
      expect(screen.getByRole('tab', { name: 'Repository Monitoring' })).toBeInTheDocument()
    })

    await user.click(screen.getByRole('tab', { name: 'Repository Monitoring' }))

    const backupWarning = screen.getByLabelText('Backup Warning Age (days)')
    const backupCritical = screen.getByLabelText('Backup Critical Age (days)')

    await user.clear(backupWarning)
    await user.type(backupWarning, '14')
    await user.clear(backupCritical)
    await user.type(backupCritical, '31')

    await user.click(screen.getByRole('button', { name: /Save Settings/i }))

    await waitFor(() => {
      expect(settingsAPI.updateSystemSettings).toHaveBeenCalledWith(
        expect.objectContaining({
          dashboard_backup_warning_days: 14,
          dashboard_backup_critical_days: 31,
        })
      )
    })
    await waitFor(() => {
      expect(settingsAPI.getSystemSettings).toHaveBeenCalledTimes(2)
      expect(screen.getByLabelText('Backup Warning Age (days)')).toHaveValue(15)
      expect(screen.getByLabelText('Backup Critical Age (days)')).toHaveValue(32)
    })
  })
})

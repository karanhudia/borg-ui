import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ThemeProvider } from '../../context/ThemeContext'
import { fireEvent, renderWithProviders, screen, waitFor } from '../../test/test-utils'
import Settings from '../Settings'
import * as apiModule from '../../services/api'

const trackSettings = vi.fn()
const trackSystem = vi.fn()

vi.mock('../../hooks/useAuth', () => ({
  useAuth: () => ({
    user: {
      id: 1,
      username: 'admin',
      email: 'admin@example.com',
      role: 'admin',
      global_permissions: ['settings.system.manage'],
    },
    hasGlobalPermission: (permission: string) => permission === 'settings.system.manage',
  }),
}))

vi.mock('../../hooks/useAnalytics', () => ({
  useAnalytics: () => ({
    trackSettings,
    trackSystem,
    EventAction: {
      VIEW: 'View',
      EDIT: 'Edit',
      START: 'Start',
    },
  }),
}))

vi.mock('../../components/AccountTab', () => ({ default: () => null }))
vi.mock('../../components/AppearanceTab', () => ({ default: () => null }))
vi.mock('../../components/NotificationsTab', () => ({ default: () => null }))
vi.mock('../../components/PreferencesTab', () => ({ default: () => null }))
vi.mock('../../components/PackagesTab', () => ({ default: () => null }))
vi.mock('../../components/ExportImportTab', () => ({ default: () => null }))
vi.mock('../../components/LogManagementTab', () => ({ default: () => null }))
vi.mock('../../components/CacheManagementTab', () => ({ default: () => null }))
vi.mock('../../components/MountsManagementTab', () => ({ default: () => null }))
vi.mock('../../components/SystemSettingsTab', () => ({ default: () => null }))
vi.mock('../../components/LicensingTab', () => ({ default: () => null }))
vi.mock('../../components/BetaFeaturesTab', () => ({ default: () => null }))
vi.mock('../../components/MqttSettingsTab', () => ({ default: () => null }))
vi.mock('../../components/UsersTab', () => ({ default: () => null }))
vi.mock('../Scripts', () => ({ default: () => null }))
vi.mock('../Activity', () => ({ default: () => null }))

vi.mock('../../services/api', () => ({
  settingsAPI: {
    getSystemSettings: vi.fn(),
    updateSystemSettings: vi.fn(),
    runBackupMonitoring: vi.fn(),
    sendBackupReport: vi.fn(),
  },
}))

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom')
  return {
    ...actual,
    useParams: () => ({ tab: 'monitoring' }),
  }
})

const systemSettings = {
  backup_monitoring_enabled: false,
  backup_monitoring_stale_after_days: 3,
  backup_monitoring_interval_hours: 24,
  backup_monitoring_alert_cooldown_hours: 24,
  backup_monitoring_include_observe_repos: true,
  backup_monitoring_last_checked_at: null,
  backup_monitoring_last_alert_sent_at: null,
  backup_reports_enabled: false,
  backup_reports_frequency: 'weekly',
  backup_reports_hour_utc: 8,
  backup_reports_weekday: 1,
  backup_reports_monthday: 1,
  backup_reports_include_summary: true,
  backup_reports_include_stale_repositories: true,
  backup_reports_include_recent_activity: true,
  backup_reports_last_sent_at: null,
}

describe('Settings monitoring reports tab', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(apiModule.settingsAPI.getSystemSettings).mockResolvedValue({
      data: { settings: systemSettings },
    } as never)
    vi.mocked(apiModule.settingsAPI.updateSystemSettings).mockResolvedValue({
      data: { settings: {} },
    } as never)
    vi.mocked(apiModule.settingsAPI.runBackupMonitoring).mockResolvedValue({
      data: { stale_count: 2, alert_sent: true },
    } as never)
    vi.mocked(apiModule.settingsAPI.sendBackupReport).mockResolvedValue({
      data: { sent: true, repository_count: 4 },
    } as never)
  })

  it('saves monitoring and report settings from the settings route', async () => {
    renderWithProviders(
      <ThemeProvider>
        <Settings />
      </ThemeProvider>
    )

    await screen.findByRole('heading', { name: /monitoring & reports/i })

    fireEvent.click(screen.getByLabelText(/enable stale-backup monitoring/i))
    fireEvent.change(screen.getByLabelText(/stale after/i), { target: { value: '5' } })
    fireEvent.change(screen.getByLabelText(/check interval/i), { target: { value: '6' } })
    fireEvent.click(screen.getByLabelText(/enable backup reports/i))
    fireEvent.click(screen.getByLabelText(/recent backup activity/i))
    fireEvent.click(screen.getByRole('button', { name: /save settings/i }))

    await waitFor(() => {
      expect(apiModule.settingsAPI.updateSystemSettings).toHaveBeenCalledWith(
        expect.objectContaining({
          backup_monitoring_enabled: true,
          backup_monitoring_stale_after_days: 5,
          backup_monitoring_interval_hours: 6,
          backup_reports_enabled: true,
          backup_reports_include_recent_activity: false,
        })
      )
    })
  })

  it('runs manual monitoring and report actions', async () => {
    renderWithProviders(
      <ThemeProvider>
        <Settings />
      </ThemeProvider>
    )

    await screen.findByRole('heading', { name: /monitoring & reports/i })
    fireEvent.click(screen.getByRole('button', { name: /run check now/i }))
    fireEvent.click(screen.getByRole('button', { name: /send report now/i }))

    await waitFor(() => {
      expect(apiModule.settingsAPI.runBackupMonitoring).toHaveBeenCalledTimes(1)
      expect(apiModule.settingsAPI.sendBackupReport).toHaveBeenCalledTimes(1)
    })
  })
})

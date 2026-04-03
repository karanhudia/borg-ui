import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderWithProviders, screen, userEvent, waitFor } from '../../test/test-utils'
import PreferencesTab from '../PreferencesTab'
import { toast } from 'react-hot-toast'
import i18n from '../../i18n'

const getPreferencesMock = vi.fn()
const updatePreferencesMock = vi.fn()
const resetOptOutCacheMock = vi.fn()
const trackOptOutMock = vi.fn()
const trackLanguageChangeMock = vi.fn()

vi.mock('../../services/api', () => ({
  settingsAPI: {
    getPreferences: () => getPreferencesMock(),
    updatePreferences: (preferences: unknown) => updatePreferencesMock(preferences),
  },
}))

vi.mock('../../utils/analytics', async () => {
  const actual =
    await vi.importActual<typeof import('../../utils/analytics')>('../../utils/analytics')
  return {
    ...actual,
    resetOptOutCache: () => resetOptOutCacheMock(),
    trackOptOut: () => trackOptOutMock(),
    trackLanguageChange: (langCode: string) => trackLanguageChangeMock(langCode),
  }
})

vi.mock('react-hot-toast', async () => {
  const actual = await vi.importActual<typeof import('react-hot-toast')>('react-hot-toast')
  return {
    ...actual,
    toast: {
      success: vi.fn(),
      error: vi.fn(),
    },
  }
})

describe('PreferencesTab', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    getPreferencesMock.mockResolvedValue({
      data: {
        preferences: {
          analytics_enabled: true,
        },
      },
    })
    updatePreferencesMock.mockResolvedValue({ data: {} })
    resetOptOutCacheMock.mockResolvedValue(undefined)
  })

  it('loads preferences and disables analytics with the correct side effects', async () => {
    const user = userEvent.setup()
    const setTimeoutSpy = vi.spyOn(window, 'setTimeout')

    renderWithProviders(<PreferencesTab />)

    const analyticsSwitch = await screen.findByRole('switch', { name: /enable analytics/i })
    expect(analyticsSwitch).toBeChecked()

    await user.click(analyticsSwitch)

    await waitFor(() => {
      expect(trackOptOutMock).toHaveBeenCalledTimes(1)
      expect(updatePreferencesMock).toHaveBeenCalledWith({ analytics_enabled: false })
      expect(resetOptOutCacheMock).toHaveBeenCalledTimes(1)
      expect(toast.success).toHaveBeenCalled()
    })

    expect(setTimeoutSpy).toHaveBeenCalledWith(expect.any(Function), 500)
  })

  it('changes the UI language and persists the selection locally', async () => {
    const user = userEvent.setup()
    const changeLanguageSpy = vi
      .spyOn(i18n, 'changeLanguage')
      .mockResolvedValue(i18n.t.bind(i18n) as typeof i18n.t)

    renderWithProviders(<PreferencesTab />)

    const languageSelect = await screen.findByRole('combobox')
    await user.click(languageSelect)
    await user.click(await screen.findByRole('option', { name: 'Deutsch' }))

    expect(trackLanguageChangeMock).toHaveBeenCalledWith('de')
    expect(changeLanguageSpy).toHaveBeenCalledWith('de')
    expect(localStorage.getItem('i18nextLng')).toBe('de')
    expect(toast.success).toHaveBeenCalled()
  })

  it('shows the translated backend error when updating preferences fails', async () => {
    const user = userEvent.setup()
    updatePreferencesMock.mockRejectedValue({
      response: {
        data: {
          detail: 'backend.errors.auth.invalidToken',
        },
      },
    })

    renderWithProviders(<PreferencesTab />)

    const analyticsSwitch = await screen.findByRole('switch', { name: /enable analytics/i })
    await user.click(analyticsSwitch)

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('Invalid token')
    })
  })
})

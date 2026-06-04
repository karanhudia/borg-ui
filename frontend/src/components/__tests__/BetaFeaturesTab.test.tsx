import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient } from '@tanstack/react-query'
import BetaFeaturesTab from '../BetaFeaturesTab'
import { settingsAPI } from '../../services/api'
import { renderWithProviders } from '../../test/test-utils'
import { AxiosResponse } from 'axios'

vi.mock('../../services/api', () => ({
  settingsAPI: {
    getSystemSettings: vi.fn(),
    updateSystemSettings: vi.fn(),
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

describe('BetaFeaturesTab', () => {
  const mockSystemSettings = {
    settings: {
      bypass_lock_on_info: false,
      bypass_lock_on_list: false,
      lock_breaking_enabled: true,
      borg2_fast_browse_beta_enabled: false,
      mqtt_beta_enabled: false,
    },
  }

  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(settingsAPI.getSystemSettings).mockResolvedValue({
      data: mockSystemSettings,
    } as AxiosResponse)
  })

  function createSystemSettingsClient(settings: Record<string, unknown>) {
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false, staleTime: Infinity },
        mutations: { retry: false },
      },
    })
    queryClient.setQueryData(['systemSettings'], { settings })
    return queryClient
  }

  function getSwitchByLabel(label: string) {
    const labelElement = screen.getByText(label).closest('label')
    expect(labelElement).not.toBeNull()
    return within(labelElement as HTMLElement).getByRole('switch')
  }

  describe('Rendering', () => {
    it('shows loading spinner while fetching settings', () => {
      vi.mocked(settingsAPI.getSystemSettings).mockImplementation(() => new Promise(() => {}))
      renderWithProviders(<BetaFeaturesTab />)
      expect(screen.getByRole('progressbar')).toBeInTheDocument()
    })

    it('renders Beta Features header', async () => {
      renderWithProviders(<BetaFeaturesTab />)
      await waitFor(() => {
        expect(screen.getByText('Beta Features')).toBeInTheDocument()
      })
    })

    it('renders description text', async () => {
      renderWithProviders(<BetaFeaturesTab />)
      await waitFor(() => {
        expect(
          screen.getByText(
            /Try experimental features before they're released to everyone. These features are still in development and may change./
          )
        ).toBeInTheDocument()
      })
    })

    it('renders bypass lock on info toggle', async () => {
      renderWithProviders(<BetaFeaturesTab />)
      await waitFor(() => {
        expect(
          screen.getByText('Enable bypass-lock for all borg info commands')
        ).toBeInTheDocument()
      })
    })

    it('renders bypass lock on list toggle', async () => {
      renderWithProviders(<BetaFeaturesTab />)
      await waitFor(() => {
        expect(
          screen.getByText('Enable bypass-lock for all borg list commands')
        ).toBeInTheDocument()
      })
    })

    it('renders manual lock breaking toggle', async () => {
      renderWithProviders(<BetaFeaturesTab />)
      await waitFor(() => {
        expect(screen.getByText('Allow manual repository lock breaking')).toBeInTheDocument()
      })
    })

    it('renders MQTT integration toggle', async () => {
      renderWithProviders(<BetaFeaturesTab />)
      await waitFor(() => {
        expect(screen.getByText('Enable MQTT')).toBeInTheDocument()
      })
    })

    it('renders Borg 2 fast browse toggle', async () => {
      renderWithProviders(<BetaFeaturesTab />)
      await waitFor(() => {
        expect(screen.getByText('Enable faster Borg 2 archive browsing')).toBeInTheDocument()
      })
    })

    it('renders section headers', async () => {
      renderWithProviders(<BetaFeaturesTab />)
      await waitFor(() => {
        expect(screen.getByText('Bypass Locks for Info Commands')).toBeInTheDocument()
        expect(screen.getByText('Bypass Locks for List Commands')).toBeInTheDocument()
        expect(screen.getByText('Manual Lock Breaking')).toBeInTheDocument()
        expect(screen.getByText('Fast Borg 2 Archive Browse')).toBeInTheDocument()
        expect(screen.getByText('MQTT Integration')).toBeInTheDocument()
      })
    })
  })

  describe('Manual Lock Breaking', () => {
    it('can disable manual lock breaking', async () => {
      const user = userEvent.setup()
      vi.mocked(settingsAPI.updateSystemSettings).mockResolvedValue({} as AxiosResponse)

      renderWithProviders(<BetaFeaturesTab />)

      await waitFor(() => {
        expect(screen.getByText('Allow manual repository lock breaking')).toBeInTheDocument()
      })

      const lockBreakingSwitch = getSwitchByLabel('Allow manual repository lock breaking')
      await user.click(lockBreakingSwitch)

      await waitFor(() => {
        expect(settingsAPI.updateSystemSettings).toHaveBeenCalledWith({
          lock_breaking_enabled: false,
        })
      })
    })
  })

  describe('Bypass Lock on Info', () => {
    it('toggle is initially unchecked', async () => {
      renderWithProviders(<BetaFeaturesTab />)

      await waitFor(() => {
        expect(
          screen.getByText('Enable bypass-lock for all borg info commands')
        ).toBeInTheDocument()
      })

      const infoSwitch = getSwitchByLabel('Enable bypass-lock for all borg info commands')
      expect(infoSwitch).not.toBeChecked()
    })

    it('can enable bypass lock on info', async () => {
      const user = userEvent.setup()
      vi.mocked(settingsAPI.updateSystemSettings).mockResolvedValue({} as AxiosResponse)

      renderWithProviders(<BetaFeaturesTab />)

      await waitFor(() => {
        expect(
          screen.getByText('Enable bypass-lock for all borg info commands')
        ).toBeInTheDocument()
      })

      const infoSwitch = getSwitchByLabel('Enable bypass-lock for all borg info commands')
      await user.click(infoSwitch)

      await waitFor(() => {
        expect(settingsAPI.updateSystemSettings).toHaveBeenCalledWith({
          bypass_lock_on_info: true,
        })
      })
    })

    it('shows success toast after enabling', async () => {
      const user = userEvent.setup()
      const { toast } = await import('react-hot-toast')
      vi.mocked(settingsAPI.updateSystemSettings).mockResolvedValue({} as AxiosResponse)

      renderWithProviders(<BetaFeaturesTab />)

      await waitFor(() => {
        expect(
          screen.getByText('Enable bypass-lock for all borg info commands')
        ).toBeInTheDocument()
      })

      const infoSwitch = getSwitchByLabel('Enable bypass-lock for all borg info commands')
      await user.click(infoSwitch)

      await waitFor(() => {
        expect(toast.success).toHaveBeenCalledWith('Setting updated successfully')
      })
    })

    it('reverts state on error', async () => {
      const user = userEvent.setup()
      const { toast } = await import('react-hot-toast')
      vi.mocked(settingsAPI.updateSystemSettings).mockRejectedValue(new Error('API Error'))

      renderWithProviders(<BetaFeaturesTab />)

      await waitFor(() => {
        expect(
          screen.getByText('Enable bypass-lock for all borg info commands')
        ).toBeInTheDocument()
      })

      const infoSwitch = getSwitchByLabel('Enable bypass-lock for all borg info commands')
      await user.click(infoSwitch)

      await waitFor(() => {
        expect(toast.error).toHaveBeenCalledWith('Failed to update setting: API Error')
        expect(infoSwitch).not.toBeChecked()
      })
    })

    it('shows bypass lock info description', async () => {
      renderWithProviders(<BetaFeaturesTab />)

      await waitFor(() => {
        expect(
          screen.getByText((_, element) => {
            const hasText = element?.textContent?.includes(
              'Adds --bypass-lock to all borg info commands'
            )
            const isDescription =
              element?.tagName === 'P' &&
              element?.textContent?.includes('This prevents lock contention')
            return (hasText && isDescription) ?? false
          })
        ).toBeInTheDocument()
      })
    })
  })

  describe('Bypass Lock on List', () => {
    it('toggle is initially unchecked', async () => {
      renderWithProviders(<BetaFeaturesTab />)

      await waitFor(() => {
        expect(
          screen.getByText('Enable bypass-lock for all borg list commands')
        ).toBeInTheDocument()
      })

      const listSwitch = getSwitchByLabel('Enable bypass-lock for all borg list commands')
      expect(listSwitch).not.toBeChecked()
    })

    it('can enable bypass lock on list', async () => {
      const user = userEvent.setup()
      vi.mocked(settingsAPI.updateSystemSettings).mockResolvedValue({} as AxiosResponse)

      renderWithProviders(<BetaFeaturesTab />)

      await waitFor(() => {
        expect(
          screen.getByText('Enable bypass-lock for all borg list commands')
        ).toBeInTheDocument()
      })

      const listSwitch = getSwitchByLabel('Enable bypass-lock for all borg list commands')
      await user.click(listSwitch)

      await waitFor(() => {
        expect(settingsAPI.updateSystemSettings).toHaveBeenCalledWith({
          bypass_lock_on_list: true,
        })
      })
    })

    it('shows bypass lock list description', async () => {
      renderWithProviders(<BetaFeaturesTab />)

      await waitFor(() => {
        expect(
          screen.getByText((_, element) => {
            const hasText = element?.textContent?.includes(
              'Adds --bypass-lock to all borg list commands'
            )
            const isDescription =
              element?.tagName === 'P' &&
              element?.textContent?.includes('This prevents lock contention')
            return (hasText && isDescription) ?? false
          })
        ).toBeInTheDocument()
      })
    })
  })

  describe('Borg 2 Fast Browse', () => {
    it('toggle is initially unchecked', async () => {
      renderWithProviders(<BetaFeaturesTab />)

      await waitFor(() => {
        expect(screen.getByText('Enable faster Borg 2 archive browsing')).toBeInTheDocument()
      })

      const fastBrowseSwitch = getSwitchByLabel('Enable faster Borg 2 archive browsing')
      expect(fastBrowseSwitch).not.toBeChecked()
    })

    it('can enable Borg 2 fast browse', async () => {
      const user = userEvent.setup()
      vi.mocked(settingsAPI.updateSystemSettings).mockResolvedValue({} as AxiosResponse)

      renderWithProviders(<BetaFeaturesTab />)

      await waitFor(() => {
        expect(screen.getByText('Enable faster Borg 2 archive browsing')).toBeInTheDocument()
      })

      const fastBrowseSwitch = getSwitchByLabel('Enable faster Borg 2 archive browsing')
      await user.click(fastBrowseSwitch)

      await waitFor(() => {
        expect(settingsAPI.updateSystemSettings).toHaveBeenCalledWith({
          borg2_fast_browse_beta_enabled: true,
        })
      })
    })

    it('shows Borg 2 fast browse description', async () => {
      renderWithProviders(<BetaFeaturesTab />)

      await waitFor(() => {
        expect(
          screen.getByText(
            /Uses depth-limited browsing for Borg 2 repositories to reduce payload size and improve responsiveness on very large archives/
          )
        ).toBeInTheDocument()
      })
    })
  })

  describe('MQTT Beta', () => {
    it('toggle is initially unchecked', async () => {
      renderWithProviders(<BetaFeaturesTab />)

      await waitFor(() => {
        expect(screen.getByText('Enable MQTT')).toBeInTheDocument()
      })

      const mqttSwitch = getSwitchByLabel('Enable MQTT')
      expect(mqttSwitch).not.toBeChecked()
    })

    it('can enable MQTT', async () => {
      const user = userEvent.setup()
      vi.mocked(settingsAPI.updateSystemSettings).mockResolvedValue({} as AxiosResponse)

      renderWithProviders(<BetaFeaturesTab />)

      await waitFor(() => {
        expect(screen.getByText('Enable MQTT')).toBeInTheDocument()
      })

      const mqttSwitch = getSwitchByLabel('Enable MQTT')
      await user.click(mqttSwitch)

      await waitFor(() => {
        expect(settingsAPI.updateSystemSettings).toHaveBeenCalledWith({
          mqtt_beta_enabled: true,
        })
      })
    })

    it('shows MQTT description', async () => {
      renderWithProviders(<BetaFeaturesTab />)

      await waitFor(() => {
        expect(screen.getByText('Activates MQTT integration in the UI.')).toBeInTheDocument()
      })
    })
  })

  it('does not render managed CLI agents as a beta feature', async () => {
    renderWithProviders(<BetaFeaturesTab />)

    await waitFor(() => {
      expect(screen.getByText('Beta Features')).toBeInTheDocument()
    })

    expect(screen.queryByText('Enable managed CLI agents')).not.toBeInTheDocument()
    expect(
      screen.queryByText(
        'Shows the Managed Agents navigation item and server-side agent enrollment workflow.'
      )
    ).not.toBeInTheDocument()
  })

  describe('Loading State', () => {
    it('disables all switches while mutation is pending', async () => {
      const user = userEvent.setup()
      vi.mocked(settingsAPI.updateSystemSettings).mockImplementation(() => new Promise(() => {}))

      renderWithProviders(<BetaFeaturesTab />)

      await waitFor(() => {
        expect(
          screen.getByText('Enable bypass-lock for all borg info commands')
        ).toBeInTheDocument()
      })

      const infoSwitch = getSwitchByLabel('Enable bypass-lock for all borg info commands')
      const switches = screen.getAllByRole('switch')
      await user.click(infoSwitch)

      await waitFor(() => {
        switches.forEach((sw) => {
          expect(sw).toBeDisabled()
        })
      })
    })
  })

  describe('Form Initialization', () => {
    it('loads and displays existing settings', async () => {
      const existingSettings = {
        settings: {
          bypass_lock_on_info: true,
          bypass_lock_on_list: true,
          lock_breaking_enabled: true,
          borg2_fast_browse_beta_enabled: true,
          mqtt_beta_enabled: true,
        },
      }

      renderWithProviders(<BetaFeaturesTab />, {
        queryClient: createSystemSettingsClient(existingSettings.settings),
      })

      await waitFor(() => {
        const switches = screen.getAllByRole('switch')
        switches.forEach((sw) => {
          expect(sw).toBeChecked()
        })
      })
    })

    it('handles null/undefined values with defaults', async () => {
      const settingsWithNulls = {
        settings: {},
      }

      renderWithProviders(<BetaFeaturesTab />, {
        queryClient: createSystemSettingsClient(settingsWithNulls.settings),
      })

      await waitFor(() => {
        expect(getSwitchByLabel('Enable bypass-lock for all borg info commands')).not.toBeChecked()
        expect(getSwitchByLabel('Enable bypass-lock for all borg list commands')).not.toBeChecked()
        expect(getSwitchByLabel('Allow manual repository lock breaking')).toBeChecked()
        expect(getSwitchByLabel('Enable faster Borg 2 archive browsing')).not.toBeChecked()
        expect(getSwitchByLabel('Enable MQTT')).not.toBeChecked()
      })
    })
  })

  describe('Multiple Toggle Interactions', () => {
    it('can toggle multiple settings independently', async () => {
      const user = userEvent.setup()
      vi.mocked(settingsAPI.updateSystemSettings).mockResolvedValue({} as AxiosResponse)

      renderWithProviders(<BetaFeaturesTab />)

      await waitFor(() => {
        expect(
          screen.getByText('Enable bypass-lock for all borg info commands')
        ).toBeInTheDocument()
      })

      const infoSwitch = getSwitchByLabel('Enable bypass-lock for all borg info commands')
      const listSwitch = getSwitchByLabel('Enable bypass-lock for all borg list commands')

      // Enable info
      await user.click(infoSwitch)
      await waitFor(() => {
        expect(settingsAPI.updateSystemSettings).toHaveBeenCalledWith({
          bypass_lock_on_info: true,
        })
      })

      // Enable list
      await user.click(listSwitch)
      await waitFor(() => {
        expect(settingsAPI.updateSystemSettings).toHaveBeenCalledWith({
          bypass_lock_on_list: true,
        })
      })

      expect(settingsAPI.updateSystemSettings).toHaveBeenCalledTimes(2)
    })

    it('can disable after enabling', async () => {
      const user = userEvent.setup()
      vi.mocked(settingsAPI.updateSystemSettings).mockResolvedValue({} as AxiosResponse)

      renderWithProviders(<BetaFeaturesTab />)

      await waitFor(() => {
        expect(screen.getByText('Enable MQTT')).toBeInTheDocument()
      })

      const mqttSwitch = getSwitchByLabel('Enable MQTT')

      // Enable
      await user.click(mqttSwitch)
      await waitFor(() => {
        expect(settingsAPI.updateSystemSettings).toHaveBeenCalledWith({
          mqtt_beta_enabled: true,
        })
      })

      // Mock updated settings
      vi.mocked(settingsAPI.getSystemSettings).mockResolvedValue({
        data: {
          settings: {
            ...mockSystemSettings.settings,
            borg2_fast_browse_beta_enabled: false,
            mqtt_beta_enabled: true,
          },
        },
      } as AxiosResponse)

      // Disable
      await user.click(mqttSwitch)
      await waitFor(() => {
        expect(settingsAPI.updateSystemSettings).toHaveBeenCalledWith({
          mqtt_beta_enabled: false,
        })
      })
    })
  })
})

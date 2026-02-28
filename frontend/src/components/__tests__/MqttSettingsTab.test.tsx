import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import MqttSettingsTab from '../MqttSettingsTab'
import { settingsAPI } from '@/services/api.ts'
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

describe('MqttSettingsTab', () => {
  const mockSystemSettings = {
    settings: {
      mqtt_enabled: false,
      mqtt_broker_url: '',
      mqtt_broker_port: 1883,
      mqtt_username: '',
      mqtt_client_id: 'borg-ui',
      mqtt_qos: 1,
      mqtt_tls_enabled: false,
      mqtt_tls_ca_cert: '',
      mqtt_tls_client_cert: '',
      mqtt_tls_client_key: '',
      mqtt_password_set: false,
    },
  }

  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(settingsAPI.getSystemSettings).mockResolvedValue({
      data: mockSystemSettings,
    } as AxiosResponse)
  })

  describe('Rendering', () => {
    it('shows loading spinner while fetching settings', () => {
      vi.mocked(settingsAPI.getSystemSettings).mockImplementation(() => new Promise(() => {}))
      renderWithProviders(<MqttSettingsTab />)
      expect(screen.getByRole('progressbar')).toBeInTheDocument()
    })

    it('renders MQTT settings header', async () => {
      renderWithProviders(<MqttSettingsTab />)
      await waitFor(() => {
        expect(screen.getByText('MQTT Settings')).toBeInTheDocument()
      })
    })

    it('renders description text', async () => {
      renderWithProviders(<MqttSettingsTab />)
      await waitFor(() => {
        expect(
          screen.getByText(/Configure MQTT broker connection for Home Assistant state publishing/)
        ).toBeInTheDocument()
      })
    })

    it('renders Save Settings button', async () => {
      renderWithProviders(<MqttSettingsTab />)
      await waitFor(() => {
        expect(screen.getByRole('button', { name: /Save Settings/i })).toBeInTheDocument()
      })
    })

    it('renders Enable MQTT Publishing checkbox', async () => {
      renderWithProviders(<MqttSettingsTab />)
      await waitFor(() => {
        expect(screen.getByLabelText('Enable MQTT Publishing')).toBeInTheDocument()
      })
    })

    it('Save button is disabled initially when no changes', async () => {
      renderWithProviders(<MqttSettingsTab />)
      await waitFor(() => {
        const saveButton = screen.getByRole('button', { name: /Save Settings/i })
        expect(saveButton).toBeDisabled()
      })
    })
  })

  describe('MQTT Connection Settings', () => {
    it('shows MQTT connection fields when MQTT is enabled', async () => {
      const user = userEvent.setup()
      renderWithProviders(<MqttSettingsTab />)

      await waitFor(() => {
        expect(screen.getByLabelText('Enable MQTT Publishing')).toBeInTheDocument()
      })

      await user.click(screen.getByLabelText('Enable MQTT Publishing'))

      expect(screen.getByLabelText(/Broker URL/i)).toBeInTheDocument()
      expect(screen.getByLabelText('Broker Port')).toBeInTheDocument()
      expect(screen.getByLabelText('Username')).toBeInTheDocument()
      expect(screen.getByLabelText('Password')).toBeInTheDocument()
      expect(screen.getByLabelText('Client ID')).toBeInTheDocument()
      expect(screen.getByLabelText('QoS Level')).toBeInTheDocument()
    })

    it('hides MQTT connection fields when MQTT is disabled', async () => {
      renderWithProviders(<MqttSettingsTab />)

      await waitFor(() => {
        expect(screen.getByLabelText('Enable MQTT Publishing')).toBeInTheDocument()
      })

      expect(screen.queryByLabelText('Broker URL')).not.toBeInTheDocument()
      expect(screen.queryByLabelText('Broker Port')).not.toBeInTheDocument()
    })

    it('can update broker URL', async () => {
      const user = userEvent.setup()
      renderWithProviders(<MqttSettingsTab />)

      await waitFor(() => {
        expect(screen.getByLabelText('Enable MQTT Publishing')).toBeInTheDocument()
      })

      await user.click(screen.getByLabelText('Enable MQTT Publishing'))

      const brokerUrlInput = screen.getByLabelText(/Broker URL/i)
      await user.clear(brokerUrlInput)
      await user.type(brokerUrlInput, 'mqtt.example.com')

      expect(brokerUrlInput).toHaveValue('mqtt.example.com')
    })

    it('can update broker port', async () => {
      const user = userEvent.setup()
      renderWithProviders(<MqttSettingsTab />)

      await waitFor(() => {
        expect(screen.getByLabelText('Enable MQTT Publishing')).toBeInTheDocument()
      })

      await user.click(screen.getByLabelText('Enable MQTT Publishing'))

      const brokerPortInput = screen.getByLabelText('Broker Port')
      await user.clear(brokerPortInput)
      await user.type(brokerPortInput, '8883')

      expect(brokerPortInput).toHaveValue(8883)
    })

    it('can update username', async () => {
      const user = userEvent.setup()
      renderWithProviders(<MqttSettingsTab />)

      await waitFor(() => {
        expect(screen.getByLabelText('Enable MQTT Publishing')).toBeInTheDocument()
      })

      await user.click(screen.getByLabelText('Enable MQTT Publishing'))

      const usernameInput = screen.getByLabelText('Username')
      await user.type(usernameInput, 'testuser')

      expect(usernameInput).toHaveValue('testuser')
    })

    it('can update password', async () => {
      const user = userEvent.setup()
      renderWithProviders(<MqttSettingsTab />)

      await waitFor(() => {
        expect(screen.getByLabelText('Enable MQTT Publishing')).toBeInTheDocument()
      })

      await user.click(screen.getByLabelText('Enable MQTT Publishing'))

      const passwordInput = screen.getByLabelText('Password')
      await user.type(passwordInput, 'secretpass')

      expect(passwordInput).toHaveValue('secretpass')
    })

    it('password input is hidden by default', async () => {
      const user = userEvent.setup()
      renderWithProviders(<MqttSettingsTab />)

      await waitFor(() => {
        expect(screen.getByLabelText('Enable MQTT Publishing')).toBeInTheDocument()
      })

      await user.click(screen.getByLabelText('Enable MQTT Publishing'))

      const passwordInput = screen.getByLabelText('Password')
      expect(passwordInput).toHaveAttribute('type', 'password')
    })

    it('can toggle password visibility', async () => {
      const user = userEvent.setup()
      renderWithProviders(<MqttSettingsTab />)

      await waitFor(() => {
        expect(screen.getByLabelText('Enable MQTT Publishing')).toBeInTheDocument()
      })

      await user.click(screen.getByLabelText('Enable MQTT Publishing'))

      const passwordInput = screen.getByLabelText('Password')
      await user.type(passwordInput, 'testpass')

      // Find the visibility toggle button by checking parent structure
      // The button contains the Eye/EyeOff icon within the password field's endAdornment
      const passwordField =
        passwordInput.closest('.MuiTextField-root') || passwordInput.parentElement?.parentElement
      const visibilityToggle = passwordField?.querySelector('button')

      if (visibilityToggle) {
        await user.click(visibilityToggle)
        expect(passwordInput).toHaveAttribute('type', 'text')

        await user.click(visibilityToggle)
        expect(passwordInput).toHaveAttribute('type', 'password')
      }
    })

    it('can update client ID', async () => {
      const user = userEvent.setup()
      renderWithProviders(<MqttSettingsTab />)

      await waitFor(() => {
        expect(screen.getByLabelText('Enable MQTT Publishing')).toBeInTheDocument()
      })

      await user.click(screen.getByLabelText('Enable MQTT Publishing'))

      const clientIdInput = screen.getByLabelText('Client ID')
      await user.clear(clientIdInput)
      await user.type(clientIdInput, 'custom-client-id')

      expect(clientIdInput).toHaveValue('custom-client-id')
    })

    it('can update QoS level', async () => {
      const user = userEvent.setup()
      renderWithProviders(<MqttSettingsTab />)

      await waitFor(() => {
        expect(screen.getByLabelText('Enable MQTT Publishing')).toBeInTheDocument()
      })

      await user.click(screen.getByLabelText('Enable MQTT Publishing'))

      const qosInput = screen.getByLabelText('QoS Level')
      await user.clear(qosInput)
      await user.type(qosInput, '2')

      expect(qosInput).toHaveValue(2)
    })

    it('clamps QoS level between 0 and 2', async () => {
      const user = userEvent.setup()
      renderWithProviders(<MqttSettingsTab />)

      await waitFor(() => {
        expect(screen.getByLabelText('Enable MQTT Publishing')).toBeInTheDocument()
      })

      await user.click(screen.getByLabelText('Enable MQTT Publishing'))

      const qosInput = screen.getByLabelText('QoS Level')
      await user.clear(qosInput)
      await user.type(qosInput, '5')

      // Value should be clamped to 2
      expect(qosInput).toHaveValue(2)
    })
  })

  describe('TLS/SSL Settings', () => {
    it('shows TLS card when MQTT is enabled', async () => {
      const user = userEvent.setup()
      renderWithProviders(<MqttSettingsTab />)

      await waitFor(() => {
        expect(screen.getByLabelText('Enable MQTT Publishing')).toBeInTheDocument()
      })

      await user.click(screen.getByLabelText('Enable MQTT Publishing'))

      await waitFor(() => {
        expect(screen.getByText('TLS/SSL Configuration')).toBeInTheDocument()
        expect(screen.getByLabelText('Enable TLS/SSL')).toBeInTheDocument()
      })
    })

    it('hides TLS card when MQTT is disabled', async () => {
      renderWithProviders(<MqttSettingsTab />)

      await waitFor(() => {
        expect(screen.getByLabelText('Enable MQTT Publishing')).toBeInTheDocument()
      })

      expect(screen.queryByText('TLS/SSL Configuration')).not.toBeInTheDocument()
    })

    it('shows TLS fields when TLS is enabled', async () => {
      const user = userEvent.setup()
      renderWithProviders(<MqttSettingsTab />)

      await waitFor(() => {
        expect(screen.getByLabelText('Enable MQTT Publishing')).toBeInTheDocument()
      })

      await user.click(screen.getByLabelText('Enable MQTT Publishing'))
      await user.click(screen.getByLabelText('Enable TLS/SSL'))

      await waitFor(() => {
        expect(screen.getByLabelText('CA Certificate Path')).toBeInTheDocument()
        expect(screen.getByLabelText('Client Certificate Path')).toBeInTheDocument()
        expect(screen.getByLabelText('Client Key Path')).toBeInTheDocument()
      })
    })

    it('can update CA certificate path', async () => {
      const user = userEvent.setup()
      renderWithProviders(<MqttSettingsTab />)

      await waitFor(() => {
        expect(screen.getByLabelText('Enable MQTT Publishing')).toBeInTheDocument()
      })

      await user.click(screen.getByLabelText('Enable MQTT Publishing'))
      await user.click(screen.getByLabelText('Enable TLS/SSL'))

      const caCertInput = screen.getByLabelText('CA Certificate Path')
      await user.type(caCertInput, '/certs/ca.crt')

      expect(caCertInput).toHaveValue('/certs/ca.crt')
    })

    it('shows TLS certificate note', async () => {
      const user = userEvent.setup()
      renderWithProviders(<MqttSettingsTab />)

      await waitFor(() => {
        expect(screen.getByLabelText('Enable MQTT Publishing')).toBeInTheDocument()
      })

      await user.click(screen.getByLabelText('Enable MQTT Publishing'))
      await user.click(screen.getByLabelText('Enable TLS/SSL'))

      await waitFor(() => {
        expect(
          screen.getByText(/Certificate paths are relative to the container's filesystem/)
        ).toBeInTheDocument()
      })
    })
  })

  describe('Save Settings', () => {
    it('enables save button when changes are made', async () => {
      const user = userEvent.setup()
      renderWithProviders(<MqttSettingsTab />)

      await waitFor(() => {
        expect(screen.getByLabelText('Enable MQTT Publishing')).toBeInTheDocument()
      })

      const saveButton = screen.getByRole('button', { name: /Save Settings/i })
      expect(saveButton).toBeDisabled()

      await user.click(screen.getByLabelText('Enable MQTT Publishing'))

      await waitFor(() => {
        expect(saveButton).not.toBeDisabled()
      })
    })

    it('saves MQTT settings successfully', async () => {
      const user = userEvent.setup()
      vi.mocked(settingsAPI.updateSystemSettings).mockResolvedValue({} as AxiosResponse)

      renderWithProviders(<MqttSettingsTab />)

      await waitFor(() => {
        expect(screen.getByLabelText('Enable MQTT Publishing')).toBeInTheDocument()
      })

      await user.click(screen.getByLabelText('Enable MQTT Publishing'))

      const brokerUrlInput = screen.getByLabelText(/Broker URL/i)
      await user.type(brokerUrlInput, 'mqtt.example.com')

      const saveButton = screen.getByRole('button', { name: /Save Settings/i })
      await user.click(saveButton)

      await waitFor(() => {
        expect(settingsAPI.updateSystemSettings).toHaveBeenCalledWith(
          expect.objectContaining({
            mqtt_enabled: true,
            mqtt_broker_url: 'mqtt.example.com',
          })
        )
      })
    })

    it('includes password only when changed', async () => {
      const user = userEvent.setup()
      vi.mocked(settingsAPI.updateSystemSettings).mockResolvedValue({} as AxiosResponse)

      renderWithProviders(<MqttSettingsTab />)

      await waitFor(() => {
        expect(screen.getByLabelText('Enable MQTT Publishing')).toBeInTheDocument()
      })

      await user.click(screen.getByLabelText('Enable MQTT Publishing'))

      const passwordInput = screen.getByLabelText('Password')
      await user.type(passwordInput, 'newpassword')

      const saveButton = screen.getByRole('button', { name: /Save Settings/i })
      await user.click(saveButton)

      await waitFor(() => {
        expect(settingsAPI.updateSystemSettings).toHaveBeenCalledWith(
          expect.objectContaining({
            mqtt_password: 'newpassword',
          })
        )
      })
    })

    it('sends null for empty optional fields', async () => {
      const user = userEvent.setup()
      vi.mocked(settingsAPI.updateSystemSettings).mockResolvedValue({} as AxiosResponse)

      renderWithProviders(<MqttSettingsTab />)

      await waitFor(() => {
        expect(screen.getByLabelText('Enable MQTT Publishing')).toBeInTheDocument()
      })

      await user.click(screen.getByLabelText('Enable MQTT Publishing'))

      const saveButton = screen.getByRole('button', { name: /Save Settings/i })
      await user.click(saveButton)

      await waitFor(() => {
        expect(settingsAPI.updateSystemSettings).toHaveBeenCalledWith(
          expect.objectContaining({
            mqtt_broker_url: null,
            mqtt_username: null,
            mqtt_tls_ca_cert: null,
            mqtt_tls_client_cert: null,
            mqtt_tls_client_key: null,
          })
        )
      })
    })

    it('shows saving state while saving', async () => {
      const user = userEvent.setup()
      vi.mocked(settingsAPI.updateSystemSettings).mockImplementation(() => new Promise(() => {}))

      renderWithProviders(<MqttSettingsTab />)

      await waitFor(() => {
        expect(screen.getByLabelText('Enable MQTT Publishing')).toBeInTheDocument()
      })

      await user.click(screen.getByLabelText('Enable MQTT Publishing'))

      const saveButton = screen.getByRole('button', { name: /Save Settings/i })
      await user.click(saveButton)

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /Saving.../i })).toBeInTheDocument()
        expect(screen.getByRole('button', { name: /Saving.../i })).toBeDisabled()
      })
    })

    it('disables save button after successful save', async () => {
      const user = userEvent.setup()
      vi.mocked(settingsAPI.updateSystemSettings).mockResolvedValue({} as AxiosResponse)

      renderWithProviders(<MqttSettingsTab />)

      await waitFor(() => {
        expect(screen.getByLabelText('Enable MQTT Publishing')).toBeInTheDocument()
      })

      await user.click(screen.getByLabelText('Enable MQTT Publishing'))

      const saveButton = screen.getByRole('button', { name: /Save Settings/i })
      await user.click(saveButton)

      await waitFor(() => {
        expect(saveButton).toBeDisabled()
      })
    })
  })

  describe('Error Handling', () => {
    it('handles save error with array of errors', async () => {
      const user = userEvent.setup()
      const { toast } = await import('react-hot-toast')

      vi.mocked(settingsAPI.updateSystemSettings).mockRejectedValue({
        response: {
          data: [{ msg: 'Error 1' }, { msg: 'Error 2' }],
        },
      })

      renderWithProviders(<MqttSettingsTab />)

      await waitFor(() => {
        expect(screen.getByLabelText('Enable MQTT Publishing')).toBeInTheDocument()
      })

      await user.click(screen.getByLabelText('Enable MQTT Publishing'))

      const saveButton = screen.getByRole('button', { name: /Save Settings/i })
      await user.click(saveButton)

      await waitFor(() => {
        expect(toast.error).toHaveBeenCalledWith('Error 1, Error 2')
      })
    })

    it('handles save error with detail message', async () => {
      const user = userEvent.setup()
      const { toast } = await import('react-hot-toast')

      vi.mocked(settingsAPI.updateSystemSettings).mockRejectedValue({
        response: {
          data: { detail: 'Connection failed' },
        },
      })

      renderWithProviders(<MqttSettingsTab />)

      await waitFor(() => {
        expect(screen.getByLabelText('Enable MQTT Publishing')).toBeInTheDocument()
      })

      await user.click(screen.getByLabelText('Enable MQTT Publishing'))

      const saveButton = screen.getByRole('button', { name: /Save Settings/i })
      await user.click(saveButton)

      await waitFor(() => {
        expect(toast.error).toHaveBeenCalledWith('Connection failed')
      })
    })

    it('handles save error with generic message', async () => {
      const user = userEvent.setup()
      const { toast } = await import('react-hot-toast')

      vi.mocked(settingsAPI.updateSystemSettings).mockRejectedValue(new Error('Network error'))

      renderWithProviders(<MqttSettingsTab />)

      await waitFor(() => {
        expect(screen.getByLabelText('Enable MQTT Publishing')).toBeInTheDocument()
      })

      await user.click(screen.getByLabelText('Enable MQTT Publishing'))

      const saveButton = screen.getByRole('button', { name: /Save Settings/i })
      await user.click(saveButton)

      await waitFor(() => {
        expect(toast.error).toHaveBeenCalledWith('Failed to save MQTT settings')
      })
    })
  })

  describe('Form Initialization', () => {
    it('loads and displays existing MQTT settings', async () => {
      const existingSettings = {
        settings: {
          mqtt_enabled: true,
          mqtt_broker_url: 'existing.mqtt.com',
          mqtt_broker_port: 8883,
          mqtt_username: 'existinguser',
          mqtt_client_id: 'custom-id',
          mqtt_qos: 2,
          mqtt_tls_enabled: true,
          mqtt_tls_ca_cert: '/existing/ca.crt',
          mqtt_tls_client_cert: '/existing/client.crt',
          mqtt_tls_client_key: '/existing/client.key',
          mqtt_password_set: true,
        },
      }

      vi.mocked(settingsAPI.getSystemSettings).mockResolvedValue({
        data: existingSettings,
      } as AxiosResponse)

      renderWithProviders(<MqttSettingsTab />)

      await waitFor(() => {
        expect(screen.getByLabelText('Enable MQTT Publishing')).toBeChecked()
        expect(screen.getByLabelText(/Broker URL/i)).toHaveValue('existing.mqtt.com')
        expect(screen.getByLabelText('Broker Port')).toHaveValue(8883)
        expect(screen.getByLabelText('Username')).toHaveValue('existinguser')
        expect(screen.getByLabelText('Client ID')).toHaveValue('custom-id')
        expect(screen.getByLabelText('QoS Level')).toHaveValue(2)
        expect(screen.getByLabelText('Enable TLS/SSL')).toBeChecked()
        expect(screen.getByLabelText('CA Certificate Path')).toHaveValue('/existing/ca.crt')
      })
    })

    it('shows password is set message when password exists', async () => {
      const existingSettings = {
        settings: {
          ...mockSystemSettings.settings,
          mqtt_enabled: true,
          mqtt_password_set: true,
        },
      }

      vi.mocked(settingsAPI.getSystemSettings).mockResolvedValue({
        data: existingSettings,
      } as AxiosResponse)

      renderWithProviders(<MqttSettingsTab />)

      await waitFor(() => {
        expect(screen.getByText('Password is set')).toBeInTheDocument()
      })
    })
  })
})

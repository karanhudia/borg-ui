import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import AnalyticsConsentBanner from '../AnalyticsConsentBanner'
import { settingsAPI } from '../../services/api'
import { resetOptOutCache, trackConsentResponse } from '../../utils/matomo'
import { AxiosResponse } from 'axios'

vi.mock('../../services/api', () => ({
  settingsAPI: {
    updatePreferences: vi.fn(),
  },
}))

vi.mock('../../utils/matomo', () => ({
  resetOptOutCache: vi.fn(),
  trackConsentResponse: vi.fn(),
}))

describe('AnalyticsConsentBanner', () => {
  const mockOnConsentGiven = vi.fn()

  beforeEach(() => {
    mockOnConsentGiven.mockClear()
    vi.mocked(settingsAPI.updatePreferences).mockClear()
    vi.mocked(resetOptOutCache).mockClear()
    vi.mocked(trackConsentResponse).mockClear()
  })

  describe('Rendering', () => {
    it('renders banner title', () => {
      render(<AnalyticsConsentBanner onConsentGiven={mockOnConsentGiven} />)
      expect(screen.getByText('Help Improve Borg UI')).toBeInTheDocument()
    })

    it('renders description text', () => {
      render(<AnalyticsConsentBanner onConsentGiven={mockOnConsentGiven} />)
      expect(
        screen.getByText(/We collect anonymous usage data to understand how Borg UI is used/)
      ).toBeInTheDocument()
    })

    it('renders privacy assurance text', () => {
      render(<AnalyticsConsentBanner onConsentGiven={mockOnConsentGiven} />)
      expect(
        screen.getByText(/No personal information, IP addresses, hostnames/)
      ).toBeInTheDocument()
    })

    it('renders link to analytics dashboard', () => {
      render(<AnalyticsConsentBanner onConsentGiven={mockOnConsentGiven} />)
      const link = screen.getByText('View our public analytics dashboard')
      expect(link).toBeInTheDocument()
      expect(link).toHaveAttribute('href', 'https://analytics.nullcodeai.dev/')
      expect(link).toHaveAttribute('target', '_blank')
    })

    it('renders analytics toggle switch', () => {
      render(<AnalyticsConsentBanner onConsentGiven={mockOnConsentGiven} />)
      expect(screen.getByRole('switch')).toBeInTheDocument()
      expect(screen.getByText('Enable anonymous analytics')).toBeInTheDocument()
    })

    it('renders Continue button', () => {
      render(<AnalyticsConsentBanner onConsentGiven={mockOnConsentGiven} />)
      expect(screen.getByRole('button', { name: 'Continue' })).toBeInTheDocument()
    })

    it('renders settings note', () => {
      render(<AnalyticsConsentBanner onConsentGiven={mockOnConsentGiven} />)
      expect(screen.getByText(/You can change this anytime in Settings/)).toBeInTheDocument()
    })

    it('has analytics enabled by default', () => {
      render(<AnalyticsConsentBanner onConsentGiven={mockOnConsentGiven} />)
      const checkbox = screen.getByRole('switch')
      expect(checkbox).toBeChecked()
    })
  })

  describe('User interactions', () => {
    it('can toggle analytics off', async () => {
      const user = userEvent.setup()
      render(<AnalyticsConsentBanner onConsentGiven={mockOnConsentGiven} />)

      const checkbox = screen.getByRole('switch')
      expect(checkbox).toBeChecked()

      await user.click(checkbox)
      expect(checkbox).not.toBeChecked()
    })

    it('can toggle analytics back on', async () => {
      const user = userEvent.setup()
      render(<AnalyticsConsentBanner onConsentGiven={mockOnConsentGiven} />)

      const checkbox = screen.getByRole('switch')
      await user.click(checkbox) // Turn off
      await user.click(checkbox) // Turn back on
      expect(checkbox).toBeChecked()
    })
  })

  describe('Form submission with analytics enabled', () => {
    beforeEach(() => {
      vi.mocked(settingsAPI.updatePreferences).mockResolvedValue({} as AxiosResponse)
      vi.mocked(resetOptOutCache).mockResolvedValue(undefined)
    })

    it('tracks consent response before saving', async () => {
      const user = userEvent.setup()
      render(<AnalyticsConsentBanner onConsentGiven={mockOnConsentGiven} />)

      await user.click(screen.getByRole('button', { name: 'Continue' }))

      await waitFor(() => {
        expect(trackConsentResponse).toHaveBeenCalledWith(true)
      })
    })

    it('saves preferences with analytics enabled', async () => {
      const user = userEvent.setup()
      render(<AnalyticsConsentBanner onConsentGiven={mockOnConsentGiven} />)

      await user.click(screen.getByRole('button', { name: 'Continue' }))

      await waitFor(() => {
        expect(settingsAPI.updatePreferences).toHaveBeenCalledWith({
          analytics_enabled: true,
          analytics_consent_given: true,
        })
      })
    })

    it('resets opt-out cache after saving', async () => {
      const user = userEvent.setup()
      render(<AnalyticsConsentBanner onConsentGiven={mockOnConsentGiven} />)

      await user.click(screen.getByRole('button', { name: 'Continue' }))

      await waitFor(() => {
        expect(resetOptOutCache).toHaveBeenCalled()
      })
    })

    it('calls onConsentGiven callback after saving', async () => {
      const user = userEvent.setup()
      render(<AnalyticsConsentBanner onConsentGiven={mockOnConsentGiven} />)

      await user.click(screen.getByRole('button', { name: 'Continue' }))

      await waitFor(() => {
        expect(mockOnConsentGiven).toHaveBeenCalledTimes(1)
      })
    })
  })

  describe('Form submission with analytics disabled', () => {
    beforeEach(() => {
      vi.mocked(settingsAPI.updatePreferences).mockResolvedValue({} as AxiosResponse)
      vi.mocked(resetOptOutCache).mockResolvedValue(undefined)
    })

    it('tracks consent response with false', async () => {
      const user = userEvent.setup()
      render(<AnalyticsConsentBanner onConsentGiven={mockOnConsentGiven} />)

      // Disable analytics
      await user.click(screen.getByRole('switch'))
      await user.click(screen.getByRole('button', { name: 'Continue' }))

      await waitFor(() => {
        expect(trackConsentResponse).toHaveBeenCalledWith(false)
      })
    })

    it('saves preferences with analytics disabled', async () => {
      const user = userEvent.setup()
      render(<AnalyticsConsentBanner onConsentGiven={mockOnConsentGiven} />)

      // Disable analytics
      await user.click(screen.getByRole('switch'))
      await user.click(screen.getByRole('button', { name: 'Continue' }))

      await waitFor(() => {
        expect(settingsAPI.updatePreferences).toHaveBeenCalledWith({
          analytics_enabled: false,
          analytics_consent_given: true,
        })
      })
    })
  })

  describe('Loading state', () => {
    it('shows Saving... text while processing', async () => {
      vi.mocked(settingsAPI.updatePreferences).mockImplementation(() => new Promise(() => {}))
      const user = userEvent.setup()
      render(<AnalyticsConsentBanner onConsentGiven={mockOnConsentGiven} />)

      await user.click(screen.getByRole('button', { name: 'Continue' }))

      await waitFor(() => {
        expect(screen.getByRole('button', { name: 'Saving...' })).toBeInTheDocument()
      })
    })

    it('disables Continue button while saving', async () => {
      vi.mocked(settingsAPI.updatePreferences).mockImplementation(() => new Promise(() => {}))
      const user = userEvent.setup()
      render(<AnalyticsConsentBanner onConsentGiven={mockOnConsentGiven} />)

      await user.click(screen.getByRole('button', { name: 'Continue' }))

      await waitFor(() => {
        expect(screen.getByRole('button', { name: 'Saving...' })).toBeDisabled()
      })
    })

    it('disables toggle switch while saving', async () => {
      vi.mocked(settingsAPI.updatePreferences).mockImplementation(() => new Promise(() => {}))
      const user = userEvent.setup()
      render(<AnalyticsConsentBanner onConsentGiven={mockOnConsentGiven} />)

      await user.click(screen.getByRole('button', { name: 'Continue' }))

      await waitFor(() => {
        expect(screen.getByRole('switch')).toBeDisabled()
      })
    })
  })

  describe('Error handling', () => {
    it('still calls onConsentGiven when API fails', async () => {
      const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
      vi.mocked(settingsAPI.updatePreferences).mockRejectedValue(new Error('API Error'))
      const user = userEvent.setup()
      render(<AnalyticsConsentBanner onConsentGiven={mockOnConsentGiven} />)

      await user.click(screen.getByRole('button', { name: 'Continue' }))

      await waitFor(() => {
        expect(mockOnConsentGiven).toHaveBeenCalledTimes(1)
      })

      consoleSpy.mockRestore()
    })

    it('logs error when API fails', async () => {
      const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
      vi.mocked(settingsAPI.updatePreferences).mockRejectedValue(new Error('API Error'))
      const user = userEvent.setup()
      render(<AnalyticsConsentBanner onConsentGiven={mockOnConsentGiven} />)

      await user.click(screen.getByRole('button', { name: 'Continue' }))

      await waitFor(() => {
        expect(consoleSpy).toHaveBeenCalledWith(
          'Failed to save analytics preference:',
          expect.any(Error)
        )
      })

      consoleSpy.mockRestore()
    })
  })
})

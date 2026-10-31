import { afterEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, screen, waitFor } from '@testing-library/react'
import { licensingAPI } from '../../services/api'
import { renderWithProviders } from '../../test/test-utils'
import { liveOfferId, recordPaywallIntent } from '../../utils/paywallOffer'
import PaywallOffer from '../PaywallOffer'

const plan = vi.hoisted(() => ({ uiState: 'full_access_expired' }))

vi.mock('../../hooks/usePlan', () => ({
  usePlan: () => ({
    plan: 'community',
    features: {},
    entitlement: { ui_state: plan.uiState },
    can: () => false,
  }),
}))
vi.mock('../../services/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../services/api')>()
  return { ...actual, licensingAPI: { ...actual.licensingAPI, paywallOffer: vi.fn() } }
})

const DAY = 86_400_000
const threeDays = () =>
  [0, 1, 2].forEach((i) => recordPaywallIntent(new Date(Date.now() - i * DAY)))

describe('PaywallOffer', () => {
  afterEach(() => {
    localStorage.clear()
    plan.uiState = 'full_access_expired'
  })

  it('shows nothing until the user has asked on three days', () => {
    recordPaywallIntent()
    renderWithProviders(<PaywallOffer surface="test" />)
    expect(screen.queryByRole('button', { name: /claim 5% off/i })).not.toBeInTheDocument()
  })

  it('shows nothing on a paid or running plan', () => {
    threeDays()
    plan.uiState = 'paid_active'
    renderWithProviders(<PaywallOffer surface="test" />)
    expect(screen.queryByRole('button', { name: /claim/i })).not.toBeInTheDocument()
  })

  it('claims once and puts the offer on the buy links', async () => {
    threeDays()
    const expires = new Date(Date.now() + 7 * DAY).toISOString()
    vi.mocked(licensingAPI.paywallOffer).mockResolvedValue({
      data: { result: 'issued', offer_id: 'ofr_1', percent: 5, expires_at: expires },
    } as never)
    renderWithProviders(<PaywallOffer surface="test" />)
    fireEvent.click(screen.getByRole('button', { name: /claim 5% off/i }))
    await waitFor(() =>
      expect(screen.getByText(/your 5% offer is on every buy link/i)).toBeInTheDocument()
    )
    expect(licensingAPI.paywallOffer).toHaveBeenCalledWith('repeat', 3)
    expect(liveOfferId()).toBe('ofr_1')
  })

  it('says so once when the service refuses, and never offers again', async () => {
    threeDays()
    vi.mocked(licensingAPI.paywallOffer).mockResolvedValue({
      data: { result: 'denied', reason: 'offer_already_used' },
    } as never)
    const { unmount } = renderWithProviders(<PaywallOffer surface="test" />)
    fireEvent.click(screen.getByRole('button', { name: /claim 5% off/i }))
    await waitFor(() =>
      expect(screen.getByText(/isn't available for this install/i)).toBeInTheDocument()
    )
    unmount()
    renderWithProviders(<PaywallOffer surface="test" />)
    expect(screen.queryByRole('button', { name: /claim/i })).not.toBeInTheDocument()
  })
  it('keeps the claim button after a failed request and succeeds on retry', async () => {
    threeDays()
    const expires = new Date(Date.now() + 7 * DAY).toISOString()
    vi.mocked(licensingAPI.paywallOffer)
      .mockRejectedValueOnce(new Error('400'))
      .mockResolvedValueOnce({
        data: { result: 'issued', offer_id: 'ofr_2', percent: 5, expires_at: expires },
      } as never)
    renderWithProviders(<PaywallOffer surface="test" />)
    fireEvent.click(screen.getByRole('button', { name: /claim 5% off/i }))
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent(/try again/i))
    expect(screen.queryByText(/isn't available for this install/i)).not.toBeInTheDocument()
    expect(localStorage.getItem('borgui.paywallOffer')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: /claim 5% off/i }))
    await waitFor(() => expect(liveOfferId()).toBe('ofr_2'))
  })
})

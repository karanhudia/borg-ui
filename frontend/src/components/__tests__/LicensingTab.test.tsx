import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderWithProviders, screen, userEvent, waitFor } from '../../test/test-utils'
import LicensingTab from '../LicensingTab'
import { BUY_URL } from '../../utils/externalLinks'

const { refreshMock, activateMock, deactivateMock, trackPlanMock, invalidateQueriesMock } =
  vi.hoisted(() => ({
    refreshMock: vi.fn(),
    activateMock: vi.fn(),
    deactivateMock: vi.fn(),
    trackPlanMock: vi.fn(),
    invalidateQueriesMock: vi.fn(),
  }))

vi.mock('../../services/api', () => ({
  licensingAPI: {
    refresh: () => refreshMock(),
    activate: (key: string) => activateMock(key),
    deactivate: () => deactivateMock(),
  },
}))

vi.mock('@tanstack/react-query', async () => {
  const actual =
    await vi.importActual<typeof import('@tanstack/react-query')>('@tanstack/react-query')
  return {
    ...actual,
    useQueryClient: () => ({
      invalidateQueries: invalidateQueriesMock,
    }),
  }
})

vi.mock('../../hooks/usePlan', () => ({
  usePlan: () => ({
    plan: 'pro',
    entitlement: {
      access_level: 'pro',
      ui_state: 'paid_active',
      status: 'active',
      is_full_access: false,
      license_id: 'lic_123',
      instance_id: 'instance_123',
      expires_at: '2026-12-31T00:00:00.000Z',
    },
  }),
}))

vi.mock('../../hooks/useAnalytics', () => ({
  useAnalytics: () => ({
    trackPlan: trackPlanMock,
    EventAction: {
      VIEW: 'View',
      START: 'Start',
      COMPLETE: 'Complete',
      FAIL: 'Fail',
    },
  }),
}))

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

describe('LicensingTab', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    refreshMock.mockResolvedValue({ data: {} })
    activateMock.mockResolvedValue({ data: {} })
    deactivateMock.mockResolvedValue({ data: {} })
    invalidateQueriesMock.mockResolvedValue(undefined)
  })

  it('tracks a plan view with entitlement context on render', async () => {
    renderWithProviders(<LicensingTab />)

    await waitFor(() => {
      expect(trackPlanMock).toHaveBeenCalledWith('View', {
        surface: 'licensing_tab',
        current_plan: 'pro',
        access_level: 'pro',
        ui_state: 'paid_active',
        status: 'active',
        is_full_access: false,
        has_license_id: true,
      })
    })
  })

  it('tracks activation with properties and the license key length', async () => {
    const user = userEvent.setup()

    renderWithProviders(<LicensingTab />)

    await user.type(screen.getByLabelText(/licence key/i), 'BORG-1234-5678-9012')
    await user.click(screen.getByRole('button', { name: /replace licence/i }))

    await waitFor(() => {
      expect(activateMock).toHaveBeenCalledWith('BORG-1234-5678-9012')
      expect(trackPlanMock).toHaveBeenCalledWith('Start', {
        surface: 'licensing_tab',
        current_plan: 'pro',
        access_level: 'pro',
        ui_state: 'paid_active',
        status: 'active',
        is_full_access: false,
        has_license_id: true,
        operation: 'replace_license',
        license_key_length: 19,
      })
      expect(trackPlanMock).toHaveBeenCalledWith('Complete', {
        surface: 'licensing_tab',
        current_plan: 'pro',
        access_level: 'pro',
        ui_state: 'paid_active',
        status: 'active',
        is_full_access: false,
        has_license_id: true,
        operation: 'replace_license',
        license_key_length: 19,
      })
    })
  })

  it('tracks refresh and deactivate actions', async () => {
    const user = userEvent.setup()

    renderWithProviders(<LicensingTab />)

    await user.click(screen.getByRole('button', { name: /refresh status/i }))
    await user.click(screen.getByRole('button', { name: /deactivate/i }))

    await waitFor(() => {
      expect(trackPlanMock).toHaveBeenCalledWith(
        'Start',
        expect.objectContaining({ operation: 'refresh_license' })
      )
      expect(trackPlanMock).toHaveBeenCalledWith(
        'Complete',
        expect.objectContaining({ operation: 'refresh_license' })
      )
      expect(trackPlanMock).toHaveBeenCalledWith(
        'Start',
        expect.objectContaining({ operation: 'deactivate_license' })
      )
      expect(trackPlanMock).toHaveBeenCalledWith(
        'Complete',
        expect.objectContaining({ operation: 'deactivate_license' })
      )
    })
  })

  it('shows a buy link and tracks clicks', async () => {
    const user = userEvent.setup()

    renderWithProviders(<LicensingTab />)

    const buyLink = screen.getByRole('link', { name: /upgrade to pro/i })
    expect(buyLink).toHaveAttribute('href', BUY_URL)
    buyLink.addEventListener('click', (event) => event.preventDefault())

    await user.click(buyLink)

    expect(trackPlanMock).toHaveBeenCalledWith(
      'View',
      expect.objectContaining({ operation: 'open_buy_link' })
    )
  })
})

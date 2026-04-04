import { beforeEach, describe, expect, it, vi } from 'vitest'
import { QueryClient } from '@tanstack/react-query'
import { renderWithProviders, screen, userEvent, waitFor } from '../../test/test-utils'
import PlanInfoDrawer from '../PlanInfoDrawer'

const { track, toastSuccess, toastError } = vi.hoisted(() => ({
  track: vi.fn(),
  toastSuccess: vi.fn(),
  toastError: vi.fn(),
}))

let currentUserRole = 'admin'

vi.mock('../../hooks/useAuth', () => ({
  useAuth: () => ({
    user: currentUserRole ? { role: currentUserRole } : null,
  }),
}))

vi.mock('../../hooks/useAnalytics', () => ({
  useAnalytics: () => ({
    track,
    EventCategory: { PLAN: 'plan' },
  }),
}))

vi.mock('react-hot-toast', async () => {
  const actual = await vi.importActual<typeof import('react-hot-toast')>('react-hot-toast')
  return {
    ...actual,
    toast: {
      success: toastSuccess,
      error: toastError,
    },
  }
})

vi.mock('../../services/api', () => ({
  licensingAPI: {
    refresh: vi.fn(() => Promise.resolve({ data: {} })),
    activate: vi.fn(() => Promise.resolve({ data: {} })),
    deactivate: vi.fn(() => Promise.resolve({ data: {} })),
  },
}))

const defaultEntitlement = {
  status: 'none' as const,
  access_level: 'community' as const,
  is_full_access: false,
  full_access_consumed: false,
  expires_at: null,
  starts_at: null,
  instance_id: 'instance-123',
  license_id: null,
  last_refresh_error: null,
  ui_state: 'community' as const,
}

const featureMap = {
  borg_v2: 'pro',
  multi_user: 'pro',
  extra_users: 'enterprise',
} as const

describe('PlanInfoDrawer', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    currentUserRole = 'admin'
  })

  it('shows upcoming features and tracks plan selection', async () => {
    const user = userEvent.setup()

    renderWithProviders(
      <PlanInfoDrawer
        open={true}
        onClose={vi.fn()}
        plan="community"
        features={featureMap}
        entitlement={defaultEntitlement}
      />
    )

    expect(screen.getByText('Upcoming for Pro')).toBeInTheDocument()

    await user.click(screen.getByText('Enterprise'))

    expect(track).toHaveBeenCalledWith('plan', 'ViewPlan', { plan: 'enterprise' })
    expect(screen.getByText('Upcoming for Enterprise')).toBeInTheDocument()
  })

  it('hides licence management controls for non-admin users', () => {
    currentUserRole = 'viewer'

    renderWithProviders(
      <PlanInfoDrawer
        open={true}
        onClose={vi.fn()}
        plan="community"
        features={featureMap}
        entitlement={defaultEntitlement}
      />
    )

    expect(screen.queryByText('Licence management')).not.toBeInTheDocument()
    expect(screen.queryByLabelText(/licence key/i)).not.toBeInTheDocument()
  })

  it('requires a licence key before activation', async () => {
    const user = userEvent.setup()
    const { licensingAPI } = await import('../../services/api')

    renderWithProviders(
      <PlanInfoDrawer
        open={true}
        onClose={vi.fn()}
        plan="community"
        features={featureMap}
        entitlement={defaultEntitlement}
      />
    )

    await user.click(screen.getByRole('button', { name: /activate licence/i }))

    expect(licensingAPI.activate).not.toHaveBeenCalled()
    expect(toastError).toHaveBeenCalledWith('Enter a licence key first.')
  })

  it('activates a licence, invalidates system info, and clears the field', async () => {
    const user = userEvent.setup()
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries')
    const { licensingAPI } = await import('../../services/api')

    renderWithProviders(
      <PlanInfoDrawer
        open={true}
        onClose={vi.fn()}
        plan="community"
        features={featureMap}
        entitlement={defaultEntitlement}
      />,
      { queryClient }
    )

    await user.type(screen.getByLabelText(/licence key/i), '  LIC-123  ')
    await user.click(screen.getByRole('button', { name: /activate licence/i }))

    await waitFor(() => {
      expect(licensingAPI.activate).toHaveBeenCalledWith('LIC-123')
    })
    await waitFor(() => {
      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['system-info'] })
    })
    expect(toastSuccess).toHaveBeenCalledWith('Licence activated successfully.')
    expect(screen.getByLabelText(/licence key/i)).toHaveValue('')
  })

  it('refreshes and deactivates paid licences with the entered key', async () => {
    const user = userEvent.setup()
    const { licensingAPI } = await import('../../services/api')

    renderWithProviders(
      <PlanInfoDrawer
        open={true}
        onClose={vi.fn()}
        plan="pro"
        features={featureMap}
        entitlement={{
          ...defaultEntitlement,
          status: 'active',
          access_level: 'pro',
          license_id: 'lic-001',
          ui_state: 'paid_active',
        }}
      />
    )

    await user.click(screen.getByRole('button', { name: /refresh status/i }))
    await waitFor(() => {
      expect(licensingAPI.refresh).toHaveBeenCalledTimes(1)
    })

    await user.type(screen.getByLabelText(/licence key/i), 'LIC-001')
    await user.click(screen.getByRole('button', { name: /deactivate/i }))

    await waitFor(() => {
      expect(licensingAPI.deactivate).toHaveBeenCalledWith('LIC-001')
    })
  })
})

import { beforeEach, describe, it, expect, vi } from 'vitest'
import { screen, fireEvent } from '@testing-library/react'
import { renderWithProviders } from '../../test/test-utils'
import SidebarVersionInfo from '../SidebarVersionInfo'

const { usePlanMock } = vi.hoisted(() => ({
  usePlanMock: vi.fn(() => ({
    plan: 'community',
    features: {
      borg_v2: 'pro',
      multi_user: 'pro',
      extra_users: 'enterprise',
      rbac: 'enterprise',
    },
    entitlement: {
      status: 'none',
      access_level: 'community',
      is_full_access: false,
      full_access_consumed: false,
      expires_at: null,
      starts_at: null,
      instance_id: null,
      ui_state: 'community',
      last_refresh_at: null,
      last_refresh_error: null,
    },
    isLoading: false,
    can: () => true,
  })),
}))

vi.mock('../../hooks/usePlan', () => ({
  usePlan: () => usePlanMock(),
}))

const fullSystemInfo = {
  app_version: '1.2.3',
  borg_version: 'borg 1.4.0',
  borg2_version: 'borg2 2.0.0b12',
}

describe('SidebarVersionInfo', () => {
  beforeEach(() => {
    usePlanMock.mockReturnValue({
      plan: 'community',
      features: {
        borg_v2: 'pro',
        multi_user: 'pro',
        extra_users: 'enterprise',
        rbac: 'enterprise',
      },
      entitlement: {
        status: 'none',
        access_level: 'community',
        is_full_access: false,
        full_access_consumed: false,
        expires_at: null,
        starts_at: null,
        instance_id: null,
        ui_state: 'community',
        last_refresh_at: null,
        last_refresh_error: null,
      },
      isLoading: false,
      can: () => true,
    })
  })

  it('shows loading text when systemInfo is null', () => {
    renderWithProviders(<SidebarVersionInfo systemInfo={null} />)
    expect(screen.getByText(/loading/i)).toBeInTheDocument()
  })

  it('renders UI chip with app version', () => {
    renderWithProviders(<SidebarVersionInfo systemInfo={fullSystemInfo} />)
    expect(screen.getByText('UI')).toBeInTheDocument()
    expect(screen.getByText('1.2.3')).toBeInTheDocument()
  })

  it('renders B1 chip with stripped borg prefix', () => {
    renderWithProviders(<SidebarVersionInfo systemInfo={fullSystemInfo} />)
    expect(screen.getByText('B1')).toBeInTheDocument()
    expect(screen.getByText('1.4.0')).toBeInTheDocument()
  })

  it('renders B2 chip with stripped borg2 prefix', () => {
    renderWithProviders(<SidebarVersionInfo systemInfo={fullSystemInfo} />)
    expect(screen.getByText('B2')).toBeInTheDocument()
    expect(screen.getByText('2.0.0b12')).toBeInTheDocument()
  })

  it('does not render B1 chip when borg_version is null', () => {
    renderWithProviders(
      <SidebarVersionInfo systemInfo={{ ...fullSystemInfo, borg_version: null }} />
    )
    expect(screen.queryByText('B1')).not.toBeInTheDocument()
  })

  it('does not render B2 chip when borg2_version is null', () => {
    renderWithProviders(
      <SidebarVersionInfo systemInfo={{ ...fullSystemInfo, borg2_version: null }} />
    )
    expect(screen.queryByText('B2')).not.toBeInTheDocument()
  })

  it('opens the plan drawer and shows upcoming features', () => {
    renderWithProviders(<SidebarVersionInfo systemInfo={fullSystemInfo} />)

    fireEvent.click(screen.getByText('Community'))

    expect(screen.getByText('Upcoming for Pro')).toBeInTheDocument()
    expect(screen.getByText('Scheduled backup reports')).toBeInTheDocument()
  })

  it('defaults the drawer to enterprise when the active entitlement is enterprise', () => {
    usePlanMock.mockReturnValue({
      plan: 'community',
      features: {
        borg_v2: 'pro',
        multi_user: 'pro',
        extra_users: 'enterprise',
        rbac: 'enterprise',
      },
      entitlement: {
        status: 'active',
        access_level: 'enterprise',
        is_full_access: false,
        full_access_consumed: false,
        expires_at: null,
        starts_at: null,
        instance_id: null,
        ui_state: 'paid_active',
        last_refresh_at: null,
        last_refresh_error: null,
      },
      isLoading: false,
      can: () => true,
    })

    renderWithProviders(<SidebarVersionInfo systemInfo={fullSystemInfo} />)

    fireEvent.click(screen.getByText('Community'))

    expect(screen.getByText('Unlimited user seats')).toBeInTheDocument()
    expect(screen.queryByText('Borg v2 backups')).not.toBeInTheDocument()
  })
})

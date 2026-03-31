import { describe, it, expect, vi } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import { renderWithProviders } from '../../test/test-utils'
import AppSidebar from '../AppSidebar'

const { mockApiGet, mockGetSystemSettings } = vi.hoisted(() => ({
  mockApiGet: vi.fn().mockResolvedValue({ data: {} }),
  mockGetSystemSettings: vi.fn().mockResolvedValue({ data: { settings: {} } }),
}))

vi.mock('../../services/api', () => ({
  default: { get: mockApiGet },
  settingsAPI: {
    getSystemSettings: mockGetSystemSettings,
  },
}))

vi.mock('../../context/AppContext', () => ({
  useTabEnablement: () => ({
    tabEnablement: {
      dashboard: true,
      connections: true,
      repositories: true,
      backups: true,
      archives: true,
      schedule: true,
    },
    getTabDisabledReason: () => null,
  }),
}))

describe('AppSidebar', () => {
  it('renders the app name', async () => {
    renderWithProviders(<AppSidebar mobileOpen={false} onClose={vi.fn()} />)
    await waitFor(() => expect(screen.getAllByText('Borg UI').length).toBeGreaterThan(0))
  })

  it('renders a link to the dashboard', async () => {
    renderWithProviders(<AppSidebar mobileOpen={false} onClose={vi.fn()} />)
    await waitFor(() =>
      expect(screen.getAllByRole('link', { name: /borg ui/i })[0]).toHaveAttribute(
        'href',
        '/dashboard'
      )
    )
  })

  it('renders primary nav items', async () => {
    renderWithProviders(<AppSidebar mobileOpen={false} onClose={vi.fn()} />)
    await waitFor(() => {
      expect(screen.getAllByRole('link', { name: /dashboard/i }).length).toBeGreaterThan(0)
      expect(screen.getAllByRole('link', { name: /repositories/i }).length).toBeGreaterThan(0)
    })
  })

  it('shows version info loading state when system info not yet loaded', async () => {
    renderWithProviders(<AppSidebar mobileOpen={false} onClose={vi.fn()} />)
    await waitFor(() => expect(screen.getAllByText('Loading...').length).toBeGreaterThan(0))
  })
})

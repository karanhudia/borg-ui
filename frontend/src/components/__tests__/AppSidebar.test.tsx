import { describe, it, expect, vi } from 'vitest'
import { screen } from '@testing-library/react'
import { renderWithProviders } from '../../test/test-utils'
import AppSidebar from '../AppSidebar'

vi.mock('../../services/api', () => ({
  default: { get: vi.fn().mockResolvedValue({ data: {} }) },
  settingsAPI: {
    getSystemSettings: vi.fn().mockResolvedValue({ data: { settings: {} } }),
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
  it('renders the app name', () => {
    renderWithProviders(<AppSidebar mobileOpen={false} onClose={vi.fn()} />)
    expect(screen.getAllByText('Borg UI').length).toBeGreaterThan(0)
  })

  it('renders a link to the dashboard', () => {
    renderWithProviders(<AppSidebar mobileOpen={false} onClose={vi.fn()} />)
    expect(screen.getAllByRole('link', { name: /borg ui/i })[0]).toHaveAttribute('href', '/dashboard')
  })

  it('renders primary nav items', () => {
    renderWithProviders(<AppSidebar mobileOpen={false} onClose={vi.fn()} />)
    expect(screen.getAllByRole('link', { name: /dashboard/i }).length).toBeGreaterThan(0)
    expect(screen.getAllByRole('link', { name: /repositories/i }).length).toBeGreaterThan(0)
  })

  it('shows version info loading state when system info not yet loaded', () => {
    renderWithProviders(<AppSidebar mobileOpen={false} onClose={vi.fn()} />)
    expect(screen.getAllByText('Loading...').length).toBeGreaterThan(0)
  })
})

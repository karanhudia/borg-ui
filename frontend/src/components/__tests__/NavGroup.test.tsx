import { describe, it, expect, vi } from 'vitest'
import { screen, fireEvent } from '@testing-library/react'
import { renderWithProviders } from '../../test/test-utils'
import { User, Bell } from 'lucide-react'
import NavGroup from '../NavGroup'

const defaultProps = {
  name: 'Personal',
  icon: User,
  subItems: [
    { name: 'Account', href: '/settings/account', icon: User },
    { name: 'Notifications', href: '/settings/notifications', icon: Bell },
  ],
  isExpanded: false,
  onToggle: vi.fn(),
  currentPath: '/dashboard',
  navLabel: (n: string) => n,
}

describe('NavGroup', () => {
  it('renders the group name', () => {
    renderWithProviders(<NavGroup {...defaultProps} />)
    expect(screen.getByText('Personal')).toBeInTheDocument()
  })

  it('hides sub-items when collapsed', () => {
    renderWithProviders(<NavGroup {...defaultProps} isExpanded={false} />)
    expect(screen.queryByText('Account')).not.toBeInTheDocument()
  })

  it('shows sub-items when expanded', () => {
    renderWithProviders(<NavGroup {...defaultProps} isExpanded={true} />)
    expect(screen.getByText('Account')).toBeInTheDocument()
    expect(screen.getByText('Notifications')).toBeInTheDocument()
  })

  it('calls onToggle when header is clicked', () => {
    const onToggle = vi.fn()
    renderWithProviders(<NavGroup {...defaultProps} onToggle={onToggle} />)
    fireEvent.click(screen.getByText('Personal'))
    expect(onToggle).toHaveBeenCalledOnce()
  })

  it('highlights the active sub-item based on currentPath', () => {
    renderWithProviders(
      <NavGroup {...defaultProps} isExpanded={true} currentPath="/settings/account" />
    )
    const accountLink = screen.getByRole('link', { name: /account/i })
    expect(accountLink).toHaveAttribute('aria-current', 'page')
  })

  it('uses navLabel to translate sub-item names', () => {
    const navLabel = (n: string) => (n === 'Account' ? 'Cuenta' : n)
    renderWithProviders(<NavGroup {...defaultProps} isExpanded={true} navLabel={navLabel} />)
    expect(screen.getByText('Cuenta')).toBeInTheDocument()
    expect(screen.getByText('Notifications')).toBeInTheDocument()
  })
})

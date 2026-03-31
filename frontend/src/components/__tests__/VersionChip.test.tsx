import { describe, it, expect } from 'vitest'
import { screen } from '@testing-library/react'
import { renderWithProviders } from '../../test/test-utils'
import VersionChip from '../VersionChip'

describe('VersionChip', () => {
  it('renders the label and version', () => {
    renderWithProviders(<VersionChip label="UI" version="1.2.3" />)
    expect(screen.getByText('UI')).toBeInTheDocument()
    expect(screen.getByText('1.2.3')).toBeInTheDocument()
  })

  it('renders without accent by default', () => {
    renderWithProviders(<VersionChip label="B1" version="1.4.0" />)
    const label = screen.getByText('B1')
    // default label color is text.disabled, not indigo
    expect(label).not.toHaveStyle({ color: 'rgb(99,102,241)' })
  })

  it('renders accent label color when accent=true', () => {
    renderWithProviders(<VersionChip label="B2" version="2.0.0" accent />)
    const label = screen.getByText('B2')
    expect(label).toHaveStyle({ color: 'rgb(99,102,241)' })
  })

  it('renders version in monospace', () => {
    renderWithProviders(<VersionChip label="UI" version="0.9.1" />)
    const version = screen.getByText('0.9.1')
    expect(version).toHaveStyle({ fontFamily: 'monospace' })
  })
})

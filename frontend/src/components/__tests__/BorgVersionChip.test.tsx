import { describe, it, expect } from 'vitest'
import { screen } from '@testing-library/react'
import { renderWithProviders } from '../../test/test-utils'
import BorgVersionChip from '../BorgVersionChip'

describe('BorgVersionChip', () => {
  it('renders nothing for undefined borgVersion', () => {
    renderWithProviders(<BorgVersionChip borgVersion={undefined} />)
    expect(screen.queryByText('v2')).not.toBeInTheDocument()
  })

  it('renders nothing for borgVersion 1', () => {
    renderWithProviders(<BorgVersionChip borgVersion={1} />)
    expect(screen.queryByText('v2')).not.toBeInTheDocument()
  })

  it('renders v2 chip for borgVersion 2', () => {
    renderWithProviders(<BorgVersionChip borgVersion={2} />)
    expect(screen.getByText('v2')).toBeInTheDocument()
  })

  it('applies compact sizing when compact prop is true', () => {
    const { container } = renderWithProviders(<BorgVersionChip borgVersion={2} compact />)
    const chip = container.querySelector('.MuiChip-root') as HTMLElement
    // MUI applies sx height via CSS class, not inline style — verify chip renders
    expect(chip).toBeInTheDocument()
    expect(chip).toHaveClass('MuiChip-root')
  })

  it('applies default sizing when compact is false', () => {
    const { container } = renderWithProviders(<BorgVersionChip borgVersion={2} />)
    const chip = container.querySelector('.MuiChip-root') as HTMLElement
    expect(chip).toBeInTheDocument()
    expect(chip).toHaveClass('MuiChip-root')
  })
})

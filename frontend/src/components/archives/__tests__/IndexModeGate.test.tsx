import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import IndexModeGate from '../IndexModeGate'
import type { IndexMode } from '../../../types/operations'

function renderGate(mode: IndexMode) {
  render(
    <MemoryRouter>
      <IndexModeGate mode={mode}>
        <div>changes</div>
      </IndexModeGate>
    </MemoryRouter>
  )
}

describe('IndexModeGate (spec 6.8)', () => {
  it('renders its children when the repository indexes history', () => {
    renderGate('full')
    expect(screen.getByText('changes')).toBeInTheDocument()
  })

  it('explains the mode instead of the content', () => {
    renderGate('archives')
    expect(screen.queryByText('changes')).not.toBeInTheDocument()
    expect(screen.getByText(/archives only/i)).toBeInTheDocument()
  })

  it('says the stored rows are kept, not deleted', () => {
    renderGate('off')
    expect(screen.getByText(/kept/i)).toBeInTheDocument()
  })

  it('links to the repository settings', () => {
    renderGate('off')
    expect(screen.getByRole('link')).toHaveAttribute(
      'href',
      expect.stringContaining('/repositories')
    )
  })
})

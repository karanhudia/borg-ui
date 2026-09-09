import { describe, expect, it } from 'vitest'
import { screen } from '@testing-library/react'
import { renderWithProviders } from '../../../test/test-utils'
import AgentUpgradeStateChip from '../AgentUpgradeStateChip'

describe('AgentUpgradeStateChip', () => {
  it('names the target while an upgrade is in flight', () => {
    renderWithProviders(<AgentUpgradeStateChip state="requested" targetVersion="0.1.3" />)
    expect(screen.getByText(/0\.1\.3/)).toBeInTheDocument()
  })

  it('renders a failure state', () => {
    renderWithProviders(<AgentUpgradeStateChip state="failed" error="did not come back" />)
    expect(screen.getByText(/failed/i)).toBeInTheDocument()
  })

  it('renders nothing when the endpoint is idle', () => {
    renderWithProviders(<AgentUpgradeStateChip state="idle" />)
    expect(screen.queryByText(/upgrad/i)).not.toBeInTheDocument()
  })
})

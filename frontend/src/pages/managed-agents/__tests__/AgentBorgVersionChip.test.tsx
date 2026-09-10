import { describe, expect, it } from 'vitest'
import { screen } from '@testing-library/react'
import { renderWithProviders } from '../../../test/test-utils'
import AgentBorgVersionChip from '../AgentBorgVersionChip'

describe('AgentBorgVersionChip', () => {
  it('renders nothing when the endpoint has no Borg pin', () => {
    // The provider wrapper mounts a toaster of its own, so the absence of a
    // chip is the assertion, not an empty container.
    renderWithProviders(
      <AgentBorgVersionChip
        desiredBorgVersion={null}
        borgVersions={[{ major: 1, version: '1.4.0' }]}
      />
    )
    expect(screen.queryByText(/borg/i)).not.toBeInTheDocument()
  })

  it('says the pin is pending when the endpoint does not report that major', () => {
    renderWithProviders(
      <AgentBorgVersionChip
        desiredBorgVersion="2"
        borgVersions={[{ major: 1, version: '1.4.0' }]}
      />
    )
    expect(screen.getByText(/borg 2 pending/i)).toBeInTheDocument()
  })

  it('names the pin once the endpoint reports that major', () => {
    renderWithProviders(
      <AgentBorgVersionChip
        desiredBorgVersion="2"
        borgVersions={[
          { major: 1, version: '1.4.0' },
          { major: 2, version: '2.0.0b14' },
        ]}
      />
    )
    expect(screen.getByText('Borg 2')).toBeInTheDocument()
  })

  it('treats no reported binaries as pending rather than satisfied', () => {
    renderWithProviders(<AgentBorgVersionChip desiredBorgVersion="2" borgVersions={null} />)
    expect(screen.getByText(/borg 2 pending/i)).toBeInTheDocument()
  })

  it('matches a major reported as a string', () => {
    renderWithProviders(
      <AgentBorgVersionChip desiredBorgVersion="2" borgVersions={[{ major: '2' }]} />
    )
    expect(screen.getByText('Borg 2')).toBeInTheDocument()
  })

  it('survives a malformed entry in the reported list', () => {
    renderWithProviders(
      <AgentBorgVersionChip
        desiredBorgVersion="2"
        borgVersions={[null as unknown as Record<string, unknown>, { major: 2 }]}
      />
    )
    expect(screen.getByText('Borg 2')).toBeInTheDocument()
  })
})

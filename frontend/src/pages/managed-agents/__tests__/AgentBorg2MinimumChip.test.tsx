import { describe, expect, it } from 'vitest'
import { screen } from '@testing-library/react'
import { renderWithProviders, userEvent } from '../../../test/test-utils'
import AgentBorg2MinimumChip from '../AgentBorg2MinimumChip'
import { borg2MinimumParams, borg2ReinstallFlags } from '../agentBorg2Minimum'

describe('AgentBorg2MinimumChip', () => {
  it('renders nothing for an endpoint at or above the minimum', () => {
    renderWithProviders(
      <AgentBorg2MinimumChip
        belowMinimum={false}
        minimumVersion="2.0.0b25"
        borgVersions={[{ major: 2, version: '2.0.0b25' }]}
      />
    )
    expect(screen.queryByText(/borg 2 too old/i)).not.toBeInTheDocument()
  })

  it('names both versions and the reinstall flags for an older Borg 2', async () => {
    renderWithProviders(
      <AgentBorg2MinimumChip
        belowMinimum
        minimumVersion="2.0.0b25"
        borgVersions={[
          { major: 1, version: '1.4.5' },
          { major: 2, version: '2.0.0b24' },
        ]}
      />
    )
    const user = userEvent.setup()
    await user.hover(screen.getByText('Borg 2 too old'))
    const tooltip = await screen.findByRole('tooltip')
    expect(tooltip).toHaveTextContent('2.0.0b24')
    expect(tooltip).toHaveTextContent('2.0.0b25')
    expect(tooltip).toHaveTextContent('--reinstall --borg-version both --borg-source server')
  })
})

describe('borg2ReinstallFlags', () => {
  it('keeps a Borg 1 the endpoint reports', () => {
    expect(borg2ReinstallFlags([{ major: 1 }, { major: 2 }])).toBe(
      '--reinstall --borg-version both --borg-source server'
    )
    expect(borg2ReinstallFlags([{ major: 2 }])).toBe(
      '--reinstall --borg-version 2 --borg-source server'
    )
    expect(borg2ReinstallFlags(null)).toBe('--reinstall --borg-version 2 --borg-source server')
  })

  it('reads the reported Borg 2 version for the texts', () => {
    expect(borg2MinimumParams([{ major: 2, version: '2.0.0b24' }], '2.0.0b25')).toEqual({
      version: '2.0.0b24',
      minimum: '2.0.0b25',
      flags: '--reinstall --borg-version 2 --borg-source server',
    })
  })
})

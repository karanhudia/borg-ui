import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import MockAdapter from 'axios-mock-adapter'
import { toast } from 'react-hot-toast'

import api from '../../../services/api'
import { renderWithProviders, screen, userEvent } from '../../../test/test-utils'
import QuickStartAgentConnect from '../QuickStartAgentConnect'

describe('Quick Start agent command copying', () => {
  let mock: MockAdapter
  const originalClipboard = Object.getOwnPropertyDescriptor(navigator, 'clipboard')
  const originalExecCommand = Object.getOwnPropertyDescriptor(document, 'execCommand')

  beforeEach(() => {
    toast.remove()
    mock = new MockAdapter(api)
    mock.onGet('/managed-machines/agents').reply(200, [])
    mock.onGet('/managed-machines/enrollment-tokens').reply(200, [])
    mock.onPost('/managed-machines/enrollment-tokens').reply(200, {
      id: 30,
      name: 'borg-ui-agent',
      token: 'test-enrollment-token',
      token_prefix: 'test',
      created_at: '2026-10-27T00:00:00Z',
      expires_at: null,
      used_at: null,
      used_by_agent_id: null,
      revoked_at: null,
    })
  })

  afterEach(() => {
    mock.restore()
    for (const [target, key, descriptor] of [
      [navigator, 'clipboard', originalClipboard],
      [document, 'execCommand', originalExecCommand],
    ] as const) {
      if (descriptor) Object.defineProperty(target, key, descriptor)
      else Reflect.deleteProperty(target, key)
    }
    vi.restoreAllMocks()
  })

  it.each([true, false])('reports the actual fallback copy result: %s', async (copyWorks) => {
    const user = userEvent.setup()
    // userEvent installs a clipboard stub; remove it to reproduce a LAN HTTP origin.
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: undefined })
    let copiedText = ''
    Object.defineProperty(document, 'execCommand', {
      configurable: true,
      value: (command: string) => {
        expect(command).toBe('copy')
        copiedText = (document.activeElement as HTMLTextAreaElement).value
        return copyWorks
      },
    })
    renderWithProviders(<QuickStartAgentConnect value="" onChange={() => {}} canAddMachine />)
    await user.click(await screen.findByRole('button', { name: 'Add a computer' }))
    await user.click(screen.getByRole('button', { name: 'Next' }))
    await user.click(screen.getByRole('button', { name: 'Generate install command' }))
    await user.click(await screen.findByRole('button', { name: 'Copy install command' }))

    expect(
      await screen.findByText(copyWorks ? 'Copied' : 'Failed to copy to clipboard')
    ).toBeInTheDocument()
    expect(copiedText).toContain('test-enrollment-token')
    if (!copyWorks) expect(screen.queryByText('Copied')).not.toBeInTheDocument()
  })
})

import { useEffect, useState } from 'react'
import type { Meta, StoryObj } from '@storybook/react-vite'
import { userEvent, within } from 'storybook/test'
import MockAdapter from 'axios-mock-adapter'
import { Toaster } from 'react-hot-toast'

import api from '../../services/api'
import QuickStartAgentConnect from './QuickStartAgentConnect'

function EnrollmentHarness() {
  const [ready, setReady] = useState(false)
  useEffect(() => {
    const mock = new MockAdapter(api)
    const originalClipboard = Object.getOwnPropertyDescriptor(navigator, 'clipboard')
    // Reproduce the missing browser API on an HTTP LAN install.
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: undefined })
    mock.onGet('/managed-machines/agents').reply(200, [])
    mock.onGet('/managed-machines/enrollment-tokens').reply(200, [])
    mock.onPost('/managed-machines/enrollment-tokens').reply(200, {
      id: 30,
      name: 'borg-ui-agent',
      token: 'storybook-example-token',
      token_prefix: 'storybook',
      created_at: '2026-10-27T00:00:00Z',
      expires_at: null,
      used_at: null,
      used_by_agent_id: null,
      revoked_at: null,
    })
    setReady(true)
    return () => {
      mock.restore()
      if (originalClipboard) Object.defineProperty(navigator, 'clipboard', originalClipboard)
      else Reflect.deleteProperty(navigator, 'clipboard')
    }
  }, [])
  if (!ready) return null
  return (
    <>
      <QuickStartAgentConnect value="" onChange={() => {}} canAddMachine />
      <Toaster />
    </>
  )
}

const meta = {
  title: 'Quick Start/Agent command copying',
  component: QuickStartAgentConnect,
  args: { value: '', onChange: () => {}, canAddMachine: true },
  parameters: { layout: 'fullscreen' },
  render: () => <EnrollmentHarness />,
} satisfies Meta<typeof QuickStartAgentConnect>

export default meta
type Story = StoryObj<typeof meta>

export const WithoutClipboardApi: Story = {
  play: async ({ canvasElement }) => {
    const page = within(canvasElement.ownerDocument.body)
    await userEvent.click(await page.findByRole('button', { name: 'Add a computer' }))
    await userEvent.click(await page.findByRole('button', { name: 'Next' }))
    await userEvent.click(await page.findByRole('button', { name: 'Generate install command' }))
    await page.findByRole('button', { name: 'Copy install command' })
  },
}

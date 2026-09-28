import { describe, expect, it, vi } from 'vitest'
import { QueryClient } from '@tanstack/react-query'

import { managedAgentsAPI } from '../../../services/api'
import { renderWithProviders, screen, userEvent, waitFor } from '../../../test/test-utils'
import QuickStartAgentConnect from '../QuickStartAgentConnect'
import { createInitialQuickStartAnswers } from '../quickStartState'
import QuickStartWhatStep from '../steps/QuickStartWhatStep'

vi.mock('../../../services/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../services/api')>()
  return {
    ...actual,
    managedAgentsAPI: { listAgents: vi.fn(), createEnrollmentToken: vi.fn() },
  }
})

// The real dialog is covered on the Managed Agents page; here only open/close matters.
vi.mock('../../../pages/managed-agents/AddAgentDialog', () => ({
  default: ({ open }: { open: boolean }) => (open ? <div>add agent dialog</div> : null),
}))

const laptop = { id: 1, name: 'laptop', hostname: 'laptop.local', status: 'online' }
const desktop = { id: 2, name: 'desktop', hostname: 'desktop.local', status: 'online' }

describe('QuickStartAgentConnect', () => {
  it('selects the agent that connects while the add dialog is open', async () => {
    vi.mocked(managedAgentsAPI.listAgents).mockResolvedValue({ data: [laptop] } as never)
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const onChange = vi.fn()
    const user = userEvent.setup()
    renderWithProviders(<QuickStartAgentConnect value="" onChange={onChange} canAddMachine />, {
      queryClient,
    })

    await user.click(await screen.findByRole('button', { name: 'Add a computer' }))
    expect(screen.getByText('add agent dialog')).toBeInTheDocument()

    vi.mocked(managedAgentsAPI.listAgents).mockResolvedValue({ data: [laptop, desktop] } as never)
    await queryClient.refetchQueries({ queryKey: ['managed-agents'] })

    await waitFor(() => expect(onChange).toHaveBeenCalledWith(2))
    expect(onChange).toHaveBeenCalledTimes(1)
  })
})

describe('QuickStartWhatStep', () => {
  it('locks the agent option without the plan feature', () => {
    renderWithProviders(
      <QuickStartWhatStep answers={createInitialQuickStartAnswers()} onChange={() => {}} />
    )
    expect(screen.getByRole('radio', { name: /Borg UI agent/ })).toBeDisabled()
    expect(screen.getByText('Requires a Pro or Enterprise plan.')).toBeInTheDocument()
  })
})

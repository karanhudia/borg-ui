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
    managedAgentsAPI: {
      listAgents: vi.fn(),
      createEnrollmentToken: vi.fn(),
      listEnrollmentTokens: vi.fn(),
    },
  }
})

// The real dialog is covered on the Managed Agents page; here only open/close matters.
vi.mock('../../../pages/managed-agents/AddAgentDialog', () => ({
  default: ({
    open,
    onCreateToken,
  }: {
    open: boolean
    onCreateToken: (payload: { name: string }) => Promise<unknown>
  }) =>
    open ? <button onClick={() => onCreateToken({ name: 'desktop' })}>create token</button> : null,
}))

const laptop = { id: 1, name: 'laptop', hostname: 'laptop.local', status: 'online' }
const desktop = { id: 2, name: 'desktop', hostname: 'desktop.local', status: 'online' }

describe('QuickStartAgentConnect', () => {
  it('selects the agent that enrolled with the token created in the dialog', async () => {
    const other = { id: 3, name: 'other', hostname: 'other.local', status: 'online' }
    vi.mocked(managedAgentsAPI.listAgents).mockResolvedValue({ data: [laptop] } as never)
    vi.mocked(managedAgentsAPI.createEnrollmentToken).mockResolvedValue({
      data: { id: 30, token: 'secret' },
    } as never)
    vi.mocked(managedAgentsAPI.listEnrollmentTokens).mockResolvedValue({
      data: [{ id: 30, used_by_agent_id: null }],
    } as never)
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const onChange = vi.fn()
    const user = userEvent.setup()
    renderWithProviders(<QuickStartAgentConnect value="" onChange={onChange} canAddMachine />, {
      queryClient,
    })

    await user.click(await screen.findByRole('button', { name: 'Add a computer' }))
    await user.click(screen.getByRole('button', { name: 'create token' }))

    // Another agent joining at the same time is not picked.
    vi.mocked(managedAgentsAPI.listAgents).mockResolvedValue({
      data: [laptop, other, desktop],
    } as never)
    vi.mocked(managedAgentsAPI.listEnrollmentTokens).mockResolvedValue({
      data: [{ id: 30, used_by_agent_id: 2 }],
    } as never)
    await queryClient.refetchQueries()

    await waitFor(() => expect(onChange).toHaveBeenCalledWith(2))
    expect(onChange).toHaveBeenCalledTimes(1)
  })

  it('says when the computers cannot be loaded', async () => {
    vi.mocked(managedAgentsAPI.listAgents).mockRejectedValue(new Error('offline'))
    renderWithProviders(<QuickStartAgentConnect value="" onChange={() => {}} canAddMachine />, {
      queryClient: new QueryClient({ defaultOptions: { queries: { retry: false } } }),
    })
    expect(
      await screen.findByText('Could not load the computers. Try again in a moment.')
    ).toBeInTheDocument()
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

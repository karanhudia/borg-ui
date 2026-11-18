import { beforeEach, describe, expect, it, vi } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithProviders } from '../../test/test-utils'
import McpTab from '../McpTab'
import { mcpAPI } from '../../services/api'
import { connection, connections, mcpConfig } from '../mcp/storyFixtures'

const plan = { can: (_feature: string) => true }
const auth = { user: { role: 'admin' } as { role: string } | null }

vi.mock('../../hooks/usePlan', () => ({
  usePlan: () => ({ plan: 'pro', isLoading: false, can: (f: string) => plan.can(f) }),
}))
vi.mock('../../hooks/useAuth', () => ({ useAuth: () => auth }))
vi.mock('../../hooks/useFeatureAnalytics', () => ({
  useFeatureAnalytics: () => ({ trackFeatureBlocked: vi.fn(), trackFeatureUsed: vi.fn() }),
}))
vi.mock('../../utils/clipboard', () => ({ copyText: vi.fn().mockResolvedValue(true) }))
vi.mock('../../services/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../services/api')>()
  return {
    ...actual,
    mcpAPI: {
      getConfig: vi.fn(),
      list: vi.fn(),
      create: vi.fn(),
      update: vi.fn(),
      revoke: vi.fn(),
      activity: vi.fn().mockResolvedValue({ data: [] }),
    },
  }
})

const ok = <T,>(data: T) => ({ data }) as never

beforeEach(() => {
  vi.mocked(mcpAPI.getConfig).mockReset()
  vi.mocked(mcpAPI.list).mockReset()
  plan.can = () => true
  auth.user = { role: 'admin' }
  vi.mocked(mcpAPI.getConfig).mockResolvedValue(ok(mcpConfig))
  vi.mocked(mcpAPI.list).mockResolvedValue(ok(connections))
})

describe('McpTab', () => {
  it('shows the upgrade prompt on community', async () => {
    plan.can = () => false
    renderWithProviders(<McpTab />)
    expect(
      (await screen.findAllByText('This feature requires the Pro plan.')).length
    ).toBeGreaterThan(0)
    expect(mcpAPI.list).not.toHaveBeenCalled()
  })

  it('offers a retry when the connections fail to load', async () => {
    vi.mocked(mcpAPI.list)
      .mockRejectedValueOnce(new Error('boom'))
      .mockResolvedValueOnce(ok(connections))
    renderWithProviders(<McpTab />)
    await userEvent.click(await screen.findByRole('button', { name: 'Try again' }))
    expect(await screen.findByText('Claude on my laptop')).toBeInTheDocument()
    expect(screen.queryByText('No MCP connections yet')).not.toBeInTheDocument()
  })

  it('offers a retry when the settings fail to load', async () => {
    vi.mocked(mcpAPI.getConfig)
      .mockRejectedValueOnce(new Error('boom'))
      .mockResolvedValueOnce(ok(mcpConfig))
    renderWithProviders(<McpTab />)
    await userEvent.click(await screen.findByRole('button', { name: 'Try again' }))
    expect(await screen.findByText('Claude on my laptop')).toBeInTheDocument()
  })

  it('turned off disables create but keeps revoke', async () => {
    vi.mocked(mcpAPI.getConfig).mockResolvedValue(ok({ ...mcpConfig, enabled: false }))
    renderWithProviders(<McpTab />)
    expect(await screen.findByText(/turned off by your administrator/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'New connection' })).toBeDisabled()
    expect(screen.getAllByRole('button', { name: 'Revoke' })[0]).toBeEnabled()
  })

  it("admin can switch to everyone's connections", async () => {
    renderWithProviders(<McpTab />)
    await userEvent.click(await screen.findByLabelText("Everyone's connections"))
    await waitFor(() => expect(mcpAPI.list).toHaveBeenLastCalledWith(true))
  })

  it('hides the everyone switch from other users', async () => {
    auth.user = { role: 'viewer' }
    renderWithProviders(<McpTab />)
    await screen.findByText('Claude on my laptop')
    expect(screen.queryByLabelText("Everyone's connections")).not.toBeInTheDocument()
  })

  it('create then shows the token once', async () => {
    vi.mocked(mcpAPI.create).mockResolvedValue(
      ok({ ...connection({ id: 9, name: 'laptop' }), token: 'borgui_EXAMPLE' })
    )
    renderWithProviders(<McpTab />)
    await userEvent.click(await screen.findByRole('button', { name: 'New connection' }))
    await userEvent.type(screen.getByLabelText(/Name/), 'laptop')
    await userEvent.click(screen.getByRole('button', { name: 'Create connection' }))
    expect((await screen.findAllByText(/borgui_EXAMPLE/)).length).toBeGreaterThan(0)
    await userEvent.click(screen.getByRole('button', { name: 'Copy token' }))
    await userEvent.click(screen.getByRole('button', { name: 'Done' }))
    await waitFor(() => expect(screen.queryByText(/borgui_EXAMPLE/)).not.toBeInTheDocument())
  })
})

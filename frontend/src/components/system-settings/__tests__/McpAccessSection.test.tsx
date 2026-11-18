import { beforeEach, describe, expect, it, vi } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithProviders } from '../../../test/test-utils'
import McpAccessSection from '../McpAccessSection'
import { mcpAPI } from '../../../services/api'
import { mcpConfig } from '../../mcp/storyFixtures'

const plan = { can: (_feature: string) => true }

vi.mock('../../../hooks/usePlan', () => ({
  usePlan: () => ({ plan: 'pro', isLoading: false, can: (f: string) => plan.can(f) }),
}))
vi.mock('../../../hooks/useFeatureAnalytics', () => ({
  useFeatureAnalytics: () => ({ trackFeatureBlocked: vi.fn(), trackFeatureUsed: vi.fn() }),
}))
vi.mock('../../../services/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../services/api')>()
  return { ...actual, mcpAPI: { getConfig: vi.fn(), updateConfig: vi.fn() } }
})

beforeEach(() => {
  plan.can = () => true
  vi.mocked(mcpAPI.getConfig).mockResolvedValue({ data: mcpConfig } as never)
  vi.mocked(mcpAPI.updateConfig).mockResolvedValue({ data: mcpConfig } as never)
})

describe('McpAccessSection', () => {
  it('saves the switch and cap', async () => {
    renderWithProviders(<McpAccessSection />)
    await userEvent.click(await screen.findByLabelText('Allow MCP connections'))
    await userEvent.click(screen.getByRole('combobox', { name: 'Highest access level' }))
    await userEvent.click(await screen.findByRole('option', { name: 'Operate' }))
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() =>
      expect(mcpAPI.updateConfig).toHaveBeenCalledWith({
        enabled: false,
        max_access_level: 'operate',
      })
    )
  })

  it('save waits for a change', async () => {
    renderWithProviders(<McpAccessSection />)
    expect(await screen.findByRole('button', { name: 'Save' })).toBeDisabled()
  })

  it('shows the upgrade prompt on community', async () => {
    plan.can = () => false
    renderWithProviders(<McpAccessSection />)
    expect(
      (await screen.findAllByText('This feature requires the Pro plan.')).length
    ).toBeGreaterThan(0)
    expect(mcpAPI.getConfig).not.toHaveBeenCalled()
  })
})

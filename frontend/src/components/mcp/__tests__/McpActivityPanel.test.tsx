import { describe, expect, it, vi } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithProviders } from '../../../test/test-utils'
import McpActivityPanel from '../McpActivityPanel'
import { activityRows } from '../storyFixtures'
import { mcpAPI } from '../../../services/api'

vi.mock('../../../services/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../services/api')>()
  return { ...actual, mcpAPI: { activity: vi.fn() } }
})

describe('McpActivityPanel', () => {
  it('loads older rows with before_id', async () => {
    const first = activityRows(50, 500)
    vi.mocked(mcpAPI.activity)
      .mockResolvedValueOnce({ data: first } as never)
      .mockResolvedValueOnce({ data: activityRows(3, 450) } as never)
    renderWithProviders(<McpActivityPanel connectionId={7} />)
    await userEvent.click(await screen.findByRole('button', { name: 'Load more' }))
    await waitFor(() => expect(mcpAPI.activity).toHaveBeenLastCalledWith(7, 451))
    await waitFor(() =>
      expect(screen.queryByRole('button', { name: 'Load more' })).not.toBeInTheDocument()
    )
  })

  it('has an empty state', async () => {
    vi.mocked(mcpAPI.activity).mockResolvedValueOnce({ data: [] } as never)
    renderWithProviders(<McpActivityPanel connectionId={7} />)
    expect(await screen.findByText('No calls yet')).toBeInTheDocument()
  })
})

import { describe, expect, it, vi } from 'vitest'
import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithProviders } from '../../../test/test-utils'
import McpConnectionsList from '../McpConnectionsList'
import { connections } from '../storyFixtures'

const handlers = { onEdit: vi.fn(), onRevoke: vi.fn(), onOpenActivity: vi.fn() }

describe('McpConnectionsList', () => {
  it('shows the effective level when the cap lowers it', () => {
    renderWithProviders(
      <McpConnectionsList connections={connections} showOwner={false} {...handlers} />
    )
    const row = screen.getByTestId('mcp-connection-2')
    expect(within(row).getByText('Full')).toBeInTheDocument()
    expect(within(row).getByText('applies as Read')).toBeInTheDocument()
  })

  it('shows not connected yet', () => {
    renderWithProviders(
      <McpConnectionsList connections={connections} showOwner={false} {...handlers} />
    )
    expect(
      within(screen.getByTestId('mcp-connection-3')).getByText(/Not connected yet/)
    ).toBeInTheDocument()
  })

  it('asks before revoking', async () => {
    const onRevoke = vi.fn()
    renderWithProviders(
      <McpConnectionsList
        connections={connections}
        showOwner={false}
        {...handlers}
        onRevoke={onRevoke}
      />
    )
    await userEvent.click(
      within(screen.getByTestId('mcp-connection-1')).getByRole('button', { name: 'Revoke' })
    )
    expect(onRevoke).not.toHaveBeenCalled()
    await userEvent.click(
      within(screen.getByRole('dialog')).getByRole('button', { name: 'Revoke' })
    )
    expect(onRevoke).toHaveBeenCalledWith(connections[0])
  })

  it('shows owners for admins', () => {
    renderWithProviders(<McpConnectionsList connections={connections} showOwner {...handlers} />)
    expect(screen.getByText(/sam/)).toBeInTheDocument()
  })

  it('has an empty state', () => {
    renderWithProviders(<McpConnectionsList connections={[]} showOwner={false} {...handlers} />)
    expect(screen.getByText('No MCP connections yet')).toBeInTheDocument()
  })
})

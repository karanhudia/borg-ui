import { describe, expect, it, vi } from 'vitest'
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithProviders } from '../../../test/test-utils'
import McpConnectedDialog from '../McpConnectedDialog'

vi.mock('../../../utils/clipboard', () => ({ copyText: vi.fn().mockResolvedValue(true) }))

const props = { token: 'borgui_EXAMPLE', endpointUrl: 'https://backups.example.com/mcp' }

describe('McpConnectedDialog', () => {
  it('shows every client tab', () => {
    renderWithProviders(<McpConnectedDialog open {...props} onClose={vi.fn()} />)
    for (const name of ['Claude Code', 'Claude Desktop', 'Cursor', 'VS Code', 'Other clients'])
      expect(screen.getByRole('tab', { name })).toBeInTheDocument()
    expect(screen.getAllByText(/borgui_EXAMPLE/).length).toBeGreaterThan(0)
  })

  it('asks before closing when nothing was copied', async () => {
    const onClose = vi.fn()
    renderWithProviders(<McpConnectedDialog open {...props} onClose={onClose} />)
    await userEvent.click(screen.getByRole('button', { name: 'Done' }))
    expect(onClose).not.toHaveBeenCalled()
    expect(screen.getByText('Close without copying the token?')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Close anyway' }))
    expect(onClose).toHaveBeenCalled()
  })

  it('closes straight away once the token was copied', async () => {
    const onClose = vi.fn()
    renderWithProviders(<McpConnectedDialog open {...props} onClose={onClose} />)
    await userEvent.click(screen.getByRole('button', { name: 'Copy token' }))
    await userEvent.click(screen.getByRole('button', { name: 'Done' }))
    expect(onClose).toHaveBeenCalled()
  })
})

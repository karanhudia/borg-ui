import { describe, expect, it, vi } from 'vitest'
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithProviders } from '../../../test/test-utils'
import McpConnectionDialog from '../McpConnectionDialog'
import { mcpConfig } from '../storyFixtures'

describe('McpConnectionDialog', () => {
  it('submit needs a name', async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined)
    renderWithProviders(
      <McpConnectionDialog
        open
        mode="create"
        config={mcpConfig}
        onClose={vi.fn()}
        onSubmit={onSubmit}
      />
    )
    const create = screen.getByRole('button', { name: 'Create connection' })
    expect(create).toBeDisabled()
    await userEvent.type(screen.getByLabelText(/Name/), 'laptop')
    await userEvent.click(create)
    expect(onSubmit).toHaveBeenCalledWith({
      name: 'laptop',
      access_level: 'read',
      skip_routine_confirmations: false,
    })
  })

  it('shows the skip switch only at full', async () => {
    const config = {
      ...mcpConfig,
      available_levels: ['read', 'operate', 'manage', 'full'] as const,
    }
    renderWithProviders(
      <McpConnectionDialog
        open
        mode="create"
        config={{ ...config, available_levels: [...config.available_levels] }}
        onClose={vi.fn()}
        onSubmit={vi.fn()}
      />
    )
    expect(screen.queryByLabelText('Skip routine confirmations')).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('radio', { name: /^Full/ }))
    expect(screen.getByLabelText('Skip routine confirmations')).toBeInTheDocument()
  })
})

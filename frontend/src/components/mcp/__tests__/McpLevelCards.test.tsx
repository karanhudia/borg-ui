import { describe, expect, it, vi } from 'vitest'
import { screen } from '@testing-library/react'
import { renderWithProviders } from '../../../test/test-utils'
import McpLevelCards from '../McpLevelCards'

const radio = (name: RegExp) => screen.getByRole('radio', { name })

describe('McpLevelCards', () => {
  it('disables levels without tools', () => {
    renderWithProviders(
      <McpLevelCards value="read" onChange={vi.fn()} available={['read']} cap="full" />
    )
    expect(radio(/^Read/)).toBeEnabled()
    for (const name of [/^Operate/, /^Manage/, /^Full/]) expect(radio(name)).toBeDisabled()
    expect(screen.getAllByText('Coming soon')).toHaveLength(3)
  })

  it('disables levels above the cap', () => {
    renderWithProviders(
      <McpLevelCards
        value="read"
        onChange={vi.fn()}
        available={['read', 'operate', 'manage', 'full']}
        cap="operate"
      />
    )
    expect(radio(/^Operate/)).toBeEnabled()
    expect(radio(/^Manage/)).toBeDisabled()
    expect(radio(/^Full/)).toBeDisabled()
    expect(screen.getAllByText("Above your administrator's limit")).toHaveLength(2)
  })
})

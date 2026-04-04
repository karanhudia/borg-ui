import type { AxiosResponse } from 'axios'
import { describe, it, expect, vi } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithProviders } from '../../test/test-utils'
import ApiTokensSection from '../ApiTokensSection'

interface MockToken {
  id: number
  name: string
  prefix: string
  created_at: string
  last_used_at: string | null
}

function createTokensResponse(data: MockToken[]): AxiosResponse<MockToken[]> {
  return {
    data,
    status: 200,
    statusText: 'OK',
    headers: {},
    config: { headers: {} as AxiosResponse<MockToken[]>['config']['headers'] },
  }
}

vi.mock('../../services/api', () => ({
  tokensAPI: {
    list: vi.fn().mockResolvedValue({ data: [] }),
    generate: vi.fn(),
    revoke: vi.fn(),
  },
}))

vi.mock('../../hooks/usePlan', () => ({
  usePlan: () => ({ plan: 'pro', isLoading: false, can: () => true }),
}))

describe('ApiTokensSection', () => {
  it('renders empty state when no tokens', async () => {
    renderWithProviders(<ApiTokensSection />)
    await waitFor(() => {
      expect(screen.getByText('No tokens yet')).toBeInTheDocument()
    })
  })

  it('shows generate button', () => {
    renderWithProviders(<ApiTokensSection />)
    expect(screen.getByRole('button', { name: /generate/i })).toBeInTheDocument()
  })

  it('opens generate dialog on button click', async () => {
    const user = userEvent.setup()
    renderWithProviders(<ApiTokensSection />)
    await user.click(screen.getByRole('button', { name: /generate/i }))
    expect(screen.getByText('Generate API Token')).toBeInTheDocument()
  })

  it('shows token list when tokens exist', async () => {
    const { tokensAPI } = await import('../../services/api')
    vi.mocked(tokensAPI.list).mockResolvedValueOnce(
      createTokensResponse([
        {
          id: 1,
          name: 'CI token',
          prefix: 'borgui_ab',
          created_at: '2024-01-01T00:00:00Z',
          last_used_at: null,
        },
      ])
    )

    renderWithProviders(<ApiTokensSection />)
    await waitFor(() => {
      expect(screen.getByText('CI token')).toBeInTheDocument()
    })
  })
})

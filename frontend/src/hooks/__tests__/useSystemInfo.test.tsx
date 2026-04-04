import { describe, expect, it, vi } from 'vitest'
import React from 'react'
import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useSystemInfo } from '../useSystemInfo'

vi.mock('../../services/api', () => ({
  default: {
    get: vi.fn(),
  },
}))

function makeWrapper() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client }, children)
}

describe('useSystemInfo', () => {
  it('fetches system info from /system/info', async () => {
    const { default: api } = await import('../../services/api')
    vi.mocked(api.get).mockResolvedValue({
      data: {
        app_version: '1.0.0',
        borg_version: 'borg 1.4.0',
        borg2_version: null,
        plan: 'community',
        features: {},
      },
    } as never)

    const { result } = renderHook(() => useSystemInfo(), { wrapper: makeWrapper() })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(api.get).toHaveBeenCalledWith('/system/info')
    expect(result.current.data).toEqual(
      expect.objectContaining({
        app_version: '1.0.0',
        plan: 'community',
      })
    )
  })
})

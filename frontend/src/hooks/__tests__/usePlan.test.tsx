import React from 'react'
import { describe, expect, it, vi } from 'vitest'
import { renderHook } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { usePlan } from '../usePlan'

vi.mock('../useSystemInfo', () => ({
  useSystemInfo: vi.fn(),
}))

function makeWrapper() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client }, children)
}

describe('usePlan', () => {
  it('prefers backend feature_access overrides over plan-derived access', async () => {
    const { useSystemInfo } = await import('../useSystemInfo')
    vi.mocked(useSystemInfo).mockReturnValue({
      data: {
        app_version: '1.0.0',
        borg_version: null,
        borg2_version: null,
        plan: 'community',
        features: {
          borg_v2: 'pro',
        },
        feature_access: {
          borg_v2: true,
        },
      },
      isLoading: false,
    } as unknown as ReturnType<typeof useSystemInfo>)

    const { result } = renderHook(() => usePlan(), { wrapper: makeWrapper() })

    expect(result.current.can('borg_v2')).toBe(true)
  })
})

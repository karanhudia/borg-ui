import { beforeEach, describe, expect, it, vi } from 'vitest'
import React from 'react'
import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'

import { backupPlansAPI, repositoriesAPI } from '../../../services/api'
import { QUICK_START_DISMISSED_KEY, useQuickStartAutoOpen } from '../useQuickStartAutoOpen'

vi.mock('../../../services/api', () => ({
  repositoriesAPI: { getRepositories: vi.fn() },
  backupPlansAPI: { list: vi.fn() },
}))

function wrapperAt(path: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(
      QueryClientProvider,
      { client },
      React.createElement(MemoryRouter, { initialEntries: [path] }, children)
    )
}

function mockCounts(repositories: number, plans: number) {
  vi.mocked(repositoriesAPI.getRepositories).mockResolvedValue({
    data: { repositories: Array.from({ length: repositories }, (_, id) => ({ id })) },
  } as never)
  vi.mocked(backupPlansAPI.list).mockResolvedValue({
    data: { backup_plans: Array.from({ length: plans }, (_, id) => ({ id })) },
  } as never)
}

describe('useQuickStartAutoOpen', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.mocked(repositoriesAPI.getRepositories).mockReset()
    vi.mocked(backupPlansAPI.list).mockReset()
  })

  it('opens once on the dashboard of an empty install', async () => {
    mockCounts(0, 0)
    const onOpen = vi.fn()
    renderHook(() => useQuickStartAutoOpen({ enabled: true, onOpen }), {
      wrapper: wrapperAt('/dashboard'),
    })
    await waitFor(() => expect(onOpen).toHaveBeenCalledTimes(1))
    expect(localStorage.getItem(QUICK_START_DISMISSED_KEY)).toBe('1')
  })

  it('stays closed when a repository already exists', async () => {
    mockCounts(1, 0)
    const onOpen = vi.fn()
    renderHook(() => useQuickStartAutoOpen({ enabled: true, onOpen }), {
      wrapper: wrapperAt('/dashboard'),
    })
    await waitFor(() => expect(backupPlansAPI.list).toHaveBeenCalled())
    await waitFor(() => expect(repositoriesAPI.getRepositories).toHaveBeenCalled())
    expect(onOpen).not.toHaveBeenCalled()
  })

  it('stays closed once dismissed, off the dashboard, or when disabled', () => {
    mockCounts(0, 0)
    const onOpen = vi.fn()
    localStorage.setItem(QUICK_START_DISMISSED_KEY, '1')
    renderHook(() => useQuickStartAutoOpen({ enabled: true, onOpen }), {
      wrapper: wrapperAt('/dashboard'),
    })
    localStorage.clear()
    renderHook(() => useQuickStartAutoOpen({ enabled: true, onOpen }), {
      wrapper: wrapperAt('/repositories'),
    })
    renderHook(() => useQuickStartAutoOpen({ enabled: false, onOpen }), {
      wrapper: wrapperAt('/dashboard'),
    })
    expect(repositoriesAPI.getRepositories).not.toHaveBeenCalled()
    expect(onOpen).not.toHaveBeenCalled()
  })
})

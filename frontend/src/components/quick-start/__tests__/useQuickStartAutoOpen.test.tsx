import { beforeEach, describe, expect, it, vi } from 'vitest'
import React from 'react'
import { act, renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'

import { backupPlansAPI, repositoriesAPI } from '../../../services/api'
import { QUICK_START_DISMISSED_KEY, useQuickStartAutoOpen } from '../useQuickStartAutoOpen'

vi.mock('../../../services/api', () => ({
  repositoriesAPI: { getRepositories: vi.fn() },
  backupPlansAPI: { list: vi.fn() },
}))

function wrapperAt(
  path: string,
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
) {
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(
      QueryClientProvider,
      { client },
      React.createElement(MemoryRouter, { initialEntries: [path] }, children)
    )
}

// Flushes the effects React scheduled for the last render, so a negative
// assertion runs after the hook has had its chance to open.
async function settleEffects() {
  await act(async () => {})
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
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const onOpen = vi.fn()
    renderHook(() => useQuickStartAutoOpen({ enabled: true, onOpen }), {
      wrapper: wrapperAt('/dashboard', client),
    })
    // Wait for both answers to land, not just for the requests to start.
    await waitFor(() => expect(client.getQueryState(['repositories'])?.status).toBe('success'))
    await waitFor(() => expect(client.getQueryState(['backup-plans'])?.status).toBe('success'))
    await waitFor(() => expect(client.isFetching()).toBe(0))
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
  it('opens only once per session even when storage cannot be written', async () => {
    mockCounts(0, 0)
    const setItem = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('blocked')
    })
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const onOpen = vi.fn()
    const { rerender } = renderHook(({ enabled }) => useQuickStartAutoOpen({ enabled, onOpen }), {
      wrapper: wrapperAt('/dashboard', client),
      initialProps: { enabled: true },
    })
    await waitFor(() => expect(onOpen).toHaveBeenCalledTimes(1))
    // The provider disables the hook while the dialog is open, then enables it again.
    rerender({ enabled: false })
    rerender({ enabled: true })
    await waitFor(() => expect(client.isFetching()).toBe(0))
    await settleEffects()
    expect(onOpen).toHaveBeenCalledTimes(1)
    setItem.mockRestore()
  })
  it('waits for fresh counts instead of trusting a stale empty cache', async () => {
    // The app caches for 30s; an empty list cached a moment ago is still "fresh" to it.
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false, staleTime: 30_000 } },
    })
    client.setQueryData(['repositories'], { data: { repositories: [] } })
    client.setQueryData(['backup-plans'], { data: { backup_plans: [] } })
    mockCounts(1, 0)
    const onOpen = vi.fn()
    renderHook(() => useQuickStartAutoOpen({ enabled: true, onOpen }), {
      wrapper: wrapperAt('/dashboard', client),
    })
    await waitFor(() => expect(repositoriesAPI.getRepositories).toHaveBeenCalled())
    await waitFor(() => expect(client.isFetching()).toBe(0))
    expect(onOpen).not.toHaveBeenCalled()
    expect(localStorage.getItem(QUICK_START_DISMISSED_KEY)).toBeNull()
  })
  it('stays closed when the refetch fails, even with empty lists cached', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    client.setQueryData(['repositories'], { data: { repositories: [] } })
    client.setQueryData(['backup-plans'], { data: { backup_plans: [] } })
    vi.mocked(repositoriesAPI.getRepositories).mockRejectedValue(new Error('offline'))
    vi.mocked(backupPlansAPI.list).mockResolvedValue({ data: { backup_plans: [] } } as never)
    const onOpen = vi.fn()
    renderHook(() => useQuickStartAutoOpen({ enabled: true, onOpen }), {
      wrapper: wrapperAt('/dashboard', client),
    })
    await waitFor(() => expect(repositoriesAPI.getRepositories).toHaveBeenCalled())
    await waitFor(() => expect(client.isFetching()).toBe(0))
    expect(onOpen).not.toHaveBeenCalled()
  })
  it('does not open when another tab already did', async () => {
    mockCounts(0, 0)
    let resolveRepositories: (value: unknown) => void = () => {}
    vi.mocked(repositoriesAPI.getRepositories).mockReturnValue(
      new Promise((resolve) => {
        resolveRepositories = resolve
      }) as never
    )
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const onOpen = vi.fn()
    renderHook(() => useQuickStartAutoOpen({ enabled: true, onOpen }), {
      wrapper: wrapperAt('/dashboard', client),
    })
    await waitFor(() => expect(repositoriesAPI.getRepositories).toHaveBeenCalled())
    // The other tab writes the flag while this one is still loading.
    localStorage.setItem(QUICK_START_DISMISSED_KEY, '1')
    await act(async () => {
      resolveRepositories({ data: { repositories: [] } })
    })
    await waitFor(() => expect(client.getQueryState(['repositories'])?.status).toBe('success'))
    await waitFor(() => expect(client.isFetching()).toBe(0))
    await settleEffects()
    expect(onOpen).not.toHaveBeenCalled()
  })
})

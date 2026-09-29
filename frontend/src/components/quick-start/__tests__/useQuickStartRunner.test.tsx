import { beforeEach, describe, expect, it, vi } from 'vitest'
import React from 'react'
import { act, renderHook } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import { backupPlansAPI } from '../../../services/api'
import { BorgApiClient } from '../../../services/borgApi'
import { createInitialQuickStartAnswers, type QuickStartAnswers } from '../quickStartState'
import { useQuickStartRunner } from '../useQuickStartRunner'

vi.mock('../../../services/api', () => ({
  backupPlansAPI: { create: vi.fn() },
}))
vi.mock('../../../services/borgApi', () => ({
  BorgApiClient: { createRepository: vi.fn() },
}))

function wrapper({ children }: { children: React.ReactNode }) {
  const client = new QueryClient()
  return React.createElement(QueryClientProvider, { client }, children)
}

const answers: QuickStartAnswers = {
  ...createInitialQuickStartAnswers(),
  sourcePaths: ['/local/home'],
  destinationPath: '/local/borg-backups/home',
  name: 'home',
  passphrase: 'correct horse',
  passphraseConfirm: 'correct horse',
  passphraseSaved: true,
}

describe('useQuickStartRunner', () => {
  beforeEach(() => {
    vi.mocked(BorgApiClient.createRepository).mockReset()
    vi.mocked(backupPlansAPI.create).mockReset()
  })

  it('creates the repository, then the plan', async () => {
    vi.mocked(BorgApiClient.createRepository).mockResolvedValue({
      data: { repository: { id: 4 } },
    } as never)
    vi.mocked(backupPlansAPI.create).mockResolvedValue({ data: { id: 9 } } as never)

    const { result } = renderHook(() => useQuickStartRunner(), { wrapper })
    let ok = false
    await act(async () => {
      ok = await result.current.run(answers)
    })

    expect(ok).toBe(true)
    expect(result.current.results).toEqual({ repositoryId: 4, planId: 9 })
    expect(result.current.statuses).toEqual({ create_repository: 'done', create_plan: 'done' })
    expect(vi.mocked(backupPlansAPI.create).mock.calls[0][0].repositories[0].repository_id).toBe(4)
  })

  it('stops on a failure and resumes without recreating the repository', async () => {
    vi.mocked(BorgApiClient.createRepository).mockResolvedValue({ data: { id: 4 } } as never)
    vi.mocked(backupPlansAPI.create)
      .mockRejectedValueOnce({ response: { data: { detail: 'Plan name already exists' } } })
      .mockResolvedValueOnce({ data: { id: 9 } } as never)

    const { result } = renderHook(() => useQuickStartRunner(), { wrapper })
    await act(async () => {
      await result.current.run(answers)
    })

    expect(result.current.statuses.create_plan).toBe('failed')
    expect(result.current.error).toBe('Plan name already exists')
    expect(result.current.running).toBe(false)

    // Editing answers keeps what already exists.
    act(() => result.current.edit())
    expect(result.current.actions).toEqual([])
    expect(result.current.results).toEqual({ repositoryId: 4 })

    await act(async () => {
      await result.current.run(answers)
    })

    expect(BorgApiClient.createRepository).toHaveBeenCalledTimes(1)
    expect(backupPlansAPI.create).toHaveBeenCalledTimes(2)
    expect(result.current.error).toBeNull()
    expect(result.current.results).toEqual({ repositoryId: 4, planId: 9 })
  })
})

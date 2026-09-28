import { describe, expect, it, vi } from 'vitest'
import { QueryClient } from '@tanstack/react-query'
import { deleteJobFromLists, forgetPendingDeletes, pendingDeletes, withoutJob } from '../jobCache'

const backup7 = { id: 7, type: 'backup', status: 'completed' }
const backup8 = { id: 8, type: 'backup', status: 'completed' }
const script7 = { id: 7, type: 'script_execution', status: 'completed' }
const planRun7 = { id: 7, type: 'backup_plan_run', status: 'failed' }

describe('withoutJob', () => {
  it('filters a plain array by type and id together', () => {
    const rows = [backup7, script7, planRun7, backup8]
    expect(withoutJob(rows, { id: 7, type: 'backup' })).toEqual([script7, planRun7, backup8])
    expect(withoutJob(rows, { id: 7, type: 'backup_plan_run' })).toEqual([
      backup7,
      script7,
      backup8,
    ])
  })

  it('reads a missing type as a backup, as the delete call does', () => {
    const untyped = [{ id: 7 }, { id: 8 }]
    expect(withoutJob(untyped, { id: 7 })).toEqual([{ id: 8 }])
    expect(withoutJob(untyped, { id: 7, type: 'check' })).toEqual(untyped)
  })

  it('matches ids across string and number', () => {
    expect(withoutJob([backup7, backup8], { id: '7', type: 'backup' })).toEqual([backup8])
  })

  it('filters every page of an infinite query and keeps its page params', () => {
    const data = { pages: [[backup8], [backup7, script7]], pageParams: [null, 'cursor'] }
    expect(withoutJob(data, { id: 7, type: 'backup' })).toEqual({
      pages: [[backup8], [script7]],
      pageParams: [null, 'cursor'],
    })
  })

  it('filters { jobs } and an axios response around it', () => {
    expect(withoutJob({ jobs: [backup7, backup8], total: 2 }, backup7)).toEqual({
      jobs: [backup8],
      total: 2,
    })
    expect(withoutJob({ status: 200, data: { jobs: [backup7, backup8] } }, backup7)).toEqual({
      status: 200,
      data: { jobs: [backup8] },
    })
  })

  it('drops a follow-up step nested under a row', () => {
    const run = { ...backup8, followups: [{ id: 3, type: 'prune' }, script7] }
    expect(withoutJob({ pages: [[run]] }, { id: 3, type: 'prune' })).toEqual({
      pages: [[{ ...backup8, followups: [script7] }]],
    })
  })

  it('leaves data of any other shape alone', () => {
    const other = { cells: [backup7] }
    expect(withoutJob(other, backup7)).toBe(other)
    expect(withoutJob(undefined, backup7)).toBeUndefined()
  })
})

describe('deleteJobFromLists', () => {
  const held = () => {
    let resolve: () => void = () => {}
    let reject: (error: Error) => void = () => {}
    const promise = new Promise<void>((res, rej) => {
      resolve = res
      reject = rej
    })
    return { promise, resolve, reject }
  }

  // Two tables (two pages, or one page mounted twice) delete through the
  // same client; nothing is shared between the calls but the client.
  const setup = () => {
    const queryClient = new QueryClient()
    queryClient.setQueryData(['activity', null], { pages: [[backup7, backup8]], pageParams: [] })
    queryClient.setQueryData(['backup-jobs-all'], { data: { jobs: [backup7, backup8] } })
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries')
    return { queryClient, invalidate }
  }

  it('keeps the other row out when one of two deletes fails', async () => {
    const { queryClient, invalidate } = setup()
    const first = held()
    const second = held()
    const a = deleteJobFromLists(queryClient, backup7, () => first.promise)
    const b = deleteJobFromLists(queryClient, backup8, () => second.promise)
    await vi.waitFor(() => expect(pendingDeletes(queryClient).size).toBe(2))

    first.reject(new Error('job not found'))
    await expect(a).rejects.toThrow('job not found')
    expect(queryClient.getQueryData(['activity', null])).toEqual({
      pages: [[backup7]],
      pageParams: [],
    })
    expect(queryClient.getQueryData(['backup-jobs-all'])).toEqual({ data: { jobs: [backup7] } })
    // The other delete is still out: a refetch now would bring its row back.
    expect(invalidate).not.toHaveBeenCalled()

    second.resolve()
    await expect(b).resolves.toBe(true)
    expect(invalidate).toHaveBeenCalled()
    expect(pendingDeletes(queryClient).size).toBe(0)
  })

  it('sends no second request for a row whose delete is out', async () => {
    const { queryClient } = setup()
    const first = held()
    const request = vi.fn(() => first.promise)
    const a = deleteJobFromLists(queryClient, backup7, request)
    await expect(deleteJobFromLists(queryClient, { id: '7' }, request)).resolves.toBe(false)
    expect(request).toHaveBeenCalledTimes(1)
    first.resolve()
    await expect(a).resolves.toBe(true)
  })

  it('keeps each query client to itself', async () => {
    const one = setup().queryClient
    const other = setup().queryClient
    const first = held()
    const a = deleteJobFromLists(one, backup7, () => first.promise)
    expect(pendingDeletes(one).has('backup-7')).toBe(true)
    expect(pendingDeletes(other).size).toBe(0)
    first.resolve()
    await a
  })

  it('forgets deletes of a cache that was cleared for another backend', async () => {
    const { queryClient, invalidate } = setup()
    const first = held()
    const a = deleteJobFromLists(queryClient, backup7, () => first.promise)
    await vi.waitFor(() => expect(pendingDeletes(queryClient).has('backup-7')).toBe(true))

    // What switching the backend does: another server's lists, same client.
    forgetPendingDeletes(queryClient)
    queryClient.clear()
    const otherBackend = { pages: [[{ ...backup7, status: 'failed' }]], pageParams: [] }
    queryClient.setQueryData(['activity', null], otherBackend)
    expect(pendingDeletes(queryClient).size).toBe(0)

    first.reject(new Error('job not found'))
    await expect(a).rejects.toThrow('job not found')
    expect(queryClient.getQueryData(['activity', null])).toEqual(otherBackend)
    expect(queryClient.getQueryData(['backup-jobs-all'])).toBeUndefined()
    expect(pendingDeletes(queryClient).size).toBe(0)
    expect(invalidate).not.toHaveBeenCalled()
  })

  it('sends the request before anything else, to the backend it was made on', () => {
    const { queryClient } = setup()
    const request = vi.fn(() => new Promise<void>(() => {}))
    void deleteJobFromLists(queryClient, backup7, request)
    // Nothing awaited yet: a backend switched after the click must not
    // receive this request.
    expect(request).toHaveBeenCalledTimes(1)
  })

  it('puts a row back into a list first loaded during the series', async () => {
    const { queryClient } = setup()
    const first = held()
    const second = held()
    const a = deleteJobFromLists(queryClient, backup7, () => first.promise)
    await vi.waitFor(() =>
      expect(queryClient.getQueryData(['activity', null])).toEqual({
        pages: [[backup8]],
        pageParams: [],
      })
    )

    // A filter chosen while the first delete is out loads a list of its own.
    queryClient.setQueryData(['activity', 'failed'], { pages: [[backup8]], pageParams: [] })
    const b = deleteJobFromLists(queryClient, backup8, () => second.promise)
    await vi.waitFor(() =>
      expect(queryClient.getQueryData(['activity', 'failed'])).toEqual({
        pages: [[]],
        pageParams: [],
      })
    )

    second.reject(new Error('job not found'))
    await expect(b).rejects.toThrow('job not found')
    expect(queryClient.getQueryData(['activity', 'failed'])).toEqual({
      pages: [[backup8]],
      pageParams: [],
    })
    first.resolve()
    await a
  })

  it('drops a deleted row again before it can be deleted twice', async () => {
    const { queryClient } = setup()
    const first = held()
    const second = held()
    const a = deleteJobFromLists(queryClient, backup7, () => first.promise)
    const b = deleteJobFromLists(queryClient, backup8, () => second.promise)
    await vi.waitFor(() =>
      expect(queryClient.getQueryData(['activity', null])).toEqual({
        pages: [[]],
        pageParams: [],
      })
    )

    // A refresh while both are out lists both rows again.
    queryClient.setQueryData(['activity', null], { pages: [[backup7, backup8]], pageParams: [] })
    first.resolve()
    await a
    // The refetch waits for the other delete; the row it confirmed goes now.
    expect(queryClient.getQueryData(['activity', null])).toEqual({
      pages: [[backup8]],
      pageParams: [],
    })
    expect(pendingDeletes(queryClient).has('backup-7')).toBe(false)
    second.resolve()
    await b
  })
})

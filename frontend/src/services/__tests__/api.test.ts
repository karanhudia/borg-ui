import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import MockAdapter from 'axios-mock-adapter'
import { toast } from 'react-hot-toast'
import api, { operationsAPI, archivesAPI as archivesApiClient } from '../api'

describe('api response interceptor', () => {
  let toastErrorSpy: ReturnType<typeof vi.spyOn>

  beforeEach(() => {
    toastErrorSpy = vi.spyOn(toast, 'error').mockReturnValue('toast-id')
  })

  afterEach(() => {
    toastErrorSpy.mockRestore()
  })

  it.each([
    ['string detail', 'backend.errors.plan.featureNotAvailable'],
    [
      'object detail',
      {
        key: 'backend.errors.plan.featureNotAvailable',
        params: { feature: 'container_backups' },
      },
    ],
    [
      'JSON string detail',
      JSON.stringify({
        key: 'backend.errors.plan.featureNotAvailable',
        params: { feature: 'container_backups' },
      }),
    ],
  ])(
    'does not show the generic permission toast for plan-gated feature errors with %s',
    async (_label, detail) => {
      const mock = new MockAdapter(api)

      try {
        mock.onPost('/backup-plans/7/run').reply(403, {
          detail,
        })

        await expect(api.post('/backup-plans/7/run')).rejects.toMatchObject({
          response: { status: 403 },
        })

        expect(toastErrorSpy).not.toHaveBeenCalledWith(
          "You don't have permission to perform this action"
        )
      } finally {
        mock.restore()
      }
    }
  )

  it('shows the generic permission toast for ordinary permission errors', async () => {
    const mock = new MockAdapter(api)

    try {
      mock.onPost('/settings/users').reply(403, { detail: 'Forbidden' })

      await expect(api.post('/settings/users')).rejects.toMatchObject({
        response: { status: 403 },
      })

      expect(toastErrorSpy).toHaveBeenCalledWith("You don't have permission to perform this action")
    } finally {
      mock.restore()
    }
  })
})

describe('operationsAPI', () => {
  it('requests the queue view', async () => {
    const mock = new MockAdapter(api)
    mock.onGet('/operations/queue').reply(200, { repositories: [], limits: {}, paused: false })
    const response = await operationsAPI.getQueue()
    expect(response.data.paused).toBe(false)
    mock.restore()
  })

  it('pauses and resumes background work', async () => {
    const mock = new MockAdapter(api)
    mock.onPost('/operations/pause').reply(200, { paused: true })
    mock.onPost('/operations/resume').reply(200, { paused: false })
    await operationsAPI.pause()
    await operationsAPI.resume()
    expect(mock.history.post).toHaveLength(2)
    mock.restore()
  })

  it('updates index worker limits', async () => {
    const mock = new MockAdapter(api)
    mock.onPut('/operations/limits').reply(200, {})
    await operationsAPI.updateLimits(4)
    expect(JSON.parse(mock.history.put[0].data)).toEqual({ index_workers: 4 })
    mock.restore()
  })

  it('cancels an operation', async () => {
    const mock = new MockAdapter(api)
    mock.onPost('/operations/9/cancel').reply(200, {})
    await operationsAPI.cancel(9)
    expect(mock.history.post[0].url).toBe('/operations/9/cancel')
    mock.restore()
  })
})

describe('archivesAPI status strip and rebuild', () => {
  it('requests the status strip for a repository', async () => {
    const mock = new MockAdapter(api)
    mock.onGet('/repositories/3/status-strip').reply(200, { cells: [], overdue_available: false })
    const response = await archivesApiClient.getStatusStrip(3)
    expect(response.data.overdue_available).toBe(false)
    mock.restore()
  })

  it('requests a rebuild from a given stage', async () => {
    const mock = new MockAdapter(api)
    mock.onPost('/repositories/3/rebuild').reply(200, { run_id: 'r1', operations: [1, 2] })
    const response = await archivesApiClient.rebuild(3, 'archives')
    expect(JSON.parse(mock.history.post[0].data)).toEqual({ from: 'archives' })
    expect(response.data.run_id).toBe('r1')
    mock.restore()
  })
})

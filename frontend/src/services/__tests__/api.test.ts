import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import MockAdapter from 'axios-mock-adapter'
import { toast } from 'react-hot-toast'
import api from '../api'

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

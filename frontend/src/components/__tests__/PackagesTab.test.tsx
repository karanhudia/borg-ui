import { beforeEach, describe, expect, it, vi } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import PackagesTab from '../PackagesTab'
import { renderWithProviders, userEvent } from '../../test/test-utils'
import i18n from '../../i18n'

const { apiGetMock, apiPostMock, toastSuccessMock, trackPackageMock } = vi.hoisted(() => ({
  apiGetMock: vi.fn(),
  apiPostMock: vi.fn(),
  toastSuccessMock: vi.fn(),
  trackPackageMock: vi.fn(),
}))

vi.mock('react-hot-toast', async () => {
  const actual = await vi.importActual<typeof import('react-hot-toast')>('react-hot-toast')
  return {
    ...actual,
    toast: {
      ...actual.toast,
      success: toastSuccessMock,
      error: vi.fn(),
    },
  }
})

vi.mock('../../services/api', () => ({
  default: {
    get: apiGetMock,
    post: apiPostMock,
    put: vi.fn(),
    delete: vi.fn(),
  },
}))

vi.mock('../../hooks/useAnalytics', () => ({
  useAnalytics: () => ({
    trackPackage: trackPackageMock,
    EventAction: {
      COMPLETE: 'complete',
      CREATE: 'create',
      DELETE: 'delete',
      EDIT: 'edit',
      FAIL: 'fail',
      START: 'start',
      VIEW: 'view',
    },
  }),
}))

vi.mock('../DataTable', () => ({
  default: ({
    data,
    actions,
    loading,
  }: {
    data: Array<Record<string, unknown>>
    actions?: Array<{
      label: string
      onClick: (row: Record<string, unknown>) => void
      show?: (row: Record<string, unknown>) => boolean
    }>
    loading?: boolean
  }) => (
    <div>
      {loading && <span>Loading</span>}
      {data.map((row) => (
        <div key={String(row.id)}>
          <span>{String(row.name)}</span>
          {actions
            ?.filter((action) => (action.show ? action.show(row) : true))
            .map((action) => (
              <button key={`${row.id}-${action.label}`} onClick={() => action.onClick(row)}>
                {action.label}
              </button>
            ))}
        </div>
      ))}
    </div>
  ),
}))

describe('PackagesTab', () => {
  beforeEach(async () => {
    await i18n.changeLanguage('en')
    apiGetMock.mockReset()
    apiPostMock.mockReset()
    toastSuccessMock.mockReset()
    trackPackageMock.mockReset()
  })

  it('interpolates the package name in the install-start toast', async () => {
    apiGetMock.mockImplementation((url: string) => {
      if (url === '/packages/') {
        return Promise.resolve({
          data: [
            {
              id: 7,
              name: 'curl',
              install_command: 'sudo apt-get install -y curl',
              description: null,
              status: 'pending',
              install_log: null,
              installed_at: null,
              last_check: null,
              created_at: '2026-01-01T00:00:00+00:00',
              updated_at: '2026-01-01T00:00:00+00:00',
            },
          ],
        })
      }

      return Promise.reject(new Error(`Unexpected GET ${url}`))
    })
    apiPostMock.mockResolvedValue({
      data: {
        job_id: 42,
        message: 'backend.success.packages.installationStarted',
        status: 'pending',
      },
    })

    renderWithProviders(<PackagesTab />)

    await userEvent.click(await screen.findByRole('button', { name: 'Install' }))

    await waitFor(() => {
      expect(toastSuccessMock).toHaveBeenCalledWith("Package 'curl' installation started")
    })
    expect(apiPostMock).toHaveBeenCalledWith('/packages/7/install')
  })
})

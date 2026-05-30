import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, screen, renderWithProviders } from '../../test/test-utils'
import NotificationsTab from '../NotificationsTab'
import { notificationsAPI, repositoriesAPI } from '../../services/api'

vi.mock('../../services/api', () => ({
  notificationsAPI: {
    list: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
    test: vi.fn(),
  },
  repositoriesAPI: {
    list: vi.fn(),
  },
}))

vi.mock('../../hooks/useAnalytics', () => ({
  useAnalytics: () => ({
    trackNotifications: vi.fn(),
    EventAction: {
      CREATE: 'Create',
      EDIT: 'Edit',
      DELETE: 'Delete',
      TEST: 'Test',
      VIEW: 'View',
    },
  }),
}))

vi.mock('../shared/ResponsiveDialog', () => ({
  default: ({
    open,
    children,
    footer,
  }: {
    open: boolean
    children: ReactNode
    footer?: ReactNode
  }) =>
    open ? (
      <div>
        {children}
        {footer}
      </div>
    ) : null,
}))

vi.mock('../MultiRepositorySelector', () => ({
  default: () => <div>MultiRepositorySelector</div>,
}))

vi.mock('react-hot-toast', async () => {
  const actual = await vi.importActual<typeof import('react-hot-toast')>('react-hot-toast')
  return {
    ...actual,
    toast: {
      success: vi.fn(),
      error: vi.fn(),
    },
  }
})

describe('NotificationsTab', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(notificationsAPI.list).mockResolvedValue({ data: [] } as never)
    vi.mocked(repositoriesAPI.list).mockResolvedValue({ data: { repositories: [] } } as never)
    vi.mocked(notificationsAPI.create).mockResolvedValue({ data: {} } as never)
    vi.mocked(notificationsAPI.update).mockResolvedValue({ data: {} } as never)
  })

  it('renders a backup warning toggle in the notification form', async () => {
    renderWithProviders(<NotificationsTab />)

    fireEvent.click(await screen.findByRole('button', { name: /add service/i }))

    expect(await screen.findByLabelText('Warning')).toBeInTheDocument()
    expect(screen.getByLabelText(/stale backup alerts/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/backup reports/i)).toBeInTheDocument()
  })

  it('submits monitoring and report notification toggles', async () => {
    renderWithProviders(<NotificationsTab />)

    fireEvent.click(await screen.findByRole('button', { name: /add service/i }))
    fireEvent.change(screen.getByLabelText(/service name/i), { target: { value: 'Ops Alerts' } })
    fireEvent.change(screen.getByLabelText(/service url/i, { selector: 'input' }), {
      target: { value: 'json://example' },
    })
    fireEvent.click(screen.getByLabelText(/stale backup alerts/i))
    fireEvent.click(screen.getByRole('button', { name: /^add$/i }))

    await vi.waitFor(() => {
      expect(notificationsAPI.create).toHaveBeenCalled()
    })
    expect(vi.mocked(notificationsAPI.create).mock.calls[0][0]).toEqual(
      expect.objectContaining({
        notify_on_stale_backup: false,
        notify_on_backup_report: true,
      })
    )
  })
})

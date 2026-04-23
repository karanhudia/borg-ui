import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { screen, renderWithProviders, userEvent } from '../../test/test-utils'
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

vi.mock('../ResponsiveDialog', () => ({
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
    const user = userEvent.setup()
    renderWithProviders(<NotificationsTab />)

    await user.click(await screen.findByRole('button', { name: /add service/i }))

    expect(await screen.findByLabelText('Warning')).toBeInTheDocument()
  })
})

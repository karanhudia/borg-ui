import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderWithProviders, screen, userEvent, waitFor } from '../../test/test-utils'
import AnnouncementManager from '../AnnouncementManager'

const {
  announcementSurfaceMock,
  acknowledgeAnnouncementMock,
  snoozeAnnouncementMock,
  trackAnnouncementCtaClickMock,
} = vi.hoisted(() => ({
  announcementSurfaceMock: vi.fn(),
  acknowledgeAnnouncementMock: vi.fn(),
  snoozeAnnouncementMock: vi.fn(),
  trackAnnouncementCtaClickMock: vi.fn(),
}))

vi.mock('../../hooks/useAnnouncementSurface', () => ({
  useAnnouncementSurface: () => announcementSurfaceMock(),
}))

vi.mock('../AnnouncementModal', () => ({
  default: ({
    announcement,
    open,
    onAcknowledge,
    onSnooze,
    onCtaClick,
  }: {
    announcement: { id: string; title: string } | null
    open: boolean
    onAcknowledge: () => void
    onSnooze: () => void
    onCtaClick?: () => void
  }) =>
    open && announcement ? (
      <div>
        <div>{announcement.title}</div>
        <button onClick={onAcknowledge}>Got it</button>
        <button onClick={onSnooze}>Remind me later</button>
        <button onClick={onCtaClick}>View details</button>
      </div>
    ) : null,
}))

describe('AnnouncementManager', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    announcementSurfaceMock.mockReturnValue({
      announcement: {
        id: 'update-1',
        type: 'update_available',
        priority: 50,
        title: 'Update Available',
        message: 'A new version is ready.',
      },
      acknowledgeAnnouncement: acknowledgeAnnouncementMock,
      snoozeAnnouncement: snoozeAnnouncementMock,
      trackAnnouncementCtaClick: trackAnnouncementCtaClickMock,
    })
  })

  it('renders the selected announcement', async () => {
    renderWithProviders(<AnnouncementManager />)

    expect(await screen.findByText('Update Available')).toBeInTheDocument()
  })

  it('forwards acknowledge actions', async () => {
    const user = userEvent.setup()
    renderWithProviders(<AnnouncementManager />)

    expect(await screen.findByText('Update Available')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /got it/i }))

    expect(acknowledgeAnnouncementMock).toHaveBeenCalledTimes(1)
  })

  it('forwards snooze actions', async () => {
    const user = userEvent.setup()
    renderWithProviders(<AnnouncementManager />)

    expect(await screen.findByText('Update Available')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /remind me later/i }))

    expect(snoozeAnnouncementMock).toHaveBeenCalledTimes(1)
  })

  it('forwards CTA clicks', async () => {
    const user = userEvent.setup()
    renderWithProviders(<AnnouncementManager />)

    expect(await screen.findByText('Update Available')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /view details/i }))

    expect(trackAnnouncementCtaClickMock).toHaveBeenCalledTimes(1)
  })

  it('stays hidden when the announcement surface is closed by the parent', async () => {
    renderWithProviders(<AnnouncementManager open={false} />)

    await waitFor(() => {
      expect(screen.queryByText('Update Available')).not.toBeInTheDocument()
    })
  })
})

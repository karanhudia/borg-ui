import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderWithProviders, screen, userEvent, waitFor } from '../../test/test-utils'
import AnnouncementManager from '../AnnouncementManager'

const { fetchAnnouncementsManifestMock, getAnnouncementsUrlMock, systemInfoMock } = vi.hoisted(
  () => ({
    fetchAnnouncementsManifestMock: vi.fn(),
    getAnnouncementsUrlMock: vi.fn(() => 'https://example.test/announcements.json'),
    systemInfoMock: vi.fn(),
  })
)

vi.mock('../../hooks/useSystemInfo', () => ({
  useSystemInfo: () => systemInfoMock(),
}))

vi.mock('../../services/announcements', () => ({
  fetchAnnouncementsManifest: fetchAnnouncementsManifestMock,
  getAnnouncementsUrl: getAnnouncementsUrlMock,
}))

vi.mock('../AnnouncementModal', () => ({
  default: ({
    announcement,
    open,
    onAcknowledge,
    onSnooze,
  }: {
    announcement: { id: string; title: string } | null
    open: boolean
    onAcknowledge: () => void
    onSnooze: () => void
  }) =>
    open && announcement ? (
      <div>
        <div>{announcement.title}</div>
        <button onClick={onAcknowledge}>Got it</button>
        <button onClick={onSnooze}>Remind me later</button>
      </div>
    ) : null,
}))

describe('AnnouncementManager', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    systemInfoMock.mockReturnValue({
      data: {
        app_version: '1.78.0',
        borg_version: 'borg 1.4.0',
        borg2_version: 'borg2 2.0.0',
        plan: 'community',
        features: {},
      },
    })
    fetchAnnouncementsManifestMock.mockResolvedValue({
      version: 1,
      generated_at: '2026-04-02T00:00:00Z',
      announcements: [
        {
          id: 'update-1',
          type: 'update_available',
          priority: 50,
          title: 'Update Available',
          message: 'A new version is ready.',
          snooze_days: 7,
          starts_at: '2026-01-01T00:00:00Z',
          target_plans: ['community'],
        },
      ],
    })
  })

  it('fetches the configured manifest URL and renders the selected announcement', async () => {
    renderWithProviders(<AnnouncementManager />)

    await waitFor(() => {
      expect(getAnnouncementsUrlMock).toHaveBeenCalled()
      expect(fetchAnnouncementsManifestMock).toHaveBeenCalledWith(
        'https://example.test/announcements.json'
      )
    })

    expect(await screen.findByText('Update Available')).toBeInTheDocument()
  })

  it('acknowledges the active announcement and hides it for future renders', async () => {
    const user = userEvent.setup()
    const { rerender } = renderWithProviders(<AnnouncementManager />)

    expect(await screen.findByText('Update Available')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /got it/i }))

    expect(localStorage.getItem('announcement:update-1:ack')).toBe('true')
    await waitFor(() => {
      expect(screen.queryByText('Update Available')).not.toBeInTheDocument()
    })

    rerender(<AnnouncementManager />)

    await waitFor(() => {
      expect(screen.queryByText('Update Available')).not.toBeInTheDocument()
    })
  })

  it('snoozes the active announcement and hides it until the snooze expires', async () => {
    const user = userEvent.setup()
    const { rerender } = renderWithProviders(<AnnouncementManager />)

    expect(await screen.findByText('Update Available')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /remind me later/i }))

    const snoozeUntil = localStorage.getItem('announcement:update-1:snooze_until')
    expect(snoozeUntil).toBeTruthy()
    expect(new Date(snoozeUntil!).getTime()).toBeGreaterThan(Date.now())

    await waitFor(() => {
      expect(screen.queryByText('Update Available')).not.toBeInTheDocument()
    })

    rerender(<AnnouncementManager />)

    await waitFor(() => {
      expect(screen.queryByText('Update Available')).not.toBeInTheDocument()
    })
  })

  it('shows the higher-priority security notice before the update and falls through after ack', async () => {
    const user = userEvent.setup()
    fetchAnnouncementsManifestMock.mockResolvedValue({
      version: 1,
      generated_at: '2026-04-02T00:00:00Z',
      announcements: [
        {
          id: 'update-1',
          type: 'update_available',
          priority: 50,
          title: 'Update Available',
          message: 'A new version is ready.',
          starts_at: '2026-01-01T00:00:00Z',
          target_plans: ['community'],
        },
        {
          id: 'security-1',
          type: 'security_notice',
          priority: 100,
          title: 'Security Notice',
          message: 'Important action required.',
          snooze_days: 3,
          starts_at: '2026-01-01T00:00:00Z',
          target_plans: ['community'],
        },
      ],
    })

    renderWithProviders(<AnnouncementManager />)

    expect(await screen.findByText('Security Notice')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /got it/i }))

    expect(localStorage.getItem('announcement:security-1:ack')).toBe('true')
    expect(await screen.findByText('Update Available')).toBeInTheDocument()
  })
})

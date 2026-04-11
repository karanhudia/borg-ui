import { describe, expect, it, vi } from 'vitest'
import { fireEvent, screen, renderWithProviders, userEvent } from '../../test/test-utils'
import AnnouncementModal from '../AnnouncementModal'

describe('AnnouncementModal', () => {
  const baseAnnouncement = {
    id: 'release-1.70.0',
    type: 'update_available' as const,
    title: 'Borg UI 1.70.0 is available',
    message: 'A new release is available.',
  }

  it('hides the acknowledge action for non-dismissible announcements', () => {
    renderWithProviders(
      <AnnouncementModal
        announcement={{ ...baseAnnouncement, dismissible: false }}
        open
        onAcknowledge={vi.fn()}
        onSnooze={vi.fn()}
      />
    )

    expect(screen.queryByRole('button', { name: 'Got it' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Remind me later' })).toBeInTheDocument()
  })

  it('shows the acknowledge action when the announcement is dismissible', () => {
    renderWithProviders(
      <AnnouncementModal
        announcement={{ ...baseAnnouncement, dismissible: true }}
        open
        onAcknowledge={vi.fn()}
        onSnooze={vi.fn()}
      />
    )

    expect(screen.getByRole('button', { name: 'Got it' })).toBeInTheDocument()
  })

  it('wires the snooze and acknowledge handlers and renders highlights with CTA', async () => {
    const user = userEvent.setup()
    const onAcknowledge = vi.fn()
    const onSnooze = vi.fn()
    const onCtaClick = vi.fn()

    renderWithProviders(
      <AnnouncementModal
        announcement={{
          ...baseAnnouncement,
          dismissible: true,
          highlights: ['First improvement', 'Second improvement'],
          cta_label: 'View release notes',
          cta_url: 'javascript:void(0)',
        }}
        open
        onAcknowledge={onAcknowledge}
        onSnooze={onSnooze}
        onCtaClick={onCtaClick}
      />
    )

    expect(screen.getByText('First improvement')).toBeInTheDocument()
    expect(screen.getByText('Second improvement')).toBeInTheDocument()
    expect(screen.getByText('Latest release')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /view release notes/i })).toHaveAttribute(
      'href',
      'javascript:void(0)'
    )

    await user.click(screen.getByRole('button', { name: 'Remind me later' }))
    await user.click(screen.getByRole('button', { name: 'Got it' }))
    fireEvent.click(screen.getByRole('link', { name: /view release notes/i }))

    expect(onSnooze).toHaveBeenCalledTimes(1)
    expect(onAcknowledge).toHaveBeenCalledTimes(1)
    expect(onCtaClick).toHaveBeenCalledTimes(1)
  })

  it('uses the close button for dismissible notices', async () => {
    const user = userEvent.setup()
    const onAcknowledge = vi.fn()

    renderWithProviders(
      <AnnouncementModal
        announcement={{ ...baseAnnouncement, dismissible: true, type: 'security_notice' }}
        open
        onAcknowledge={onAcknowledge}
        onSnooze={vi.fn()}
      />
    )

    await user.click(screen.getByRole('button', { name: /close announcement/i }))

    expect(onAcknowledge).toHaveBeenCalledTimes(1)
  })
})

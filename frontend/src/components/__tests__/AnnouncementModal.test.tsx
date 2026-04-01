import { describe, expect, it, vi } from 'vitest'
import { screen } from '../../test/test-utils'
import { renderWithProviders } from '../../test/test-utils'
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
})

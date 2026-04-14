import AnnouncementModal from './AnnouncementModal'
import { useAnnouncementSurface } from '../hooks/useAnnouncementSurface'

interface AnnouncementManagerProps {
  open?: boolean
}

export default function AnnouncementManager({ open = true }: AnnouncementManagerProps = {}) {
  const { announcement, acknowledgeAnnouncement, snoozeAnnouncement, trackAnnouncementCtaClick } =
    useAnnouncementSurface()

  return (
    <AnnouncementModal
      announcement={announcement}
      open={open && !!announcement}
      onAcknowledge={acknowledgeAnnouncement}
      onSnooze={snoozeAnnouncement}
      onCtaClick={trackAnnouncementCtaClick}
    />
  )
}

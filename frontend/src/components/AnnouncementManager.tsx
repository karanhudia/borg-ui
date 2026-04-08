import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import AnnouncementModal from './AnnouncementModal'
import { useSystemInfo } from '../hooks/useSystemInfo'
import {
  DEFAULT_ANNOUNCEMENTS_MANIFEST,
  fetchAnnouncementsManifest,
  getAnnouncementsUrl,
} from '../services/announcements'
import {
  acknowledgeAnnouncement,
  getAnnouncementSnoozeDays,
  resolveAnnouncementLocale,
  selectAnnouncement,
  snoozeAnnouncement,
} from '../utils/announcements'

export default function AnnouncementManager() {
  const [hiddenAnnouncementIds, setHiddenAnnouncementIds] = useState<string[]>([])
  const { i18n } = useTranslation()
  const { data: systemInfo } = useSystemInfo()
  const announcementsUrl = getAnnouncementsUrl()

  const { data: manifest } = useQuery({
    queryKey: ['announcements-manifest', announcementsUrl],
    queryFn: () => fetchAnnouncementsManifest(announcementsUrl),
    initialData: DEFAULT_ANNOUNCEMENTS_MANIFEST,
    initialDataUpdatedAt: 0,
    staleTime: 60 * 60 * 1000,
    retry: false,
  })

  const selectedAnnouncement = useMemo(() => {
    if (!systemInfo || !manifest) return null

    const announcement = selectAnnouncement(
      manifest.announcements.filter(
        (announcement) => !hiddenAnnouncementIds.includes(announcement.id)
      ),
      {
        appVersion: systemInfo.app_version,
        plan: systemInfo.plan,
        now: new Date(),
      }
    )

    return announcement ? resolveAnnouncementLocale(announcement, i18n.resolvedLanguage) : null
  }, [hiddenAnnouncementIds, i18n.resolvedLanguage, manifest, systemInfo])

  const hideAnnouncement = (id: string) => {
    setHiddenAnnouncementIds((current) => [...current, id])
  }

  const handleAcknowledge = () => {
    if (!selectedAnnouncement || selectedAnnouncement.dismissible === false) return
    acknowledgeAnnouncement(selectedAnnouncement.id)
    hideAnnouncement(selectedAnnouncement.id)
  }

  const handleSnooze = () => {
    if (!selectedAnnouncement) return
    const snoozeUntil = new Date()
    snoozeUntil.setDate(snoozeUntil.getDate() + getAnnouncementSnoozeDays(selectedAnnouncement))
    snoozeAnnouncement(selectedAnnouncement.id, snoozeUntil)
    hideAnnouncement(selectedAnnouncement.id)
  }

  return (
    <AnnouncementModal
      announcement={selectedAnnouncement}
      open={!!selectedAnnouncement}
      onAcknowledge={handleAcknowledge}
      onSnooze={handleSnooze}
    />
  )
}

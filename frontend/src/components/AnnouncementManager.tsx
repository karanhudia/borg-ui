import { useEffect, useMemo, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import AnnouncementModal from './AnnouncementModal'
import { useAnalytics } from '../hooks/useAnalytics'
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
  const { trackAnnouncement, EventAction } = useAnalytics()
  const { data: systemInfo } = useSystemInfo()
  const announcementsUrl = getAnnouncementsUrl()
  const lastTrackedAnnouncementIdRef = useRef<string | null>(null)

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

  const buildAnnouncementAnalyticsData = (
    announcement: NonNullable<typeof selectedAnnouncement>
  ) => ({
    announcement_id: announcement.id,
    announcement_type: announcement.type,
    priority: announcement.priority ?? null,
    dismissible: announcement.dismissible !== false,
    has_cta: Boolean(announcement.cta_url),
  })

  useEffect(() => {
    if (!selectedAnnouncement) {
      lastTrackedAnnouncementIdRef.current = null
      return
    }

    if (lastTrackedAnnouncementIdRef.current === selectedAnnouncement.id) return

    lastTrackedAnnouncementIdRef.current = selectedAnnouncement.id
    trackAnnouncement(EventAction.VIEW, buildAnnouncementAnalyticsData(selectedAnnouncement))
  }, [EventAction.VIEW, selectedAnnouncement, trackAnnouncement])

  const handleAcknowledge = () => {
    if (!selectedAnnouncement || selectedAnnouncement.dismissible === false) return
    trackAnnouncement('Acknowledge', buildAnnouncementAnalyticsData(selectedAnnouncement))
    acknowledgeAnnouncement(selectedAnnouncement.id)
    hideAnnouncement(selectedAnnouncement.id)
  }

  const handleSnooze = () => {
    if (!selectedAnnouncement) return
    trackAnnouncement('Snooze', buildAnnouncementAnalyticsData(selectedAnnouncement))
    const snoozeUntil = new Date()
    snoozeUntil.setDate(snoozeUntil.getDate() + getAnnouncementSnoozeDays(selectedAnnouncement))
    snoozeAnnouncement(selectedAnnouncement.id, snoozeUntil)
    hideAnnouncement(selectedAnnouncement.id)
  }

  const handleCtaClick = () => {
    if (!selectedAnnouncement || !selectedAnnouncement.cta_url) return
    trackAnnouncement('CTA Click', buildAnnouncementAnalyticsData(selectedAnnouncement))
  }

  return (
    <AnnouncementModal
      announcement={selectedAnnouncement}
      open={!!selectedAnnouncement}
      onAcknowledge={handleAcknowledge}
      onSnooze={handleSnooze}
      onCtaClick={handleCtaClick}
    />
  )
}

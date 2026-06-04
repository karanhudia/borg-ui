import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { useAnalytics } from './useAnalytics'
import { useSystemInfo } from './useSystemInfo'
import type { Announcement } from '../types/announcements'
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

interface UseAnnouncementSurfaceResult {
  announcement: Announcement | null
  acknowledgeAnnouncement: () => void
  snoozeAnnouncement: () => void
  trackAnnouncementCtaClick: () => void
}

export function useAnnouncementSurface(): UseAnnouncementSurfaceResult {
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

  const announcement = useMemo(() => {
    if (!systemInfo || !manifest) return null

    const selectedAnnouncement = selectAnnouncement(
      manifest.announcements.filter(
        (manifestAnnouncement) => !hiddenAnnouncementIds.includes(manifestAnnouncement.id)
      ),
      {
        appVersion: systemInfo.app_version,
        plan: systemInfo.plan,
        now: new Date(),
      }
    )

    return selectedAnnouncement
      ? resolveAnnouncementLocale(selectedAnnouncement, i18n.resolvedLanguage)
      : null
  }, [hiddenAnnouncementIds, i18n.resolvedLanguage, manifest, systemInfo])

  const hideAnnouncement = useCallback((id: string) => {
    setHiddenAnnouncementIds((current) => [...current, id])
  }, [])

  const buildAnnouncementAnalyticsData = useCallback(
    (activeAnnouncement: Announcement) => ({
      announcement_id: activeAnnouncement.id,
      announcement_type: activeAnnouncement.type,
      priority: activeAnnouncement.priority ?? null,
      dismissible: activeAnnouncement.dismissible !== false,
      has_cta: Boolean(activeAnnouncement.cta_url),
    }),
    []
  )

  useEffect(() => {
    if (!announcement) {
      lastTrackedAnnouncementIdRef.current = null
      return
    }

    if (lastTrackedAnnouncementIdRef.current === announcement.id) return

    lastTrackedAnnouncementIdRef.current = announcement.id
    trackAnnouncement(EventAction.VIEW, buildAnnouncementAnalyticsData(announcement))
  }, [EventAction.VIEW, announcement, buildAnnouncementAnalyticsData, trackAnnouncement])

  const handleAcknowledgeAnnouncement = useCallback(() => {
    if (!announcement || announcement.dismissible === false) return
    trackAnnouncement('Acknowledge', buildAnnouncementAnalyticsData(announcement))
    acknowledgeAnnouncement(announcement.id)
    hideAnnouncement(announcement.id)
  }, [announcement, buildAnnouncementAnalyticsData, hideAnnouncement, trackAnnouncement])

  const handleSnoozeAnnouncement = useCallback(() => {
    if (!announcement) return
    trackAnnouncement('Snooze', buildAnnouncementAnalyticsData(announcement))
    const snoozeUntil = new Date()
    snoozeUntil.setDate(snoozeUntil.getDate() + getAnnouncementSnoozeDays(announcement))
    snoozeAnnouncement(announcement.id, snoozeUntil)
    hideAnnouncement(announcement.id)
  }, [announcement, buildAnnouncementAnalyticsData, hideAnnouncement, trackAnnouncement])

  const handleTrackAnnouncementCtaClick = useCallback(() => {
    if (!announcement || !announcement.cta_url) return
    trackAnnouncement('CTA Click', buildAnnouncementAnalyticsData(announcement))
  }, [announcement, buildAnnouncementAnalyticsData, trackAnnouncement])

  return {
    announcement,
    acknowledgeAnnouncement: handleAcknowledgeAnnouncement,
    snoozeAnnouncement: handleSnoozeAnnouncement,
    trackAnnouncementCtaClick: handleTrackAnnouncementCtaClick,
  }
}

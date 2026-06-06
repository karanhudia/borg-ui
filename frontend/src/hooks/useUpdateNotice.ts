import { useCallback, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import type { Announcement } from '../types/announcements'
import {
  DEFAULT_ANNOUNCEMENTS_MANIFEST,
  fetchAnnouncementsManifest,
  getAnnouncementsUrl,
} from '../services/announcements'
import { compareVersions, resolveAnnouncementLocale } from '../utils/announcements'
import { useSystemInfo } from './useSystemInfo'
import { useAnalytics } from './useAnalytics'

const STORAGE_PREFIX = 'sidebar_update_notice'
const SURFACE = 'sidebar_update_notice'

function getDismissKey(announcementId: string) {
  return `${STORAGE_PREFIX}:${announcementId}:dismissed`
}

function isNoticeDismissed(announcementId: string) {
  try {
    return localStorage.getItem(getDismissKey(announcementId)) === 'true'
  } catch {
    return false
  }
}

function setNoticeDismissed(announcementId: string) {
  try {
    localStorage.setItem(getDismissKey(announcementId), 'true')
  } catch {
    // Ignore storage write failures (private mode, quota, etc.).
  }
}

const VERSION_REGEX = /(\d+(?:\.\d+){1,3}(?:-[\w.]+)?)/

function extractVersion(announcement: Announcement): string | null {
  const idMatch = announcement.id.match(VERSION_REGEX)
  if (idMatch) return idMatch[1]
  const titleMatch = announcement.title.match(VERSION_REGEX)
  if (titleMatch) return titleMatch[1]
  return null
}

export interface UpdateNotice {
  id: string
  version: string | null
  title: string
  ctaUrl: string | null
}

export interface UseUpdateNoticeResult {
  notice: UpdateNotice | null
  dismiss: () => void
  trackCtaClick: () => void
}

export function useUpdateNotice(): UseUpdateNoticeResult {
  const [dismissedTick, setDismissedTick] = useState(0)
  const { i18n } = useTranslation()
  const { data: systemInfo } = useSystemInfo()
  const { trackAnnouncement } = useAnalytics()
  const announcementsUrl = getAnnouncementsUrl()

  const { data: manifest } = useQuery({
    queryKey: ['announcements-manifest', announcementsUrl],
    queryFn: () => fetchAnnouncementsManifest(announcementsUrl),
    initialData: DEFAULT_ANNOUNCEMENTS_MANIFEST,
    initialDataUpdatedAt: 0,
    staleTime: 60 * 60 * 1000,
    retry: false,
  })

  const notice = useMemo<UpdateNotice | null>(() => {
    if (!systemInfo || !manifest) return null
    void dismissedTick

    const candidates = manifest.announcements
      .filter((a) => a.type === 'update_available')
      .filter((a) => !isNoticeDismissed(a.id))
      .map((a) => ({ announcement: a, version: extractVersion(a) }))
      .filter(
        ({ version }) => version !== null && compareVersions(version, systemInfo.app_version) > 0
      )

    if (candidates.length === 0) return null

    candidates.sort((a, b) => compareVersions(b.version as string, a.version as string))
    const winner = candidates[0]
    const localized = resolveAnnouncementLocale(winner.announcement, i18n.resolvedLanguage)

    return {
      id: winner.announcement.id,
      version: winner.version,
      title: localized.title,
      ctaUrl: localized.cta_url ?? null,
    }
  }, [systemInfo, manifest, i18n.resolvedLanguage, dismissedTick])

  const dismiss = useCallback(() => {
    if (!notice) return
    setNoticeDismissed(notice.id)
    trackAnnouncement('Dismiss', {
      announcement_id: notice.id,
      surface: SURFACE,
    })
    setDismissedTick((tick) => tick + 1)
  }, [notice, trackAnnouncement])

  const trackCtaClick = useCallback(() => {
    if (!notice) return
    trackAnnouncement('CTA Click', {
      announcement_id: notice.id,
      surface: SURFACE,
    })
  }, [notice, trackAnnouncement])

  return { notice, dismiss, trackCtaClick }
}

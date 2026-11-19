import { useCallback, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useAnalytics } from './useAnalytics'
import { useAnnouncementsManifest } from './useAnnouncementsManifest'
import { useSystemInfo } from './useSystemInfo'
import type { Announcement } from '../types/announcements'
import { resolveAnnouncementLocale, selectSeasonalBadge } from '../utils/announcements'

export interface SeasonalBadgeState {
  badge: Announcement | null
  /** True when this install's plan gets the sale line and the link. */
  showSale: boolean
  trackSaleClick: () => void
}

export function useSeasonalBadge(): SeasonalBadgeState {
  const { i18n } = useTranslation()
  const { trackAnnouncement } = useAnalytics()
  const { data: systemInfo } = useSystemInfo()
  const { data: manifest } = useAnnouncementsManifest()
  const [now] = useState(() => new Date())

  const badge = useMemo(() => {
    if (!systemInfo || !Array.isArray(manifest?.announcements)) return null
    const selected = selectSeasonalBadge(manifest.announcements, {
      appVersion: systemInfo.app_version,
      plan: systemInfo.plan,
      now,
    })
    return selected ? resolveAnnouncementLocale(selected, i18n.resolvedLanguage) : null
  }, [i18n.resolvedLanguage, manifest, now, systemInfo])

  const showSale = Boolean(
    badge?.cta_url && systemInfo && badge.cta_plans?.includes(systemInfo.plan)
  )

  const trackSaleClick = useCallback(() => {
    if (!badge) return
    trackAnnouncement('CTA Click', {
      announcement_id: badge.id,
      announcement_type: badge.type,
      priority: badge.priority ?? null,
      dismissible: false,
      has_cta: true,
    })
  }, [badge, trackAnnouncement])

  return { badge, showSale, trackSaleClick }
}

import { useCallback } from 'react'
import { useLocation } from 'react-router-dom'
import {
  trackEvent,
  trackPageView,
  EventCategory,
  EventAction,
  anonymizeEntityName,
} from '../utils/analytics'
import { formatBytes, parseBytes } from '../utils/dateUtils'

type AnalyticsEntity =
  | string
  | {
      name?: string | null
      repository?: string | null
      total_size?: string | number | null
      size_bytes?: number | null
    }

/**
 * Custom hook for Umami analytics tracking.
 * Provides easy-to-use tracking functions for components.
 *
 * Entity names (repos, connections, etc.) are automatically hashed for privacy.
 * Example: "my-backup-repo" → "a3f2b1c8"
 */
export const useAnalytics = () => {
  const location = useLocation()

  const resolveEntityName = useCallback((entity?: AnalyticsEntity) => {
    if (typeof entity === 'string') return entity
    return entity?.name ?? entity?.repository ?? undefined
  }, [])

  const resolveEntitySize = useCallback((entity?: AnalyticsEntity) => {
    if (!entity || typeof entity === 'string') return undefined
    if (typeof entity.size_bytes === 'number') return entity.size_bytes
    if (typeof entity.total_size === 'number') return entity.total_size
    if (typeof entity.total_size === 'string' && entity.total_size.trim()) {
      return parseBytes(entity.total_size)
    }
    return undefined
  }, [])

  const buildEntityData = useCallback(
    (entity?: AnalyticsEntity, extra?: Record<string, unknown>) => {
      const data: Record<string, unknown> = { ...(extra || {}) }
      const entityName = resolveEntityName(entity)
      const sizeBytes = resolveEntitySize(entity)

      if (entityName) {
        data.name = anonymizeEntityName(entityName)
      }

      if (sizeBytes !== undefined) {
        data.size_bytes = sizeBytes
        data.size_human = formatBytes(sizeBytes)
      }

      return Object.keys(data).length ? data : undefined
    },
    [resolveEntityName, resolveEntitySize]
  )

  // Track page view with current location
  const trackPage = useCallback(
    (customTitle?: string) => {
      trackPageView(customTitle || `${location.pathname}${location.search}`)
    },
    [location]
  )

  // Generic event tracking
  const track = useCallback(
    (
      category: string,
      action: string,
      nameOrData?: string | Record<string, unknown>,
      value?: number
    ) => {
      trackEvent(category, action, nameOrData, value)
    },
    []
  )

  // Repository-specific tracking with anonymous entity hash
  const trackRepository = useCallback(
    (action: string, entity?: AnalyticsEntity) => {
      trackEvent(EventCategory.REPOSITORY, action, buildEntityData(entity))
    },
    [buildEntityData]
  )

  // Backup tracking - descriptor for type (e.g., 'logs'), entityName for repo
  const trackBackup = useCallback(
    (action: string, descriptor?: string, entity?: AnalyticsEntity) => {
      trackEvent(
        EventCategory.BACKUP,
        action,
        buildEntityData(entity, descriptor ? { descriptor } : undefined)
      )
    },
    [buildEntityData]
  )

  // Archive tracking with anonymous entity hash
  const trackArchive = useCallback(
    (action: string, entity?: AnalyticsEntity) => {
      trackEvent(EventCategory.ARCHIVE, action, buildEntityData(entity))
    },
    [buildEntityData]
  )

  // Mount tracking with anonymous entity hash
  const trackMount = useCallback(
    (action: string, entity?: AnalyticsEntity) => {
      trackEvent(EventCategory.MOUNT, action, buildEntityData(entity))
    },
    [buildEntityData]
  )

  // Maintenance tracking - operationType required, entityName for repo hash
  const trackMaintenance = useCallback(
    (action: string, operationType: string, entity?: AnalyticsEntity) => {
      trackEvent(
        EventCategory.MAINTENANCE,
        action,
        buildEntityData(entity, { operation_type: operationType })
      )
    },
    [buildEntityData]
  )

  const trackSSH = useCallback(
    (action: string, entityNameOrData?: string | Record<string, unknown>) => {
      if (typeof entityNameOrData === 'string') {
        trackEvent(EventCategory.SSH, action, { name: anonymizeEntityName(entityNameOrData) })
        return
      }

      trackEvent(EventCategory.SSH, action, entityNameOrData)
    },
    []
  )

  const trackSettings = useCallback(
    (action: string, settingNameOrData?: string | Record<string, unknown>) => {
      trackEvent(EventCategory.SETTINGS, action, settingNameOrData)
    },
    []
  )

  const trackScripts = useCallback(
    (action: string, scriptName?: string, data?: Record<string, unknown>) => {
      trackEvent(EventCategory.SCRIPT, action, {
        ...(data || {}),
        ...(scriptName ? { name: anonymizeEntityName(scriptName) } : {}),
      })
    },
    []
  )

  const trackNotifications = useCallback((action: string, data?: Record<string, unknown>) => {
    trackEvent(EventCategory.NOTIFICATION, action, data)
  }, [])

  const trackSystem = useCallback((action: string, data?: Record<string, unknown>) => {
    trackEvent(EventCategory.SYSTEM, action, data)
  }, [])

  const trackPackage = useCallback(
    (action: string, packageName?: string, data?: Record<string, unknown>) => {
      trackEvent(EventCategory.PACKAGE, action, {
        ...(data || {}),
        ...(packageName ? { name: packageName } : {}),
      })
    },
    []
  )

  const trackNavigation = useCallback((action: string, data?: Record<string, unknown>) => {
    trackEvent(EventCategory.NAVIGATION, action, data)
  }, [])

  const trackPlan = useCallback((action: string, data?: Record<string, unknown>) => {
    trackEvent(EventCategory.PLAN, action, data)
  }, [])

  // Auth tracking
  const trackAuth = useCallback((action: string) => {
    trackEvent(EventCategory.AUTH, action)
  }, [])

  return {
    trackPage,
    track,
    trackRepository,
    trackBackup,
    trackArchive,
    trackMount,
    trackMaintenance,
    trackSSH,
    trackSettings,
    trackScripts,
    trackNotifications,
    trackSystem,
    trackPackage,
    trackNavigation,
    trackPlan,
    trackAuth,
    EventCategory,
    EventAction,
  }
}

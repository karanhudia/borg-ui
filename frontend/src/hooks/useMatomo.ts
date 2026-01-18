import { useCallback } from 'react'
import { useLocation } from 'react-router-dom'
import {
  trackEvent,
  trackPageView,
  EventCategory,
  EventAction,
  anonymizeEntityName,
} from '../utils/matomo'

/**
 * Custom hook for Matomo tracking
 * Provides easy-to-use tracking functions for components
 *
 * Entity names (repos, connections, etc.) are automatically hashed for privacy.
 * Example: "my-backup-repo" → "a3f2b1c8"
 */
export const useMatomo = () => {
  const location = useLocation()

  // Track page view with current location
  const trackPage = useCallback(
    (customTitle?: string) => {
      trackPageView(customTitle || `${location.pathname}${location.search}`)
    },
    [location]
  )

  // Generic event tracking
  const track = useCallback((category: string, action: string, name?: string, value?: number) => {
    trackEvent(category, action, name, value)
  }, [])

  // Repository-specific tracking with anonymous entity hash
  const trackRepository = useCallback((action: string, entityName?: string) => {
    const hash = entityName ? anonymizeEntityName(entityName) : undefined
    trackEvent(EventCategory.REPOSITORY, action, hash)
  }, [])

  // Backup tracking - descriptor for type (e.g., 'logs'), entityName for repo
  const trackBackup = useCallback((action: string, descriptor?: string, entityName?: string) => {
    const label = entityName
      ? descriptor
        ? `${descriptor} [${anonymizeEntityName(entityName)}]`
        : anonymizeEntityName(entityName)
      : descriptor
    trackEvent(EventCategory.BACKUP, action, label)
  }, [])

  // Archive tracking with anonymous entity hash
  const trackArchive = useCallback((action: string, entityName?: string) => {
    const hash = entityName ? anonymizeEntityName(entityName) : undefined
    trackEvent(EventCategory.ARCHIVE, action, hash)
  }, [])

  // Mount tracking with anonymous entity hash
  const trackMount = useCallback((action: string, entityName?: string) => {
    const hash = entityName ? anonymizeEntityName(entityName) : undefined
    trackEvent(EventCategory.MOUNT, action, hash)
  }, [])

  // Maintenance tracking - operationType required, entityName for repo hash
  const trackMaintenance = useCallback(
    (action: string, operationType: string, entityName?: string) => {
      const label = entityName
        ? `${operationType} [${anonymizeEntityName(entityName)}]`
        : operationType
      trackEvent(EventCategory.MAINTENANCE, action, label)
    },
    []
  )

  // SSH connection tracking with anonymous entity hash
  const trackSSH = useCallback((action: string, entityName?: string) => {
    const hash = entityName ? anonymizeEntityName(entityName) : undefined
    trackEvent(EventCategory.SSH, action, hash)
  }, [])

  // Settings tracking (setting names are safe, no hashing needed)
  const trackSettings = useCallback((action: string, settingName?: string) => {
    trackEvent(EventCategory.SETTINGS, action, settingName)
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
    trackAuth,
    EventCategory,
    EventAction,
  }
}

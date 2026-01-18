import { useCallback } from 'react'
import { useLocation } from 'react-router-dom'
import { trackEvent, trackPageView, EventCategory, EventAction } from '../utils/matomo'

/**
 * Custom hook for Matomo tracking
 * Provides easy-to-use tracking functions for components
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

  // Repository-specific tracking
  const trackRepository = useCallback((action: string, repositoryName?: string) => {
    trackEvent(EventCategory.REPOSITORY, action, repositoryName)
  }, [])

  // Backup tracking
  const trackBackup = useCallback((action: string, repositoryName?: string) => {
    trackEvent(EventCategory.BACKUP, action, repositoryName)
  }, [])

  // Archive tracking
  const trackArchive = useCallback((action: string, archiveName?: string) => {
    trackEvent(EventCategory.ARCHIVE, action, archiveName)
  }, [])

  // Mount tracking
  const trackMount = useCallback((action: string, mountPoint?: string) => {
    trackEvent(EventCategory.MOUNT, action, mountPoint)
  }, [])

  // Maintenance tracking
  const trackMaintenance = useCallback((action: string, operationType?: string) => {
    trackEvent(EventCategory.MAINTENANCE, action, operationType)
  }, [])

  // SSH connection tracking
  const trackSSH = useCallback((action: string, connectionName?: string) => {
    trackEvent(EventCategory.SSH, action, connectionName)
  }, [])

  // Settings tracking
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

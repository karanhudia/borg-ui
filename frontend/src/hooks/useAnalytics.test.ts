import { renderHook } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const trackEventMock = vi.fn()
const trackPageViewMock = vi.fn()
const anonymizeEntityNameMock = vi.fn((name: string) => `hash:${name}`)

vi.mock('../utils/analytics', () => ({
  trackEvent: trackEventMock,
  trackPageView: trackPageViewMock,
  anonymizeEntityName: anonymizeEntityNameMock,
  EventCategory: {
    REPOSITORY: 'Repository',
    BACKUP: 'Backup',
    ARCHIVE: 'Archive',
    MOUNT: 'Mount',
    MAINTENANCE: 'Maintenance',
    SSH: 'SSH Connection',
    SCRIPT: 'Script',
    NOTIFICATION: 'Notification',
    SYSTEM: 'System',
    PACKAGE: 'Package',
    SETTINGS: 'Settings',
    AUTH: 'Authentication',
    NAVIGATION: 'Navigation',
    PLAN: 'Plan',
  },
  EventAction: {
    VIEW: 'View',
    START: 'Start',
    EDIT: 'Edit',
  },
}))

describe('useAnalytics', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    window.history.pushState({}, '', '/settings?tab=appearance')
  })

  it('tracks the current page by default', async () => {
    const { useAnalytics } = await import('./useAnalytics')
    const { result } = renderHook(() => useAnalytics())

    result.current.trackPage()

    expect(trackPageViewMock).toHaveBeenCalledWith('/settings?tab=appearance')
  })

  it('tracks repository events with anonymized names and normalized sizes', async () => {
    const { useAnalytics } = await import('./useAnalytics')
    const { result } = renderHook(() => useAnalytics())

    result.current.trackRepository('View', {
      name: 'prod-repo',
      total_size: '1.5 GB',
    })

    expect(anonymizeEntityNameMock).toHaveBeenCalledWith('prod-repo')
    expect(trackEventMock).toHaveBeenCalledWith('Repository', 'View', {
      name: 'hash:prod-repo',
      size_bytes: 1610612736,
      size_human: '1.50 GB',
    })
  })

  it('tracks backup events with descriptors and SSH/settings wrappers', async () => {
    const { useAnalytics } = await import('./useAnalytics')
    const { result } = renderHook(() => useAnalytics())

    result.current.trackBackup('Start', 'logs', { repository: 'nightly-repo' })
    result.current.trackSSH('Edit', 'ssh-prod')
    result.current.trackSettings('Edit', { section: 'appearance', theme: 'dark' })

    expect(trackEventMock).toHaveBeenNthCalledWith(1, 'Backup', 'Start', {
      descriptor: 'logs',
      name: 'hash:nightly-repo',
    })
    expect(trackEventMock).toHaveBeenNthCalledWith(2, 'SSH Connection', 'Edit', {
      name: 'hash:ssh-prod',
    })
    expect(trackEventMock).toHaveBeenNthCalledWith(3, 'Settings', 'Edit', {
      section: 'appearance',
      theme: 'dark',
    })
  })

  it('tracks script and maintenance events with merged payloads', async () => {
    const { useAnalytics } = await import('./useAnalytics')
    const { result } = renderHook(() => useAnalytics())

    result.current.trackScripts('Start', 'health-check', { source: 'toolbar' })
    result.current.trackMaintenance('Start', 'prune', { name: 'repo-a', size_bytes: 2048 })

    expect(trackEventMock).toHaveBeenNthCalledWith(1, 'Script', 'Start', {
      source: 'toolbar',
      name: 'hash:health-check',
    })
    expect(trackEventMock).toHaveBeenNthCalledWith(2, 'Maintenance', 'Start', {
      operation_type: 'prune',
      name: 'hash:repo-a',
      size_bytes: 2048,
      size_human: '2.00 KB',
    })
  })
})

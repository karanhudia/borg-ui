import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { Announcement } from '../../types/announcements'
import {
  acknowledgeAnnouncement,
  compareVersions,
  getAnnouncementAckKey,
  getAnnouncementSnoozeKey,
  isAnnouncementEligible,
  resolveAnnouncementLocale,
  selectAnnouncement,
  snoozeAnnouncement,
} from '../announcements'

const baseAnnouncement: Announcement = {
  id: 'release-1.70.0',
  type: 'update_available',
  title: 'Borg UI 1.70.0 is available',
  message: 'A new release is available.',
  starts_at: '2026-04-01T00:00:00Z',
  ends_at: '2026-07-01T00:00:00Z',
  min_app_version: '0.0.0',
  max_app_version: '1.69.9',
}

describe('announcements utils', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-04-10T12:00:00Z'))
  })

  afterEach(() => {
    vi.clearAllTimers()
    vi.useRealTimers()
  })

  it('compares semantic versions numerically', () => {
    expect(compareVersions('1.10.0', '1.9.9')).toBe(1)
    expect(compareVersions('1.2.0', '1.2.0')).toBe(0)
    expect(compareVersions('v1.2.3', '1.3.0')).toBe(-1)
  })

  it('filters out acknowledged announcements', () => {
    acknowledgeAnnouncement(baseAnnouncement.id)

    expect(
      isAnnouncementEligible(baseAnnouncement, {
        appVersion: '1.60.0',
        plan: 'community',
        now: new Date(),
      })
    ).toBe(false)
  })

  it('filters out snoozed announcements', () => {
    snoozeAnnouncement(baseAnnouncement.id, new Date('2026-04-12T12:00:00Z'))

    expect(
      isAnnouncementEligible(baseAnnouncement, {
        appVersion: '1.60.0',
        plan: 'community',
        now: new Date(),
      })
    ).toBe(false)
  })

  it('selects the highest priority applicable announcement', () => {
    const securityNotice: Announcement = {
      ...baseAnnouncement,
      id: 'security-1',
      type: 'security_notice',
      priority: 100,
      title: 'Security notice',
      max_app_version: '1.65.0',
    }

    const updateNotice: Announcement = {
      ...baseAnnouncement,
      priority: 50,
    }

    expect(
      selectAnnouncement([updateNotice, securityNotice], {
        appVersion: '1.60.0',
        plan: 'community',
        now: new Date(),
      })?.id
    ).toBe('security-1')
  })

  it('prefers the latest applicable update over non-critical announcement types', () => {
    const releaseHighlight: Announcement = {
      ...baseAnnouncement,
      id: 'release-highlight-1',
      type: 'release_highlight',
      priority: 90,
      title: 'Roadmap update',
    }

    const newerUpdate: Announcement = {
      ...baseAnnouncement,
      id: 'release-1.71.0',
      priority: 50,
      starts_at: '2026-04-05T00:00:00Z',
      title: 'Borg UI 1.71.0 is available',
    }

    expect(
      selectAnnouncement([releaseHighlight, newerUpdate], {
        appVersion: '1.60.0',
        plan: 'community',
        now: new Date(),
      })?.id
    ).toBe('release-1.71.0')
  })

  it('keeps update_available ahead of equal-priority critical notices', () => {
    const securityNotice: Announcement = {
      ...baseAnnouncement,
      id: 'security-1',
      type: 'security_notice',
      priority: 50,
      title: 'Security notice',
    }

    const updateNotice: Announcement = {
      ...baseAnnouncement,
      priority: 50,
    }

    expect(
      selectAnnouncement([updateNotice, securityNotice], {
        appVersion: '1.60.0',
        plan: 'community',
        now: new Date(),
      })?.id
    ).toBe(baseAnnouncement.id)
  })

  it('ignores announcements that do not match the installed version', () => {
    expect(
      selectAnnouncement([baseAnnouncement], {
        appVersion: '1.70.0',
        plan: 'community',
        now: new Date(),
      })
    ).toBeNull()
  })

  it('stores acknowledgements using stable localStorage keys', () => {
    acknowledgeAnnouncement(baseAnnouncement.id)
    expect(localStorage.getItem(getAnnouncementAckKey(baseAnnouncement.id))).toBe('true')
    expect(getAnnouncementAckKey(baseAnnouncement.id)).toBe('announcement:release-1.70.0:ack')
  })

  it('stores snoozes using stable localStorage keys', () => {
    const snoozeUntil = new Date('2026-04-12T12:00:00Z')
    snoozeAnnouncement(baseAnnouncement.id, snoozeUntil)

    expect(localStorage.getItem(getAnnouncementSnoozeKey(baseAnnouncement.id))).toBe(
      snoozeUntil.toISOString()
    )
    expect(getAnnouncementSnoozeKey(baseAnnouncement.id)).toBe(
      'announcement:release-1.70.0:snooze_until'
    )
  })

  it('rejects invalid announcement shapes', () => {
    expect(
      isAnnouncementEligible(
        {
          ...baseAnnouncement,
          type: 'invalid_type' as Announcement['type'],
        },
        {
          appVersion: '1.60.0',
          plan: 'community',
          now: new Date(),
        }
      )
    ).toBe(false)
  })

  it('resolves localized manifest content for the active language', () => {
    const localized = resolveAnnouncementLocale(
      {
        ...baseAnnouncement,
        title_localized: {
          es: 'Borg UI 1.70.0 ya esta disponible',
        },
        message_localized: {
          es: 'Hay una nueva version disponible.',
        },
        highlights: ['English highlight'],
        highlights_localized: {
          es: ['Punto destacado en espanol'],
        },
        cta_label: 'View details',
        cta_label_localized: {
          es: 'Ver detalles',
        },
      },
      'es-ES'
    )

    expect(localized.title).toBe('Borg UI 1.70.0 ya esta disponible')
    expect(localized.message).toBe('Hay una nueva version disponible.')
    expect(localized.highlights).toEqual(['Punto destacado en espanol'])
    expect(localized.cta_label).toBe('Ver detalles')
  })

  it('falls back to the base manifest text when a locale override is missing', () => {
    const localized = resolveAnnouncementLocale(
      {
        ...baseAnnouncement,
        title_localized: {
          de: 'Borg UI 1.70.0 ist verfugbar',
        },
      },
      'it'
    )

    expect(localized.title).toBe(baseAnnouncement.title)
    expect(localized.message).toBe(baseAnnouncement.message)
  })
})

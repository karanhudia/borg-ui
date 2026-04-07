import type { Announcement, AnnouncementContext } from '../types/announcements'
import type { Plan } from '../core/features'

const ANNOUNCEMENT_TYPES = new Set<Announcement['type']>([
  'update_available',
  'release_highlight',
  'security_notice',
  'maintenance_notice',
  'migration_notice',
  'custom_announcement',
])

const VALID_PLANS = new Set<Plan>(['community', 'pro', 'enterprise'])
const CRITICAL_ANNOUNCEMENT_TYPES = new Set<Announcement['type']>([
  'security_notice',
  'migration_notice',
])

function toNumericParts(version: string): number[] {
  const matches = version.match(/\d+/g)
  return matches ? matches.map((part) => Number.parseInt(part, 10)) : [0]
}

function isNonEmptyString(value: unknown): value is string {
  return typeof value === 'string' && value.trim().length > 0
}

function isOptionalString(value: unknown): value is string | undefined {
  return value === undefined || typeof value === 'string'
}

function isLocalizedStringMap(value: unknown): value is Record<string, string> | undefined {
  return (
    value === undefined ||
    (typeof value === 'object' && value !== null && Object.values(value).every(isNonEmptyString))
  )
}

function isLocalizedHighlightsMap(value: unknown): value is Record<string, string[]> | undefined {
  return (
    value === undefined ||
    (typeof value === 'object' &&
      value !== null &&
      Object.values(value).every(
        (highlights) =>
          Array.isArray(highlights) && highlights.length > 0 && highlights.every(isNonEmptyString)
      ))
  )
}

function isValidDateString(value: string | undefined) {
  if (!value) return true
  return !Number.isNaN(new Date(value).getTime())
}

function isValidAnnouncementShape(announcement: Announcement) {
  return (
    isNonEmptyString(announcement.id) &&
    ANNOUNCEMENT_TYPES.has(announcement.type) &&
    isNonEmptyString(announcement.title) &&
    isLocalizedStringMap(announcement.title_localized) &&
    isNonEmptyString(announcement.message) &&
    isLocalizedStringMap(announcement.message_localized) &&
    (announcement.priority === undefined || Number.isFinite(announcement.priority)) &&
    (announcement.highlights === undefined ||
      (Array.isArray(announcement.highlights) &&
        announcement.highlights.every(isNonEmptyString))) &&
    isLocalizedHighlightsMap(announcement.highlights_localized) &&
    isOptionalString(announcement.cta_label) &&
    isLocalizedStringMap(announcement.cta_label_localized) &&
    isOptionalString(announcement.cta_url) &&
    (announcement.dismissible === undefined || typeof announcement.dismissible === 'boolean') &&
    (announcement.snooze_days === undefined ||
      (Number.isInteger(announcement.snooze_days) && announcement.snooze_days > 0)) &&
    isValidDateString(announcement.starts_at) &&
    isValidDateString(announcement.ends_at) &&
    isOptionalString(announcement.min_app_version) &&
    isOptionalString(announcement.max_app_version) &&
    (announcement.target_plans === undefined ||
      (Array.isArray(announcement.target_plans) &&
        announcement.target_plans.every((plan) => VALID_PLANS.has(plan))))
  )
}

export function compareVersions(a: string, b: string): number {
  const aParts = toNumericParts(a)
  const bParts = toNumericParts(b)
  const maxLength = Math.max(aParts.length, bParts.length)

  for (let i = 0; i < maxLength; i += 1) {
    const aPart = aParts[i] ?? 0
    const bPart = bParts[i] ?? 0
    if (aPart > bPart) return 1
    if (aPart < bPart) return -1
  }

  return 0
}

export function getAnnouncementAckKey(id: string) {
  return `announcement:${id}:ack`
}

export function getAnnouncementSnoozeKey(id: string) {
  return `announcement:${id}:snooze_until`
}

export function acknowledgeAnnouncement(id: string) {
  localStorage.setItem(getAnnouncementAckKey(id), 'true')
}

export function snoozeAnnouncement(id: string, snoozeUntil: Date) {
  localStorage.setItem(getAnnouncementSnoozeKey(id), snoozeUntil.toISOString())
}

export function isAnnouncementAcknowledged(id: string) {
  return localStorage.getItem(getAnnouncementAckKey(id)) === 'true'
}

export function isAnnouncementSnoozed(id: string, now: Date) {
  const rawValue = localStorage.getItem(getAnnouncementSnoozeKey(id))
  if (!rawValue) return false

  const snoozeUntil = new Date(rawValue)
  if (Number.isNaN(snoozeUntil.getTime())) return false
  return snoozeUntil > now
}

export function getAnnouncementSnoozeDays(announcement: Announcement) {
  return Math.max(announcement.snooze_days ?? 7, 1)
}

function getLocaleCandidates(locale?: string): string[] {
  if (!locale) return ['default']

  const trimmed = locale.trim()
  if (!trimmed) return ['default']

  const baseLanguage = trimmed.split('-')[0]
  return Array.from(new Set([trimmed, baseLanguage, 'default']))
}

function resolveLocalizedString(
  fallback: string,
  localized: Record<string, string> | undefined,
  locale?: string
) {
  if (!localized) return fallback

  for (const candidate of getLocaleCandidates(locale)) {
    const value = localized[candidate]
    if (isNonEmptyString(value)) return value
  }

  return fallback
}

function resolveLocalizedHighlights(
  fallback: string[] | undefined,
  localized: Record<string, string[]> | undefined,
  locale?: string
) {
  if (!localized) return fallback

  for (const candidate of getLocaleCandidates(locale)) {
    const value = localized[candidate]
    if (Array.isArray(value) && value.length > 0 && value.every(isNonEmptyString)) {
      return value
    }
  }

  return fallback
}

export function resolveAnnouncementLocale(
  announcement: Announcement,
  locale?: string
): Announcement {
  return {
    ...announcement,
    title: resolveLocalizedString(announcement.title, announcement.title_localized, locale),
    message: resolveLocalizedString(announcement.message, announcement.message_localized, locale),
    highlights: resolveLocalizedHighlights(
      announcement.highlights,
      announcement.highlights_localized,
      locale
    ),
    cta_label: announcement.cta_label
      ? resolveLocalizedString(announcement.cta_label, announcement.cta_label_localized, locale)
      : resolveLocalizedString('', announcement.cta_label_localized, locale) ||
        announcement.cta_label,
  }
}

function isWithinVersionRange(announcement: Announcement, appVersion: string) {
  if (
    announcement.min_app_version &&
    compareVersions(appVersion, announcement.min_app_version) < 0
  ) {
    return false
  }

  if (
    announcement.max_app_version &&
    compareVersions(appVersion, announcement.max_app_version) > 0
  ) {
    return false
  }

  return true
}

function isWithinActiveWindow(announcement: Announcement, now: Date) {
  if (announcement.starts_at) {
    const startsAt = new Date(announcement.starts_at)
    if (!Number.isNaN(startsAt.getTime()) && startsAt > now) {
      return false
    }
  }

  if (announcement.ends_at) {
    const endsAt = new Date(announcement.ends_at)
    if (!Number.isNaN(endsAt.getTime()) && endsAt <= now) {
      return false
    }
  }

  return true
}

function matchesPlan(announcement: Announcement, plan: string) {
  return !announcement.target_plans?.length || announcement.target_plans.includes(plan as never)
}

export function isAnnouncementEligible(
  announcement: Announcement,
  context: AnnouncementContext
): boolean {
  return (
    isValidAnnouncementShape(announcement) &&
    isWithinActiveWindow(announcement, context.now) &&
    isWithinVersionRange(announcement, context.appVersion) &&
    matchesPlan(announcement, context.plan) &&
    !isAnnouncementAcknowledged(announcement.id) &&
    !isAnnouncementSnoozed(announcement.id, context.now)
  )
}

function compareAnnouncements(a: Announcement, b: Announcement) {
  const priorityDiff = (b.priority ?? 0) - (a.priority ?? 0)
  if (priorityDiff !== 0) return priorityDiff

  const startsAtDiff = new Date(b.starts_at ?? 0).getTime() - new Date(a.starts_at ?? 0).getTime()
  if (startsAtDiff !== 0) return startsAtDiff

  return b.id.localeCompare(a.id)
}

export function selectAnnouncement(
  announcements: Announcement[],
  context: AnnouncementContext
): Announcement | null {
  const eligibleAnnouncements = announcements
    .filter((announcement) => isAnnouncementEligible(announcement, context))
    .sort(compareAnnouncements)

  const highestPriorityCritical = eligibleAnnouncements.find((announcement) =>
    CRITICAL_ANNOUNCEMENT_TYPES.has(announcement.type)
  )
  const latestApplicableUpdate = eligibleAnnouncements.find(
    (announcement) => announcement.type === 'update_available'
  )

  if (highestPriorityCritical && !latestApplicableUpdate) {
    return highestPriorityCritical
  }

  if (
    highestPriorityCritical &&
    latestApplicableUpdate &&
    (highestPriorityCritical.priority ?? 0) > (latestApplicableUpdate.priority ?? 0)
  ) {
    return highestPriorityCritical
  }

  return latestApplicableUpdate ?? eligibleAnnouncements[0] ?? null
}

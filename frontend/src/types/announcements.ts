import type { Plan } from '../core/features'

export type AnnouncementType =
  | 'update_available'
  | 'release_highlight'
  | 'security_notice'
  | 'maintenance_notice'
  | 'migration_notice'
  | 'custom_announcement'

export type AnnouncementLocalizedText = Record<string, string>
export type AnnouncementLocalizedHighlights = Record<string, string[]>

export interface Announcement {
  id: string
  type: AnnouncementType
  priority?: number
  title: string
  title_localized?: AnnouncementLocalizedText
  message: string
  message_localized?: AnnouncementLocalizedText
  highlights?: string[]
  highlights_localized?: AnnouncementLocalizedHighlights
  cta_label?: string
  cta_label_localized?: AnnouncementLocalizedText
  cta_url?: string
  dismissible?: boolean
  snooze_days?: number
  starts_at?: string
  ends_at?: string
  min_app_version?: string
  max_app_version?: string
  target_plans?: Plan[]
}

export interface AnnouncementManifest {
  version: number
  generated_at?: string
  announcements: Announcement[]
}

export interface AnnouncementContext {
  appVersion: string
  plan: Plan
  now: Date
}

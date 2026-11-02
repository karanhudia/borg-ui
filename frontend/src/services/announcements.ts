import { isValidAnnouncement } from '../utils/announcements'
import { BASE_PATH } from '../utils/basePath'
import type { AnnouncementManifest } from '../types/announcements'
import announcementsManifestData from '../data/announcements.json'
import localAnnouncementsUrl from '../data/announcements.json?url'

export const LOCAL_ANNOUNCEMENTS_URL =
  BASE_PATH === '/' ? localAnnouncementsUrl : `${BASE_PATH}${localAnnouncementsUrl}`
const DEFAULT_REMOTE_ANNOUNCEMENTS_URL = 'https://updates.borgui.com/announcements.json'
export const DEFAULT_ANNOUNCEMENTS_MANIFEST = parseAnnouncementsManifest(announcementsManifestData)

function parseAnnouncementsManifest(value: unknown): AnnouncementManifest {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    throw new Error('Invalid announcements manifest')
  }
  const data = value as Record<string, unknown>
  if (!Array.isArray(data.announcements)) throw new Error('Invalid announcements manifest')
  return {
    version: typeof data.version === 'number' && Number.isFinite(data.version) ? data.version : 1,
    ...(typeof data.generated_at === 'string' ? { generated_at: data.generated_at } : {}),
    announcements: data.announcements.filter(isValidAnnouncement),
  }
}

export function getAnnouncementsUrl() {
  const configuredUrl = import.meta.env.VITE_ANNOUNCEMENTS_URL?.trim()
  if (configuredUrl) return configuredUrl

  return LOCAL_ANNOUNCEMENTS_URL
}

export async function fetchAnnouncementsManifest(url = getAnnouncementsUrl()) {
  const configuredUrl = import.meta.env.VITE_ANNOUNCEMENTS_URL?.trim()
  const candidateUrls =
    configuredUrl || import.meta.env.DEV ? [url] : [DEFAULT_REMOTE_ANNOUNCEMENTS_URL, url]

  let lastStatus: number | null = null

  for (const candidateUrl of candidateUrls) {
    let response: Response
    try {
      response = await fetch(candidateUrl, {
        headers: {
          Accept: 'application/json',
        },
      })
    } catch {
      continue
    }

    if (!response.ok) {
      lastStatus = response.status
      continue
    }

    try {
      return parseAnnouncementsManifest(await response.json())
    } catch {
      // Treat invalid JSON/envelopes like an unavailable feed and try the local fallback.
      continue
    }
  }

  throw new Error(`Failed to fetch announcements manifest${lastStatus ? ` (${lastStatus})` : ''}`)
}

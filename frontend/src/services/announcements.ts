import { BASE_PATH } from '../utils/basePath'
import type { AnnouncementManifest } from '../types/announcements'
import announcementsManifestData from '../data/announcements.json'
import localAnnouncementsUrl from '../data/announcements.json?url'

export const LOCAL_ANNOUNCEMENTS_URL =
  BASE_PATH === '/' ? localAnnouncementsUrl : `${BASE_PATH}${localAnnouncementsUrl}`
const DEFAULT_REMOTE_ANNOUNCEMENTS_URL = 'https://karanhudia.github.io/borg-ui/announcements.json'
export const DEFAULT_ANNOUNCEMENTS_MANIFEST = announcementsManifestData as AnnouncementManifest

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
    const response = await fetch(candidateUrl, {
      headers: {
        Accept: 'application/json',
      },
    })

    if (!response.ok) {
      lastStatus = response.status
      continue
    }

    const data = (await response.json()) as Partial<AnnouncementManifest>
    return {
      version: typeof data.version === 'number' ? data.version : 1,
      generated_at: data.generated_at,
      announcements: Array.isArray(data.announcements) ? data.announcements : [],
    } satisfies AnnouncementManifest
  }

  throw new Error(`Failed to fetch announcements manifest${lastStatus ? ` (${lastStatus})` : ''}`)
}

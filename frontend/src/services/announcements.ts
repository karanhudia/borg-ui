import { BASE_PATH } from '../utils/basePath'
import type { AnnouncementManifest } from '../types/announcements'

const LOCAL_ANNOUNCEMENTS_URL = `${BASE_PATH}/announcements.json`
const DEFAULT_REMOTE_ANNOUNCEMENTS_URL = 'https://karanhudia.github.io/borg-ui/announcements.json'

export function getAnnouncementsUrl() {
  const configuredUrl = import.meta.env.VITE_ANNOUNCEMENTS_URL?.trim()
  if (configuredUrl) return configuredUrl

  return import.meta.env.DEV ? LOCAL_ANNOUNCEMENTS_URL : DEFAULT_REMOTE_ANNOUNCEMENTS_URL
}

export async function fetchAnnouncementsManifest(url = getAnnouncementsUrl()) {
  const response = await fetch(url, {
    headers: {
      Accept: 'application/json',
    },
  })

  if (!response.ok) {
    throw new Error(`Failed to fetch announcements manifest (${response.status})`)
  }

  const data = (await response.json()) as Partial<AnnouncementManifest>
  return {
    version: typeof data.version === 'number' ? data.version : 1,
    generated_at: data.generated_at,
    announcements: Array.isArray(data.announcements) ? data.announcements : [],
  } satisfies AnnouncementManifest
}

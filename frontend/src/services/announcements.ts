import { BASE_PATH } from '../utils/basePath'
import type { AnnouncementManifest } from '../types/announcements'

const DEFAULT_ANNOUNCEMENTS_URL = `${BASE_PATH}/announcements.json`

export function getAnnouncementsUrl() {
  return import.meta.env.VITE_ANNOUNCEMENTS_URL?.trim() || DEFAULT_ANNOUNCEMENTS_URL
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

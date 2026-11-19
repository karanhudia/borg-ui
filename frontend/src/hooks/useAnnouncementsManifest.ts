import { useQuery } from '@tanstack/react-query'
import {
  DEFAULT_ANNOUNCEMENTS_MANIFEST,
  fetchAnnouncementsManifest,
  getAnnouncementsUrl,
} from '../services/announcements'

/** One cached manifest query shared by the announcement modal and the seasonal badge. */
export function useAnnouncementsManifest() {
  const announcementsUrl = getAnnouncementsUrl()
  return useQuery({
    queryKey: ['announcements-manifest', announcementsUrl],
    queryFn: () => fetchAnnouncementsManifest(announcementsUrl),
    initialData: DEFAULT_ANNOUNCEMENTS_MANIFEST,
    initialDataUpdatedAt: 0,
    staleTime: 60 * 60 * 1000,
    retry: false,
  })
}

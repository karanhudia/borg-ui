import { Archive } from '../types'

export type TimeGroup = 'today' | 'yesterday' | 'last7days' | 'last30days' | 'older'
export type SortOption = 'date-desc' | 'date-asc'
export type FilterType = 'all' | 'scheduled' | 'manual'

export interface GroupedArchives {
  today: Archive[]
  yesterday: Archive[]
  last7days: Archive[]
  last30days: Archive[]
  older: Archive[]
}

export interface GroupInfo {
  key: TimeGroup
  label: string
  iconName: 'Calendar' | 'Archive'
  archives: Archive[]
  defaultExpanded: boolean
}

/**
 * Determine if an archive is manual or scheduled based on its name
 */
export function getArchiveType(archive: Archive): 'manual' | 'scheduled' {
  return archive.name.startsWith('manual-backup-') ? 'manual' : 'scheduled'
}

/**
 * Filter archives by type (all, scheduled, manual)
 */
export function filterArchivesByType(archives: Archive[], filter: FilterType): Archive[] {
  if (filter === 'all') return archives
  return archives.filter((a) => getArchiveType(a) === filter)
}

/**
 * Get the time group for an archive based on its start date
 */
export function getTimeGroup(archiveDate: Date, now: Date = new Date()): TimeGroup {
  const diffMs = now.getTime() - archiveDate.getTime()
  const diffDays = diffMs / (1000 * 60 * 60 * 24)

  const isToday =
    now.getDate() === archiveDate.getDate() &&
    now.getMonth() === archiveDate.getMonth() &&
    now.getFullYear() === archiveDate.getFullYear()

  const isYesterday =
    now.getDate() - 1 === archiveDate.getDate() &&
    now.getMonth() === archiveDate.getMonth() &&
    now.getFullYear() === archiveDate.getFullYear()

  if (isToday) return 'today'
  if (isYesterday) return 'yesterday'
  if (diffDays < 7) return 'last7days'
  if (diffDays < 30) return 'last30days'
  return 'older'
}

/**
 * Group archives by time periods
 */
export function groupArchivesByTime(archives: Archive[]): GroupedArchives {
  const grouped: GroupedArchives = {
    today: [],
    yesterday: [],
    last7days: [],
    last30days: [],
    older: [],
  }

  const now = new Date()

  archives.forEach((archive) => {
    try {
      const archiveDate = new Date(archive.start)
      const group = getTimeGroup(archiveDate, now)
      grouped[group].push(archive)
    } catch {
      // If date parsing fails, put in 'older' group
      grouped.older.push(archive)
    }
  })

  return grouped
}

/**
 * Convert grouped archives to an array of GroupInfo for rendering
 */
export function getGroupsArray(grouped: GroupedArchives): GroupInfo[] {
  return [
    {
      key: 'today' as TimeGroup,
      label: 'Today',
      iconName: 'Calendar' as const,
      archives: grouped.today,
      defaultExpanded: true,
    },
    {
      key: 'yesterday' as TimeGroup,
      label: 'Yesterday',
      iconName: 'Calendar' as const,
      archives: grouped.yesterday,
      defaultExpanded: true,
    },
    {
      key: 'last7days' as TimeGroup,
      label: 'Last 7 days',
      iconName: 'Calendar' as const,
      archives: grouped.last7days,
      defaultExpanded: false,
    },
    {
      key: 'last30days' as TimeGroup,
      label: 'Last 30 days',
      iconName: 'Calendar' as const,
      archives: grouped.last30days,
      defaultExpanded: false,
    },
    {
      key: 'older' as TimeGroup,
      label: 'Older',
      iconName: 'Archive' as const,
      archives: grouped.older,
      defaultExpanded: false,
    },
  ].filter((group) => group.archives.length > 0) // Only show groups with archives
}

/**
 * Sort archives based on the selected option
 */
export function sortArchives(archives: Archive[], sortBy: SortOption): Archive[] {
  const sorted = [...archives]

  switch (sortBy) {
    case 'date-desc':
      return sorted.sort((a, b) => new Date(b.start).getTime() - new Date(a.start).getTime())
    case 'date-asc':
      return sorted.sort((a, b) => new Date(a.start).getTime() - new Date(b.start).getTime())
    default:
      return sorted
  }
}

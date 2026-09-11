import { useMemo } from 'react'
import { Box, Button, Typography, useTheme } from '@mui/material'
import ChangeBadge from './ChangeBadge'
import { changeColor } from './changeStyle'
import { useTranslation } from 'react-i18next'
import { useQuery } from '@tanstack/react-query'
import PlanGate from '../shared/PlanGate'
import { usePlan } from '../../hooks/usePlan'
import { archivesAPI } from '../../services/api'
import { formatBytes, parseBackendDate } from '../../utils/dateUtils'
import type { HistoryEntry } from '../../types/archives'

interface FileHistoryPanelProps {
  repositoryId: number
  path: string | null
  onRestoreEntry: (entry: HistoryEntry) => void
}

function FileHistoryPanelContent({ repositoryId, path, onRestoreEntry }: FileHistoryPanelProps) {
  const { t } = useTranslation()

  const { data } = useQuery({
    queryKey: ['path-history', repositoryId, path],
    queryFn: () => archivesAPI.getPathHistory(repositoryId, path as string).then((res) => res.data),
    enabled: !!path,
  })

  // The path's own series, when its entries all belong to one (a Borg 2
  // repository can hold several): the older-archive count and the coverage
  // caption are statements about that series. Spread over several, or with
  // no entries at all, the repository-wide coverage stands.
  const series = useMemo(() => {
    if (!data) return null
    const names = new Set([
      ...data.entries.map((entry) => entry.series),
      ...data.present.map((range) => range.series),
    ])
    return names.size === 1 ? [...names][0] : null
  }, [data])

  const { data: seriesArchives } = useQuery({
    queryKey: ['archive-series-for-history', repositoryId, series],
    queryFn: () =>
      archivesAPI.listStored(repositoryId, { series: series as string }).then((res) => res.data),
    enabled: !!series,
  })

  // "Not present in N older archives" is a statement about the archives of
  // the path's series older than its first sighting, so it needs exactly
  // those indexed, not the whole repository (a backup that just landed is
  // still pending and says nothing about the past).
  // Older by archive time, the id only as the tie-breaker: a listing can
  // add an archive with an earlier start under a larger id.
  const { notPresentOlderCount, olderArchivesIndexed } = useMemo(() => {
    if (!data || !seriesArchives) return { notPresentOlderCount: 0, olderArchivesIndexed: true }
    const firstSeen = new Set(data.present.map((range) => range.from_archive_id))
    const byAge = [...seriesArchives.archives].sort((a, b) =>
      a.start < b.start ? -1 : a.start > b.start ? 1 : a.id - b.id
    )
    const earliestPresent = byAge.findIndex((row) => firstSeen.has(row.id))
    if (earliestPresent < 0) return { notPresentOlderCount: 0, olderArchivesIndexed: true }
    const older = byAge.slice(0, earliestPresent)
    return {
      notPresentOlderCount: older.length,
      olderArchivesIndexed: older.every((row) => row.history_state === 'indexed'),
    }
  }, [data, seriesArchives])

  const entries = data?.entries ?? []
  // What the answer is based on. With nothing indexed the entries say
  // nothing about the path; with a partial index they cover the indexed
  // archives only, so "no earlier archive contains this path" is only true
  // once every archive is indexed. The route's coverage counts the whole
  // repository; once the path's series is known, its own archives decide
  // (the listing carries their states), since every statement below is
  // about that series. A `skipped` archive is uncovered like a `pending`
  // one: on an agent's repository it never gets indexed (the capability
  // says so), on a server's it is a leftover the next listing reopens.
  // Only `indexed` and `total` are re-scoped; `exhausted` is read below
  // from the repository-wide object alone.
  const coverage = useMemo(() => {
    const repositoryWide = data?.coverage
    if (!repositoryWide || !seriesArchives) return repositoryWide
    const rows = seriesArchives.archives
    return {
      ...repositoryWide,
      indexed: rows.filter((row) => row.history_state === 'indexed').length,
      total: rows.length,
    }
  }, [data, seriesArchives])
  // Entries can outlive a reset of the archive states (a series rename puts
  // every archive back to pending without deleting its rows), so the
  // "nothing indexed" answer is given only when there is nothing to show.
  const nothingIndexed =
    coverage != null && coverage.total > 0 && coverage.indexed === 0 && entries.length === 0
  // Entries with nothing indexed (a series reset left them) still get the
  // caption: "0 of N" is what they are based on.
  const partiallyIndexed = coverage != null && coverage.indexed < coverage.total
  const fullyIndexed = coverage == null || coverage.indexed >= coverage.total
  const sortedEntries = [...entries].sort((a, b) => (a.start < b.start ? 1 : -1))
  const firstAddedId = [...entries]
    .filter((e) => e.change === 'added')
    .sort((a, b) => (a.start < b.start ? -1 : 1))[0]?.archive_id

  const theme = useTheme()

  // With nothing to show for the path on an agent's repository, the reason
  // comes first: no index at all, or one that stays partial (whatever was
  // indexed on the server before the move stays, nothing is added). Only a
  // complete index says the path is absent.
  const unavailableForAgent =
    coverage != null &&
    coverage.capability === 'agent_unsupported' &&
    entries.length === 0 &&
    coverage.indexed < coverage.total
  if (data && (nothingIndexed || unavailableForAgent)) {
    return (
      <Box>
        <Typography variant="body2" sx={{ color: 'text.secondary' }}>
          {unavailableForAgent
            ? t('archives.files.historyUnavailableAgent')
            : data.coverage != null && data.coverage.exhausted >= data.coverage.total
              ? // the executor has given up on every archive: not "yet"
                t('archives.files.historyFailed')
              : t('archives.files.historyNotIndexed')}
        </Typography>
      </Box>
    )
  }

  return (
    <Box>
      {data && sortedEntries.length === 0 && (
        <Typography variant="body2" sx={{ color: 'text.secondary' }}>
          {fullyIndexed
            ? t('archives.files.historyEmpty')
            : t('archives.files.historyEmptyIndexed')}
        </Typography>
      )}
      {partiallyIndexed && coverage && (
        <Typography variant="caption" sx={{ color: 'text.secondary', display: 'block', mb: 1 }}>
          {t('archives.files.historyCoverage', {
            indexed: coverage.indexed,
            count: coverage.total,
          })}
        </Typography>
      )}
      <Box>
        {sortedEntries.map((entry) => {
          const isFirst = entry.archive_id === firstAddedId
          const change = isFirst ? 'added' : entry.change === 'summary' ? 'modified' : entry.change
          const detail = isFirst
            ? t('archives.files.firstSeen')
            : entry.change === 'modified'
              ? `${formatBytes(entry.size_before)} → ${formatBytes(entry.size_after)}`
              : t(`archives.changes.${entry.change === 'summary' ? 'modified' : entry.change}`)
          return (
            <Box
              key={entry.archive_id}
              sx={{
                display: 'grid',
                gridTemplateColumns: '20px minmax(0, 1fr) auto',
                columnGap: 1.5,
                alignItems: 'start',
                py: 1.25,
                borderTop: 1,
                borderColor: 'divider',
                '&:first-of-type': { borderTop: 0 },
              }}
            >
              <Box sx={{ pt: 0.25 }}>
                <ChangeBadge change={change} size={18} />
              </Box>
              <Box sx={{ minWidth: 0 }}>
                <Typography
                  variant="body2"
                  noWrap
                  title={entry.archive_name}
                  sx={{ fontWeight: 600 }}
                >
                  {entry.archive_name}
                </Typography>
                <Typography variant="caption" sx={{ color: 'text.secondary', display: 'block' }}>
                  {parseBackendDate(entry.start).toLocaleString()}
                  <Box
                    component="span"
                    sx={{ color: changeColor(theme, change), ml: 1, fontWeight: 600 }}
                  >
                    {detail}
                  </Box>
                </Typography>
              </Box>
              <Button size="small" onClick={() => onRestoreEntry(entry)} sx={{ mt: -0.5 }}>
                {t('archives.files.restoreThis')}
              </Button>
            </Box>
          )
        })}
      </Box>
      {olderArchivesIndexed && notPresentOlderCount > 0 && (
        <Typography variant="caption" sx={{ color: 'text.secondary', display: 'block', mt: 1 }}>
          {t('archives.files.notPresent', { count: notPresentOlderCount })}
        </Typography>
      )}
    </Box>
  )
}

export default function FileHistoryPanel(props: FileHistoryPanelProps) {
  const { can } = usePlan()
  return (
    <PlanGate feature="archive_history" disabled surface="archive_files" operation="view_history">
      {can('archive_history') ? (
        <FileHistoryPanelContent {...props} />
      ) : (
        <Box sx={{ minHeight: 60 }} />
      )}
    </PlanGate>
  )
}

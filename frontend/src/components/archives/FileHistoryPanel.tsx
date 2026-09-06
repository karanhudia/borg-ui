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

  const series = data?.entries[0]?.series ?? null

  const { data: seriesArchives } = useQuery({
    queryKey: ['archive-series-for-history', repositoryId, series],
    queryFn: () =>
      archivesAPI.listStored(repositoryId, { series: series as string }).then((res) => res.data),
    enabled: !!series,
  })

  const notPresentOlderCount = useMemo(() => {
    if (!data || !seriesArchives) return 0
    const earliestPresentId = data.present.reduce<number | null>(
      (min, range) => (min === null || range.from_archive_id < min ? range.from_archive_id : min),
      null
    )
    if (earliestPresentId === null) return 0
    return seriesArchives.archives.filter((row) => row.id < earliestPresentId).length
  }, [data, seriesArchives])

  const entries = data?.entries ?? []
  const sortedEntries = [...entries].sort((a, b) => (a.start < b.start ? 1 : -1))
  const firstAddedId = [...entries]
    .filter((e) => e.change === 'added')
    .sort((a, b) => (a.start < b.start ? -1 : 1))[0]?.archive_id

  const theme = useTheme()

  return (
    <Box>
      {data && sortedEntries.length === 0 && (
        <Typography variant="body2" sx={{ color: 'text.secondary' }}>
          {t('archives.files.historyEmpty')}
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
      {notPresentOlderCount > 0 && (
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

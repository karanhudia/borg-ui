import { useMemo } from 'react'
import { Box, Button, List, ListItem, ListItemText, Typography } from '@mui/material'
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

  return (
    <Box>
      {notPresentOlderCount > 0 && (
        <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
          {t('archives.files.notPresent', { count: notPresentOlderCount })}
        </Typography>
      )}
      <List dense>
        {sortedEntries.map((entry) => (
          <ListItem
            key={entry.archive_id}
            secondaryAction={
              <Button size="small" onClick={() => onRestoreEntry(entry)}>
                {t('archives.files.restoreThis')}
              </Button>
            }
          >
            <ListItemText
              primary={entry.archive_name}
              secondary={
                <>
                  {parseBackendDate(entry.start).toLocaleString()} ·{' '}
                  {entry.archive_id === firstAddedId
                    ? t('archives.files.firstSeen')
                    : entry.change === 'modified'
                      ? `${formatBytes(entry.size_before)} → ${formatBytes(entry.size_after)}`
                      : t(
                          `archives.changes.${entry.change === 'summary' ? 'modified' : entry.change}`
                        )}
                </>
              }
            />
          </ListItem>
        ))}
      </List>
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

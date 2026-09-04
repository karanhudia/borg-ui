import { useMemo, useState } from 'react'
import {
  Alert,
  Box,
  Button,
  Chip,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableRow,
  Typography,
} from '@mui/material'
import { useTranslation } from 'react-i18next'
import { useQuery } from '@tanstack/react-query'
import RichSelect from '../shared/RichSelect'
import PlanGate from '../shared/PlanGate'
import { usePlan } from '../../hooks/usePlan'
import { archivesAPI } from '../../services/api'
import { formatBytes } from '../../utils/dateUtils'
import type { ArchiveDetailResponse, ChangeType } from '../../types/archives'
import ArchiveChangesPreview from './ArchiveChangesPreview'

interface ArchiveChangesTabProps {
  repositoryId: number
  archive: ArchiveDetailResponse
}

const CHANGE_TYPES: Exclude<ChangeType, 'summary'>[] = ['added', 'removed', 'modified']
const PAGE_SIZE = 200

function ArchiveChangesTabContent({ repositoryId, archive }: ArchiveChangesTabProps) {
  const { t } = useTranslation()
  const [compareTo, setCompareTo] = useState<number | null>(archive.predecessor_id)
  const [activeFilters, setActiveFilters] = useState<ChangeType[]>([])
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE)

  const { data: olderArchives } = useQuery({
    queryKey: ['archive-series-older', repositoryId, archive.series, archive.id],
    queryFn: () =>
      archivesAPI.listStored(repositoryId, { series: archive.series }).then((res) => res.data),
  })

  const compareOptions = useMemo(() => {
    const older = (olderArchives?.archives || []).filter((row) => row.start < archive.start)
    return older.map((row) => ({
      value: String(row.id),
      primary: row.name,
      secondary: row.id === archive.predecessor_id ? t('archives.changes.previous') : undefined,
    }))
  }, [olderArchives, archive.start, archive.predecessor_id, t])

  const { data: changes, isLoading } = useQuery({
    queryKey: ['archive-changes', repositoryId, archive.id, compareTo, activeFilters],
    queryFn: () =>
      archivesAPI
        .getChanges(repositoryId, archive.id, {
          compare_to: compareTo ?? undefined,
          change: activeFilters.length > 0 ? activeFilters : undefined,
        })
        .then((res) => res.data),
  })

  const toggleFilter = (type: ChangeType) => {
    setActiveFilters((prev) =>
      prev.includes(type) ? prev.filter((f) => f !== type) : [...prev, type]
    )
  }

  const historyState = changes?.history_state ?? archive.history_state
  const rows = changes?.changes ?? []
  const visibleRows = rows.slice(0, visibleCount)

  return (
    <Box>
      <Stack direction="row" spacing={2} sx={{ mb: 2, alignItems: 'center', flexWrap: 'wrap' }}>
        <Box sx={{ minWidth: 240 }}>
          <RichSelect
            label={t('archives.changes.compareWith')}
            value={compareTo !== null ? String(compareTo) : ''}
            onChange={(value) => setCompareTo(value ? Number(value) : null)}
            options={compareOptions}
          />
        </Box>
        <Stack direction="row" spacing={1}>
          {CHANGE_TYPES.map((type) => (
            <Chip
              key={type}
              label={t(`archives.changes.${type}`)}
              color={activeFilters.includes(type) ? 'primary' : 'default'}
              onClick={() => toggleFilter(type)}
            />
          ))}
        </Stack>
      </Stack>

      {changes?.history_truncated && (
        <Alert severity="info" sx={{ mb: 2 }}>
          {t('archives.changes.truncated')}
        </Alert>
      )}

      {!isLoading && historyState !== 'indexed' && (
        <Alert
          severity="info"
          action={
            <Button size="small" onClick={() => archivesAPI.rebuild(repositoryId, 'history')}>
              {t('archives.changes.rebuildLink')}
            </Button>
          }
        >
          {historyState === 'skipped'
            ? t('archives.changes.skipped')
            : t('archives.changes.pending')}
        </Alert>
      )}

      {!isLoading && historyState === 'indexed' && rows.length === 0 && (
        <Typography variant="body2" color="text.secondary">
          {t('archives.changes.empty')}
        </Typography>
      )}

      {!isLoading && historyState === 'indexed' && rows.length > 0 && (
        <>
          <Table size="small">
            <TableBody>
              {visibleRows.map((row) => (
                <TableRow key={row.path}>
                  <TableCell>{row.path}</TableCell>
                  <TableCell>
                    {t(`archives.changes.${row.change === 'summary' ? 'modified' : row.change}`)}
                  </TableCell>
                  <TableCell>
                    {row.change === 'summary' ? (
                      t('archives.changes.summaryRow', { count: row.summary_count, path: row.path })
                    ) : row.change === 'modified' ? (
                      <>
                        {formatBytes(row.size_before)} → {formatBytes(row.size_after)}
                      </>
                    ) : (
                      formatBytes(row.size_after ?? row.size_before)
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          {rows.length > visibleCount && (
            <Button onClick={() => setVisibleCount((c) => c + PAGE_SIZE)} sx={{ mt: 1 }}>
              {t('archives.changes.showMore')}
            </Button>
          )}
        </>
      )}
    </Box>
  )
}

export default function ArchiveChangesTab(props: ArchiveChangesTabProps) {
  const { can } = usePlan()
  return (
    <PlanGate
      feature="archive_history"
      preview={<ArchiveChangesPreview />}
      surface="archive_detail"
      operation="view_changes"
    >
      {can('archive_history') ? <ArchiveChangesTabContent {...props} /> : null}
    </PlanGate>
  )
}

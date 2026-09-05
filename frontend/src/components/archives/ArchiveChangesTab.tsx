import { useMemo, useState } from 'react'
import {
  Alert,
  Box,
  Button,
  Stack,
  ToggleButton,
  ToggleButtonGroup,
  Typography,
  alpha,
  useTheme,
} from '@mui/material'
import { useTranslation } from 'react-i18next'
import { useQuery } from '@tanstack/react-query'
import RichSelect from '../shared/RichSelect'
import PlanGate from '../shared/PlanGate'
import { usePlan } from '../../hooks/usePlan'
import { archivesAPI } from '../../services/api'
import { CHANGE_GLYPH, changeColor } from './changeStyle'
import ChangeRowLine from './ChangeRowLine'
import ArchiveChangesPreview from './ArchiveChangesPreview'
import type { ArchiveDetailResponse, ChangeType } from '../../types/archives'

interface ArchiveChangesTabProps {
  repositoryId: number
  archive: ArchiveDetailResponse
}

const CHANGE_TYPES: Exclude<ChangeType, 'summary'>[] = ['added', 'removed', 'modified']
const PAGE_SIZE = 200

function ArchiveChangesTabContent({ repositoryId, archive }: ArchiveChangesTabProps) {
  const { t } = useTranslation()
  const theme = useTheme()
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

  const historyState = changes?.history_state ?? archive.history_state
  const rows = changes?.changes ?? []
  const visibleRows = rows.slice(0, visibleCount)
  const totals = changes?.totals

  return (
    <Box>
      <Stack
        direction={{ xs: 'column', md: 'row' }}
        spacing={2}
        sx={{ mb: 2, alignItems: { md: 'center' } }}
      >
        <Box sx={{ width: { xs: '100%', md: 420 } }}>
          <RichSelect
            label={t('archives.changes.compareWith')}
            value={compareTo !== null ? String(compareTo) : ''}
            onChange={(value) => setCompareTo(value ? Number(value) : null)}
            options={compareOptions}
          />
        </Box>
        <ToggleButtonGroup
          size="small"
          value={activeFilters}
          onChange={(_event, next: ChangeType[]) => setActiveFilters(next)}
          aria-label={t('archives.changes.filterLabel')}
          sx={{ bgcolor: 'background.paper', height: 40, alignSelf: { md: 'center' } }}
        >
          {CHANGE_TYPES.map((type) => {
            const color = changeColor(theme, type)
            const count = totals?.[type]
            return (
              <ToggleButton
                key={type}
                value={type}
                aria-label={t(`archives.changes.${type}`)}
                sx={{
                  textTransform: 'none',
                  fontWeight: 600,
                  fontSize: '0.8125rem',
                  px: 1.5,
                  gap: 0.75,
                  color: 'text.secondary',
                  '&:hover': { bgcolor: alpha(color, 0.06), color },
                  '&.Mui-selected': {
                    color,
                    bgcolor: alpha(color, 0.12),
                    '&:hover': { bgcolor: alpha(color, 0.18) },
                  },
                }}
              >
                <Box component="span" sx={{ color, fontFamily: 'ui-monospace, monospace' }}>
                  {CHANGE_GLYPH[type]}
                </Box>
                {t(`archives.changes.${type}`)}
                {count != null && (
                  <Box component="span" sx={{ color: 'text.secondary', fontWeight: 500 }}>
                    {count}
                  </Box>
                )}
              </ToggleButton>
            )
          })}
        </ToggleButtonGroup>
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
        <Typography variant="body2" color="text.secondary" sx={{ px: 1.5, py: 2 }}>
          {t('archives.changes.empty')}
        </Typography>
      )}

      {!isLoading && historyState === 'indexed' && rows.length > 0 && (
        <Box
          sx={{
            border: 1,
            borderColor: 'divider',
            borderRadius: 2,
            bgcolor: 'background.paper',
            py: 0.5,
          }}
        >
          {visibleRows.map((row) => (
            <ChangeRowLine key={row.path} row={row} />
          ))}
          {rows.length > visibleCount && (
            <Button onClick={() => setVisibleCount((c) => c + PAGE_SIZE)} sx={{ m: 1 }}>
              {t('archives.changes.showMore')}
            </Button>
          )}
        </Box>
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

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
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import RichSelect from '../shared/RichSelect'
import PlanGate from '../shared/PlanGate'
import IndexModeGate from './IndexModeGate'
import { usePlan } from '../../hooks/usePlan'
import { archivesAPI } from '../../services/api'
import { CHANGE_GLYPH, changeColor } from './changeStyle'
import ChangeRowLine from './ChangeRowLine'
import ArchiveChangesPreview from './ArchiveChangesPreview'
import type { ArchiveDetailResponse, ChangeRow, ChangeType } from '../../types/archives'
import type { IndexMode } from '../../types/operations'

interface ArchiveChangesTabProps {
  repositoryId: number
  archive: ArchiveDetailResponse
  // The repository's index mode (spec 6.8). Defaulted so a caller that
  // predates the mode reads as the behaviour every install had.
  indexMode?: IndexMode
}

const CHANGE_TYPES: Exclude<ChangeType, 'summary'>[] = ['added', 'removed', 'modified']
const PAGE_SIZE = 200

function ArchiveChangesTabContent({ repositoryId, archive }: ArchiveChangesTabProps) {
  const { t } = useTranslation()
  const theme = useTheme()
  const queryClient = useQueryClient()
  const [compareTo, setCompareTo] = useState<number | null>(archive.predecessor_id)
  const [activeFilters, setActiveFilters] = useState<ChangeType[]>([])
  // Pages fetched after the first one, which the query owns. The route caps
  // a response and hands back a cursor, so "Show more" has to ask for the
  // next page rather than reveal rows the client never received.
  const [extraPages, setExtraPages] = useState<ChangeRow[]>([])
  const [cursor, setCursor] = useState<string | null>(null)

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

  const {
    data: changes,
    isLoading,
    isError,
  } = useQuery({
    queryKey: ['archive-changes', repositoryId, archive.id, compareTo, activeFilters],
    queryFn: () =>
      archivesAPI
        .getChanges(repositoryId, archive.id, {
          compare_to: compareTo ?? undefined,
          change: activeFilters.length > 0 ? activeFilters : undefined,
          limit: PAGE_SIZE,
        })
        .then((res) => {
          setExtraPages([])
          setCursor(res.data.next_cursor)
          return res.data
        }),
    // A filter change re-queries; keeping the last response up until the
    // new one lands stops the chip counts flashing to nothing and the
    // chips changing width.
    placeholderData: keepPreviousData,
  })

  const morePages = useMutation({
    mutationFn: (from: string) =>
      archivesAPI
        .getChanges(repositoryId, archive.id, {
          compare_to: compareTo ?? undefined,
          change: activeFilters.length > 0 ? activeFilters : undefined,
          limit: PAGE_SIZE,
          cursor: from,
        })
        .then((res) => res.data),
    onSuccess: (page) => {
      setExtraPages((current) => [...current, ...page.changes])
      setCursor(page.next_cursor)
    },
  })

  const rebuildMutation = useMutation({
    mutationFn: () => archivesAPI.rebuild(repositoryId, 'history'),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['archive', repositoryId, archive.id] })
      queryClient.invalidateQueries({ queryKey: ['archive-changes', repositoryId, archive.id] })
      queryClient.invalidateQueries({ queryKey: ['operations-queue'] })
    },
  })

  // A refresh that fails behind rows already on screen keeps the rows; with
  // nothing to show, the empty state would claim the archive has no changes.
  const loadFailed = isError && !changes
  const historyState = changes?.history_state ?? archive.history_state
  // The repository decides whether history can exist at all; an archive of
  // a repository executed by an agent is `skipped` for good, and a rebuild
  // would only skip it again. The rebuild control is offered only where it
  // can change the outcome.
  const capability = changes?.history_capability ?? archive.history_capability ?? 'available'
  const historyUnavailable = capability !== 'available'
  const canRebuild = !historyUnavailable
  const rows = [...(changes?.changes ?? []), ...extraPages]
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
                  <Box
                    component="span"
                    sx={{
                      color: 'text.secondary',
                      fontWeight: 500,
                      fontVariantNumeric: 'tabular-nums',
                      minWidth: '2ch',
                      textAlign: 'left',
                    }}
                  >
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

      {rebuildMutation.isError && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => rebuildMutation.reset()}>
          {t('archives.changes.rebuildFailed')}
        </Alert>
      )}
      {rebuildMutation.isSuccess && (
        <Alert severity="success" sx={{ mb: 2 }} onClose={() => rebuildMutation.reset()}>
          {t('archives.changes.rebuildStarted')}
        </Alert>
      )}

      {!isLoading && historyState !== 'indexed' && (
        <Alert
          severity={historyState === 'failed' && !historyUnavailable ? 'warning' : 'info'}
          action={
            canRebuild ? (
              <Button
                size="small"
                disabled={rebuildMutation.isPending}
                onClick={() => rebuildMutation.mutate()}
              >
                {t('archives.changes.rebuildLink')}
              </Button>
            ) : undefined
          }
        >
          {capability === 'agent_unsupported'
            ? // whatever the archive's own state says (a failure recorded
              // before the move included): the failed wording promises a
              // rebuild this repository cannot have
              t('archives.changes.agentUnsupported')
            : historyState === 'skipped'
              ? t('archives.changes.skipped')
              : historyState === 'failed'
                ? t('archives.changes.failed')
                : t('archives.changes.pending')}
        </Alert>
      )}

      {!isLoading && loadFailed && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {t('archives.changes.loadFailed')}
        </Alert>
      )}

      {!isLoading && !loadFailed && historyState === 'indexed' && rows.length === 0 && (
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
            overflow: 'hidden',
          }}
        >
          {rows.map((row) => (
            <ChangeRowLine key={row.path} row={row} />
          ))}
          {cursor != null && (
            <Button
              disabled={morePages.isPending}
              onClick={() => morePages.mutate(cursor)}
              sx={{ m: 1 }}
            >
              {t('archives.changes.showMore')}
            </Button>
          )}
        </Box>
      )}
    </Box>
  )
}

export default function ArchiveChangesTab({
  indexMode = 'full',
  ...props
}: ArchiveChangesTabProps) {
  const { can } = usePlan()
  return (
    // Plan first, then mode, never both (spec 6.8): PlanGate answers for a
    // Community install, and the mode panel only renders behind it.
    <PlanGate
      feature="archive_history"
      preview={<ArchiveChangesPreview />}
      surface="archive_detail"
      operation="view_changes"
    >
      {can('archive_history') ? (
        <IndexModeGate mode={indexMode}>
          <ArchiveChangesTabContent {...props} />
        </IndexModeGate>
      ) : null}
    </PlanGate>
  )
}

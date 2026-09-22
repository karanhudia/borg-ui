import { useMemo, useRef, useState } from 'react'
import useFillViewport from '../../hooks/useFillViewport'
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
import SearchBox from '../shared/SearchBox'
import IndexModeGate from './IndexModeGate'
import { archivesAPI } from '../../services/api'
import { getApiErrorDetail } from '../../utils/apiErrors'
import { translateBackendKey } from '../../utils/translateBackendKey'
import { CHANGE_GLYPH, changeColor } from './changeStyle'
import ChangeRowLine from './ChangeRowLine'
import UpgradePrompt from '../UpgradePrompt'
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

const inertPreviewProps = { inert: 'true' } as Record<string, string>

const CHANGE_TYPES: Exclude<ChangeType, 'summary'>[] = ['added', 'removed', 'modified']
const PAGE_SIZE = 200

function ArchiveChangesTabContent({ repositoryId, archive }: ArchiveChangesTabProps) {
  const { t } = useTranslation()
  const theme = useTheme()
  const queryClient = useQueryClient()
  const [compareTo, setCompareTo] = useState<number | null>(archive.predecessor_id)
  const [activeFilters, setActiveFilters] = useState<ChangeType[]>([])
  const [needle, setNeedle] = useState('')
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
    return older.map((row) => ({ value: String(row.id), primary: row.name }))
  }, [olderArchives, archive.start])

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
  const loaded = [...(changes?.changes ?? []), ...extraPages]
  // The path filter narrows what has been loaded; "show more" still pages
  // the server, so a hit further down appears once its page is in.
  const query = needle.trim().toLowerCase()
  const rows = query ? loaded.filter((row) => row.path.toLowerCase().includes(query)) : loaded
  const listRef = useRef<HTMLDivElement>(null)
  // The frame mounts only once rows exist, so measure again when they do.
  const listHeight = useFillViewport(listRef, 240, [rows.length > 0])
  const totals = changes?.totals
  // Community reads what changed and how much; which files changed is Pro.
  // The counts are the archive's own numbers, so there is nothing to blur.
  const locked = changes?.detail_locked === true

  if (locked) {
    return (
      <Box>
        <Stack direction="row" spacing={1} sx={{ mb: 2, flexWrap: 'wrap', gap: 1 }}>
          {CHANGE_TYPES.map((type) => {
            const color = changeColor(theme, type)
            return (
              <Box
                key={type}
                sx={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 0.75,
                  px: 1.5,
                  py: 0.75,
                  borderRadius: 1.5,
                  bgcolor: alpha(color, 0.1),
                  color,
                  fontWeight: 600,
                  fontSize: '0.8125rem',
                }}
              >
                <Box component="span" sx={{ fontFamily: 'ui-monospace, monospace' }}>
                  {CHANGE_GLYPH[type]}
                </Box>
                {t(`archives.changes.${type}`)}
                <Box component="span" sx={{ fontVariantNumeric: 'tabular-nums' }}>
                  {totals?.[type] ?? 0}
                </Box>
              </Box>
            )
          })}
        </Stack>
        {!isLoading && historyState !== 'indexed' && (
          <Alert severity="info" sx={{ mb: 2 }}>
            {capability === 'agent_unsupported'
              ? t('archives.changes.agentUnsupported')
              : t('archives.changes.pending')}
          </Alert>
        )}
        <UpgradePrompt
          compact
          requiredPlan="pro"
          message={t('archives.changes.locked')}
          feature="archive_history"
        />
        {/* A sample of the rows Pro lists, dimmed and inert: the counts say how
            much changed, this says what reading them looks like. Example paths,
            never this archive's own. */}
        <Box
          aria-hidden="true"
          {...inertPreviewProps}
          sx={{
            mt: 2,
            opacity: 0.32,
            filter: 'saturate(0.7)',
            pointerEvents: 'none',
            userSelect: 'none',
          }}
        >
          <ArchiveChangesPreview />
        </Box>
      </Box>
    )
  }

  return (
    <Box>
      <Stack
        direction={{ xs: 'column', md: 'row' }}
        spacing={2}
        sx={{ mb: 2, alignItems: { md: 'center' } }}
      >
        <Box sx={{ width: { xs: '100%', md: 300 }, flexShrink: 0 }}>
          <RichSelect
            label={t('archives.changes.compareWith')}
            value={compareTo !== null ? String(compareTo) : ''}
            onChange={(value) => setCompareTo(value ? Number(value) : null)}
            options={compareOptions}
            // the same 40px as the filter buttons beside it
            size="small"
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
        <SearchBox
          value={needle}
          onChange={setNeedle}
          placeholder={t('archives.changes.search')}
          sx={{ flex: 1, minWidth: 200 }}
        />
      </Stack>

      {changes?.history_truncated && (
        <Alert severity="info" sx={{ mb: 2 }}>
          {t('archives.changes.truncated')}
        </Alert>
      )}

      {rebuildMutation.isError && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => rebuildMutation.reset()}>
          {translateBackendKey(
            getApiErrorDetail(rebuildMutation.error),
            'archives.changes.rebuildFailed'
          )}
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
        <Box sx={{ px: 1.5, py: 2 }}>
          <Typography variant="body2" color="text.secondary">
            {query ? t('archives.changes.noMatch') : t('archives.changes.empty')}
          </Typography>
          {/* the filter only sees the pages already loaded, so a match
              further down is still reachable while a cursor is left */}
          {cursor != null && (
            <Button
              disabled={morePages.isPending}
              onClick={() => morePages.mutate(cursor)}
              sx={{ mt: 1, ml: -1 }}
            >
              {t('archives.changes.showMore')}
            </Button>
          )}
        </Box>
      )}

      {!isLoading && historyState === 'indexed' && rows.length > 0 && (
        <Box
          ref={listRef}
          sx={{
            border: 1,
            borderColor: 'divider',
            borderRadius: 2,
            bgcolor: 'background.paper',
            // the list runs to the bottom of the window and scrolls
            // inside its frame; the page above it stays put
            height: listHeight ?? 'calc(100vh - 420px)',
            minHeight: 240,
            overflowY: 'auto',
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
  // No PlanGate: the index is built on every plan, so the totals are real on
  // every plan and the content locks its own file list (spec 2026-09-21,
  // section 1). The mode is the only gate left here.
  return (
    <IndexModeGate mode={indexMode}>
      <ArchiveChangesTabContent {...props} />
    </IndexModeGate>
  )
}

import { useEffect, useState } from 'react'
import {
  Alert,
  Box,
  Chip,
  DialogContent,
  DialogTitle,
  InputAdornment,
  List,
  ListItemButton,
  Skeleton,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material'
import SearchIcon from '@mui/icons-material/Search'
import { useTranslation } from 'react-i18next'
import { useQuery } from '@tanstack/react-query'
import ResponsiveDialog from '../shared/ResponsiveDialog'
import SearchBox from '../shared/SearchBox'
import PlanGate from '../shared/PlanGate'
import FileTypeIcon from '../FileTypeIcon'
import FileHistoryPanel from './FileHistoryPanel'
import { splitPath } from './pathParts'
import { usePlan } from '../../hooks/usePlan'
import { archivesAPI } from '../../services/api'
import { parseBackendDate } from '../../utils/dateUtils'
import type { SearchResult } from '../../types/archives'

interface ArchiveSearchFieldProps {
  repositoryId: number
  /** The newest archive id of each series, keyed by series name. "Present in
   *  latest" is derived here rather than served (Appendix B), and a result's
   *  `last_seen_archive_id` belongs to its own series: a repository whose
   *  series run at different times would otherwise report every file outside
   *  the last series to run as gone. */
  newestArchiveIdBySeries: Record<string, number>
  /** Restore one version of a file the search found. The wizard and the
   *  restore mutation live on the page, so the dialog hands over the archive
   *  that holds the version and the path, already selected. */
  onRestorePath: (archiveId: number, path: string) => void
}

const LIST_WIDTH = 380
// Long enough that typing a word does not fire a query per keystroke, short
// enough that the list keeps up with a correction.
const DEBOUNCE_MS = 300

function ResultRow({
  result,
  present,
  selected,
  onSelect,
}: {
  result: SearchResult
  present: boolean
  selected: boolean
  onSelect: () => void
}) {
  const { t } = useTranslation()
  const { dir, name } = splitPath(result.path)

  return (
    <ListItemButton
      selected={selected}
      onClick={onSelect}
      data-testid={`search-result-${result.path}`}
      sx={{ alignItems: 'flex-start', gap: 1.25, py: 1.25 }}
    >
      <Box sx={{ pt: 0.25, flexShrink: 0 }}>
        <FileTypeIcon name={name} type="file" size={18} />
      </Box>
      <Box sx={{ minWidth: 0, flex: 1 }}>
        <Typography variant="body2" noWrap sx={{ fontWeight: 600 }}>
          {name}
        </Typography>
        <Tooltip title={result.path} enterDelay={700} placement="top-start">
          {/* The deepest folders identify the file, so the directory is cut at
              the front: "local/Users/…/Documents/taxes/" beats a row that
              ellipsises away everything after "local/Users/kar…". */}
          <Typography
            variant="caption"
            noWrap
            sx={{
              display: 'block',
              direction: 'rtl',
              textAlign: 'left',
              color: 'text.secondary',
              fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
            }}
          >
            {dir.replace(/\/$/, '')}
          </Typography>
        </Tooltip>
        <Typography variant="caption" sx={{ color: 'text.secondary', display: 'block' }}>
          {t('archives.search.lastSeen', {
            date: parseBackendDate(result.last_seen).toLocaleDateString(),
          })}
          {' · '}
          {t('archives.search.inArchives', { count: result.archive_count })}
        </Typography>
      </Box>
      <Chip
        size="small"
        variant="outlined"
        color={present ? 'success' : 'default'}
        label={present ? t('archives.search.present') : t('archives.search.absent')}
        sx={{ flexShrink: 0, mt: 0.25 }}
      />
    </ListItemButton>
  )
}

export default function ArchiveSearchField({
  repositoryId,
  newestArchiveIdBySeries,
  onRestorePath,
}: ArchiveSearchFieldProps) {
  const { t } = useTranslation()
  const { can } = usePlan()
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState(false)
  // What the dialog's own field holds, and the debounced value behind it that
  // the query actually runs on, so refining a search never closes the dialog.
  const [refined, setRefined] = useState('')
  const [term, setTerm] = useState('')
  const [selectedPath, setSelectedPath] = useState<string | null>(null)
  const disabled = !can('archive_history')

  useEffect(() => {
    const id = setTimeout(() => setTerm(refined.trim()), DEBOUNCE_MS)
    return () => clearTimeout(id)
  }, [refined])

  const { data, isFetching } = useQuery({
    queryKey: ['archive-search', repositoryId, term],
    queryFn: () => archivesAPI.search(repositoryId, term).then((res) => res.data),
    enabled: open && term.length > 0,
  })

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault()
    if (disabled || !query.trim()) return
    setRefined(query.trim())
    setTerm(query.trim())
    setSelectedPath(null)
    setOpen(true)
  }

  const results = data?.results ?? []
  const isPresent = (result: SearchResult) =>
    result.last_seen_archive_id === newestArchiveIdBySeries[result.series]

  return (
    <PlanGate feature="archive_history" disabled surface="archives" operation="search">
      <Box component="form" role="search" onSubmit={handleSubmit}>
        <SearchBox
          value={query}
          onChange={setQuery}
          placeholder={t('archives.search.placeholder')}
          disabled={disabled}
        />
      </Box>
      <ResponsiveDialog
        open={open}
        onClose={() => setOpen(false)}
        maxWidth="lg"
        fullWidth
        PaperProps={{ sx: { height: '80vh' } }}
        mobilePaperSx={{ height: '90vh' }}
      >
        <DialogTitle sx={{ pb: 1.5 }}>{t('archives.search.title')}</DialogTitle>
        <DialogContent
          dividers
          sx={{ p: 0, display: 'flex', flexDirection: 'column', overflow: 'hidden', minHeight: 0 }}
        >
          <Box sx={{ px: 2.5, py: 1.5, borderBottom: 1, borderColor: 'divider' }}>
            <TextField
              size="small"
              fullWidth
              autoFocus
              value={refined}
              onChange={(e) => {
                setRefined(e.target.value)
                // The detail pane follows the list: a refined search can drop
                // the selected path, and a stale one could still start a
                // restore.
                setSelectedPath(null)
              }}
              placeholder={t('archives.search.placeholder')}
              slotProps={{
                input: {
                  startAdornment: (
                    <InputAdornment position="start">
                      <SearchIcon fontSize="small" />
                    </InputAdornment>
                  ),
                },
              }}
            />
          </Box>
          <Box
            sx={{
              flex: 1,
              minHeight: 0,
              display: 'flex',
              flexDirection: { xs: 'column', md: 'row' },
            }}
          >
            <Box
              // The colour belongs inside the responsive shorthand: a
              // `borderColor` alongside it loses to the media query MUI emits
              // for `borderRight`, and the pane gets a currentColor rule.
              sx={(theme) => ({
                width: { xs: '100%', md: LIST_WIDTH },
                flexShrink: 0,
                borderRight: { md: `1px solid ${theme.palette.divider}` },
                borderBottom: { xs: `1px solid ${theme.palette.divider}`, md: 'none' },
                overflowY: 'auto',
              })}
            >
              {data?.truncated && (
                <Alert severity="info" square sx={{ borderRadius: 0 }}>
                  {t('archives.search.truncated', { count: results.length })}
                </Alert>
              )}
              {isFetching && results.length === 0 && (
                <Box sx={{ px: 2, py: 1.5 }}>
                  {[0, 1, 2, 3].map((row) => (
                    <Skeleton key={row} height={44} />
                  ))}
                </Box>
              )}
              {(term.length === 0 || (!isFetching && results.length === 0)) && (
                <Typography variant="body2" sx={{ color: 'text.secondary', px: 2.5, py: 2 }}>
                  {term.length === 0
                    ? t('archives.search.typeToSearch')
                    : t('archives.search.empty')}
                </Typography>
              )}
              <List disablePadding>
                {results.map((result) => (
                  <ResultRow
                    key={result.path}
                    result={result}
                    present={isPresent(result)}
                    selected={result.path === selectedPath}
                    onSelect={() => setSelectedPath(result.path)}
                  />
                ))}
              </List>
            </Box>
            <Box sx={{ flex: 1, minWidth: 0, overflowY: 'auto', px: 2.5, py: 2 }}>
              {selectedPath ? (
                <>
                  <Typography
                    variant="body2"
                    sx={{
                      fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
                      wordBreak: 'break-all',
                      mb: 1.5,
                    }}
                  >
                    {selectedPath}
                  </Typography>
                  <FileHistoryPanel
                    repositoryId={repositoryId}
                    path={selectedPath}
                    // Straight into the restore wizard with this path
                    // selected: sending the reader to the archive page would
                    // land them at its root with the file nowhere in sight.
                    onRestoreEntry={(entry) => {
                      setOpen(false)
                      onRestorePath(entry.archive_id, selectedPath)
                    }}
                  />
                </>
              ) : (
                <Typography variant="body2" sx={{ color: 'text.secondary' }}>
                  {t('archives.search.selectPrompt')}
                </Typography>
              )}
            </Box>
          </Box>
        </DialogContent>
      </ResponsiveDialog>
    </PlanGate>
  )
}

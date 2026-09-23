import { type ReactElement, useCallback, useEffect, useRef, useState } from 'react'
import useFillViewport from '../../hooks/useFillViewport'
import { createPortal } from 'react-dom'
import {
  Box,
  Button,
  IconButton,
  Stack,
  Tooltip,
  Typography,
  useMediaQuery,
  useTheme,
} from '@mui/material'
import { CheckSquare, ChevronDown, ChevronUp, RotateCcw, X } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import ArchivePathSelector, {
  type ArchiveBrowseState,
  type ArchiveItem,
  type ArchivePathSelectionData,
} from '../ArchivePathSelector'
import ArchiveFileDetailsPane from './ArchiveFileDetailsPane'
import ResponsiveDialog from '../shared/ResponsiveDialog'
import { downloadArchiveFile, downloadArchiveFolder } from '../../utils/downloadArchiveFile'
import { formatBytes } from '../../utils/dateUtils'
import { getBorgVersion } from '../../utils/repoCapabilities'
import type { ArchiveDetailResponse } from '../../types/archives'
import type { RestorePathMetadata } from '../../utils/restorePaths'
import {
  cornerPanelFooterSx,
  cornerPanelHeaderSx,
  cornerPanelIconButtonSx,
  cornerPanelIconSx,
  cornerPanelSx,
  cornerStackSx,
} from './cornerStack'
import FileTypeIcon from '../FileTypeIcon'
import type { Repository } from '@/types'

interface ArchiveFilesTabProps {
  repositoryId: number
  repository: Repository
  archive: ArchiveDetailResponse
  /** `fromArchiveId` names the archive to restore from when it is not the
   *  one on screen: "Restore this" in file history points at an older
   *  version, and restoring the current one instead would hand back the
   *  wrong bytes without saying so (spec 10.4). */
  onRestorePaths?: (paths: string[], items: RestorePathMetadata[], fromArchiveId?: number) => void
  /** The page's bottom-right column. The selection bar renders into it so it
   *  stacks under restore progress instead of covering it. Without one the
   *  bar pins itself to the corner, which is what stories and tests see. */
  cornerStack?: HTMLElement | null
  /** Bump to drop the selection, as when a restore has gone out. Only the
   *  selection resets: the folder, filter and cursor stay where they were. */
  selectionResetToken?: number
}

// Without a column from the page, the tab floats its own.
const renderInCorner = (stack: HTMLElement | null | undefined, node: ReactElement) =>
  stack ? createPortal(node, stack) : <Box sx={cornerStackSx}>{node}</Box>

export default function ArchiveFilesTab({
  repositoryId,
  repository,
  archive,
  onRestorePaths,
  cornerStack,
  selectionResetToken = 0,
}: ArchiveFilesTabProps) {
  const { t } = useTranslation()
  const theme = useTheme()
  const isMobile = useMediaQuery(theme.breakpoints.down('md'))
  const [selection, setSelection] = useState<ArchivePathSelectionData>({
    selectedPaths: [],
    selectedItems: [],
  })
  const [lastClicked, setLastClicked] = useState<ArchiveItem | null>(null)
  const [detailsOpenMobile, setDetailsOpenMobile] = useState(false)
  const [browseState, setBrowseState] = useState<ArchiveBrowseState | null>(null)
  const [activeIndex, setActiveIndex] = useState(0)
  // The cursor outline is a keyboard affordance. It stays hidden until an
  // arrow key moves it and goes away again as soon as the mouse takes over,
  // so a mouse user never sees the first row outlined for no reason.
  const [cursorVisible, setCursorVisible] = useState(false)
  // Every item the browser has listed, by path. The selection callback only
  // carries paths and types, so this is where a selected file's size and
  // name come from once the user has moved to another folder.
  const seenItems = useRef(new Map<string, ArchiveItem>())
  // The subset of seen items that is currently selected, kept in state so
  // the footer total and restore metadata render from it.
  const [selectedEntries, setSelectedEntries] = useState<Map<string, ArchiveItem>>(new Map())

  const handleBrowseStateChange = useCallback((state: ArchiveBrowseState) => {
    for (const item of state.items) seenItems.current.set(item.path, item)
    setBrowseState(state)
    // A new listing (folder change, filter typed) shortens the rows under
    // the cursor, so pull it back inside them.
    setActiveIndex((current) => Math.min(current, Math.max(state.items.length - 1, 0)))
  }, [])

  const handleSelectionChange = (partial: Partial<ArchivePathSelectionData>) => {
    const nextPaths = partial.selectedPaths ?? selection.selectedPaths
    const addedPath = nextPaths.find((p) => !selection.selectedPaths.includes(p))
    if (addedPath) {
      const meta = (partial.selectedItems ?? []).find((item) => item.path === addedPath)
      const seen = seenItems.current.get(addedPath)
      setLastClicked(
        seen ?? {
          name: addedPath.split('/').pop() ?? addedPath,
          type: meta?.type ?? 'file',
          path: addedPath,
        }
      )
      if (isMobile) setDetailsOpenMobile(true)
    }
    const known = seenItems.current
    setSelectedEntries(
      new Map(
        nextPaths.flatMap((path) => {
          const item = known.get(path)
          return item ? [[path, item] as const] : []
        })
      )
    )
    setSelection((prev) => ({ ...prev, ...partial }))
  }

  const selectedCount = selection.selectedPaths.length
  const selectedSize = selection.selectedPaths.reduce(
    (sum, path) => sum + (selectedEntries.get(path)?.size ?? 0),
    0
  )
  const selectedItems: RestorePathMetadata[] =
    selection.selectedItems ??
    selection.selectedPaths.map((path) => ({
      path,
      type: selectedEntries.get(path)?.type ?? 'file',
    }))

  const archiveRef = getBorgVersion(repository) === 2 ? `aid:${archive.borg_id}` : archive.name

  const restoreSelection = () => onRestorePaths?.(selection.selectedPaths, selectedItems)
  const clearSelection = () => {
    setSelection({ selectedPaths: [], selectedItems: [] })
    setSelectedEntries(new Map())
  }
  const removeFromSelection = (path: string) => {
    setSelection((prev) => ({
      selectedPaths: prev.selectedPaths.filter((p) => p !== path),
      selectedItems: (prev.selectedItems ?? []).filter((item) => item.path !== path),
    }))
  }
  const [selectionOpen, setSelectionOpen] = useState(false)
  useEffect(() => {
    if (selectionResetToken === 0) return
    setSelection({ selectedPaths: [], selectedItems: [] })
    setSelectedEntries(new Map())
    setSelectionOpen(false)
  }, [selectionResetToken])

  const isTypingTarget = (target: EventTarget | null) => {
    const el = target as HTMLElement | null
    return !!el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA')
  }

  const handleKeyDown = (event: React.KeyboardEvent) => {
    if (isTypingTarget(event.target)) return
    if (!browseState) return
    const { items, currentPath, navigateTo, activateItem } = browseState

    if (event.key === 'ArrowDown') {
      event.preventDefault()
      setCursorVisible(true)
      setActiveIndex((i) => Math.min(i + 1, Math.max(items.length - 1, 0)))
    } else if (event.key === 'ArrowUp') {
      event.preventDefault()
      setCursorVisible(true)
      setActiveIndex((i) => Math.max(i - 1, 0))
    } else if (event.key === 'Enter') {
      const item = items[activeIndex]
      if (item) {
        activateItem(item)
        if (item.type === 'directory') setActiveIndex(0)
      }
    } else if (event.key === '/') {
      event.preventDefault()
      browseState.focusFilter()
    } else if (event.key === 'Backspace') {
      event.preventDefault()
      const parts = currentPath.split('/').filter(Boolean)
      parts.pop()
      navigateTo(parts.join('/'))
      setActiveIndex(0)
    } else if (event.key === 'r' && selectedCount > 0) {
      restoreSelection()
    }
  }

  const detailsPane = (
    <ArchiveFileDetailsPane
      repositoryId={repositoryId}
      indexMode={repository.index_mode ?? 'full'}
      selectedPath={lastClicked?.path ?? null}
      selectedEntry={lastClicked}
      onRestore={(entry) =>
        lastClicked &&
        onRestorePaths?.(
          [lastClicked.path],
          [{ path: lastClicked.path, type: lastClicked.type }],
          entry.archive_id
        )
      }
      onDownload={() =>
        lastClicked && downloadArchiveFile(repository, archiveRef, lastClicked.path)
      }
      onDownloadFolder={() =>
        lastClicked && downloadArchiveFolder(repository, archiveRef, lastClicked.path)
      }
    />
  )

  // Both panes run from their own top edge to the bottom of the window,
  // whatever folder is open, so browsing never moves the page; the list
  // and the details scroll inside.
  const gridRef = useRef<HTMLDivElement>(null)
  const paneHeight = useFillViewport(gridRef, 360)

  const panelSx = {
    border: 1,
    borderColor: 'divider',
    borderRadius: 2,
    bgcolor: 'background.paper',
    overflow: 'hidden',
    height: { xs: 'auto', md: paneHeight ?? 640 },
    display: 'flex',
    flexDirection: 'column',
  } as const

  return (
    <Box onKeyDown={handleKeyDown} onMouseDownCapture={() => setCursorVisible(false)}>
      <Box
        ref={gridRef}
        sx={{
          display: 'grid',
          gridTemplateColumns: { xs: '1fr', md: 'minmax(0, 3fr) minmax(300px, 2fr)' },
          gap: 3,
          alignItems: 'start',
        }}
      >
        <Box sx={panelSx}>
          <ArchivePathSelector
            variant="embedded"
            repository={repository}
            archive={{ id: archive.borg_id, name: archive.name }}
            data={selection}
            onChange={handleSelectionChange}
            onBrowseStateChange={handleBrowseStateChange}
            activeIndex={cursorVisible ? activeIndex : undefined}
          />
        </Box>
        {!isMobile && <Box sx={{ ...panelSx, overflowY: 'auto' }}>{detailsPane}</Box>}
      </Box>

      {isMobile && (
        <ResponsiveDialog open={detailsOpenMobile} onClose={() => setDetailsOpenMobile(false)}>
          <Box>{detailsPane}</Box>
        </ResponsiveDialog>
      )}

      {selectedCount > 0 &&
        // Anchored bottom right like a Drive upload panel, so picking a file
        // never shifts the panels and the action stays in reach while a long
        // folder scrolls. Expanding it lists every path that will be restored.
        renderInCorner(
          cornerStack,
          <Box role="toolbar" aria-label={t('archives.files.selectionBar')} sx={cornerPanelSx}>
            <Box sx={cornerPanelHeaderSx}>
              <Box sx={cornerPanelIconSx(theme, 'primary')} aria-hidden>
                <CheckSquare size={17} />
              </Box>
              <Box sx={{ flex: 1, minWidth: 0 }}>
                <Typography
                  variant="body2"
                  noWrap
                  sx={{ fontWeight: 600, lineHeight: 1.3, fontVariantNumeric: 'tabular-nums' }}
                >
                  {t('archives.files.selectedCount', { count: selectedCount })}
                </Typography>
                <Typography
                  variant="caption"
                  noWrap
                  component="div"
                  sx={{ color: 'text.secondary', fontVariantNumeric: 'tabular-nums' }}
                >
                  {formatBytes(selectedSize)}
                </Typography>
              </Box>
              <Tooltip
                title={
                  selectionOpen
                    ? t('archives.files.hideSelected')
                    : t('archives.files.showSelected')
                }
              >
                <IconButton
                  size="small"
                  aria-label={
                    selectionOpen
                      ? t('archives.files.hideSelected')
                      : t('archives.files.showSelected')
                  }
                  aria-expanded={selectionOpen}
                  onClick={() => setSelectionOpen((open) => !open)}
                  sx={cornerPanelIconButtonSx}
                >
                  {selectionOpen ? <ChevronDown size={16} /> : <ChevronUp size={16} />}
                </IconButton>
              </Tooltip>
              <Tooltip title={t('archives.files.clearSelection')}>
                <IconButton
                  size="small"
                  aria-label={t('archives.files.clearSelection')}
                  onClick={clearSelection}
                  sx={cornerPanelIconButtonSx}
                >
                  <X size={16} />
                </IconButton>
              </Tooltip>
            </Box>
            {selectionOpen && (
              <Box
                component="ul"
                sx={{
                  listStyle: 'none',
                  m: 0,
                  p: 0,
                  maxHeight: 260,
                  overflowY: 'auto',
                }}
              >
                {selection.selectedPaths.map((path) => {
                  const entry = selectedEntries.get(path)
                  const name = entry?.name ?? path.split('/').filter(Boolean).pop() ?? path
                  return (
                    <Stack
                      component="li"
                      key={path}
                      direction="row"
                      spacing={1.25}
                      sx={{
                        alignItems: 'center',
                        pl: 1.5,
                        pr: 0.75,
                        py: 0.75,
                        '&:hover': { bgcolor: 'action.hover' },
                      }}
                    >
                      <FileTypeIcon name={name} type={entry?.type ?? 'file'} size={28} />
                      <Box sx={{ minWidth: 0, flex: 1 }}>
                        <Typography variant="body2" noWrap sx={{ fontWeight: 500 }}>
                          {name}
                        </Typography>
                        <Typography
                          variant="caption"
                          noWrap
                          component="div"
                          sx={{ color: 'text.secondary', fontFamily: 'monospace' }}
                        >
                          {path}
                        </Typography>
                      </Box>
                      {entry?.size != null && (
                        <Typography
                          variant="caption"
                          sx={{
                            color: 'text.secondary',
                            whiteSpace: 'nowrap',
                            fontVariantNumeric: 'tabular-nums',
                          }}
                        >
                          {formatBytes(entry.size)}
                        </Typography>
                      )}
                      <IconButton
                        size="small"
                        aria-label={t('archives.files.removeFromSelection', { name })}
                        onClick={() => removeFromSelection(path)}
                        sx={cornerPanelIconButtonSx}
                      >
                        <X size={14} />
                      </IconButton>
                    </Stack>
                  )
                })}
              </Box>
            )}
            <Box sx={cornerPanelFooterSx}>
              <Button
                size="small"
                variant="contained"
                disableElevation
                startIcon={<RotateCcw size={14} />}
                onClick={restoreSelection}
                sx={{ whiteSpace: 'nowrap' }}
              >
                {t('archives.files.restoreSelection')}
              </Button>
            </Box>
          </Box>
        )}
    </Box>
  )
}

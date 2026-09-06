import { useCallback, useRef, useState } from 'react'
import {
  Box,
  Button,
  IconButton,
  Stack,
  Tooltip,
  Typography,
  alpha,
  useMediaQuery,
  useTheme,
} from '@mui/material'
import { CheckSquare, ChevronDown, ChevronUp, File, Folder, RotateCcw, X } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import ArchivePathSelector, {
  type ArchiveBrowseState,
  type ArchiveItem,
  type ArchivePathSelectionData,
} from '../ArchivePathSelector'
import ArchiveFileDetailsPane from './ArchiveFileDetailsPane'
import ResponsiveDialog from '../shared/ResponsiveDialog'
import { downloadArchiveFile } from '../../utils/downloadArchiveFile'
import { formatBytes } from '../../utils/dateUtils'
import { getBorgVersion } from '../../utils/repoCapabilities'
import type { ArchiveDetailResponse } from '../../types/archives'
import type { RestorePathMetadata } from '../../utils/restorePaths'
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
}

export default function ArchiveFilesTab({
  repositoryId,
  repository,
  archive,
  onRestorePaths,
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
    />
  )

  const panelSx = {
    border: 1,
    borderColor: 'divider',
    borderRadius: 2,
    bgcolor: 'background.paper',
    overflow: 'hidden',
  } as const

  return (
    <Box onKeyDown={handleKeyDown} onMouseDownCapture={() => setCursorVisible(false)}>
      <Box
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
        {!isMobile && <Box sx={{ ...panelSx, position: 'sticky', top: 16 }}>{detailsPane}</Box>}
      </Box>

      {isMobile && (
        <ResponsiveDialog open={detailsOpenMobile} onClose={() => setDetailsOpenMobile(false)}>
          <Box>{detailsPane}</Box>
        </ResponsiveDialog>
      )}

      {selectedCount > 0 && (
        // Anchored bottom right like a Drive upload panel, so picking a file
        // never shifts the panels and the action stays in reach while a long
        // folder scrolls. Expanding it lists every path that will be restored.
        <Box
          role="toolbar"
          aria-label={t('archives.files.selectionBar')}
          sx={{
            position: 'fixed',
            right: { xs: 12, sm: 24 },
            bottom: { xs: 12, sm: 24 },
            left: { xs: 12, sm: 'auto' },
            width: { sm: 380 },
            maxWidth: 'calc(100vw - 24px)',
            zIndex: (theme) => theme.zIndex.appBar,
            borderRadius: 3,
            overflow: 'hidden',
            color: 'common.white',
            bgcolor: (theme) =>
              theme.palette.mode === 'dark' ? theme.palette.grey[800] : theme.palette.grey[900],
            boxShadow: (theme) =>
              `0 12px 32px ${alpha(theme.palette.common.black, 0.28)}, 0 0 0 1px ${alpha(theme.palette.common.white, 0.08)}`,
            '@keyframes selection-bar-in': {
              from: { opacity: 0, transform: 'translateY(12px)' },
              to: { opacity: 1, transform: 'translateY(0)' },
            },
            animation: 'selection-bar-in 180ms ease-out',
          }}
        >
          <Stack direction="row" spacing={1} sx={{ alignItems: 'center', pl: 2, pr: 1, py: 1 }}>
            <CheckSquare size={16} aria-hidden />
            <Typography
              variant="body2"
              sx={{
                fontWeight: 600,
                flex: 1,
                minWidth: 0,
                whiteSpace: 'nowrap',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                fontVariantNumeric: 'tabular-nums',
              }}
            >
              {t('archives.files.selected', {
                count: selectedCount,
                size: formatBytes(selectedSize),
              })}
            </Typography>
            <Tooltip
              title={
                selectionOpen ? t('archives.files.hideSelected') : t('archives.files.showSelected')
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
                sx={{ color: 'inherit', opacity: 0.8, '&:hover': { opacity: 1 } }}
              >
                {selectionOpen ? <ChevronDown size={16} /> : <ChevronUp size={16} />}
              </IconButton>
            </Tooltip>
            <Tooltip title={t('archives.files.clearSelection')}>
              <IconButton
                size="small"
                aria-label={t('archives.files.clearSelection')}
                onClick={clearSelection}
                sx={{ color: 'inherit', opacity: 0.8, '&:hover': { opacity: 1 } }}
              >
                <X size={16} />
              </IconButton>
            </Tooltip>
          </Stack>
          {selectionOpen && (
            <Box
              component="ul"
              sx={{
                listStyle: 'none',
                m: 0,
                p: 0,
                maxHeight: 260,
                overflowY: 'auto',
                borderTop: (theme) => `1px solid ${alpha(theme.palette.common.white, 0.1)}`,
              }}
            >
              {selection.selectedPaths.map((path) => {
                const entry = selectedEntries.get(path)
                const name = entry?.name ?? path.split('/').filter(Boolean).pop() ?? path
                const Icon = entry?.type === 'directory' ? Folder : File
                return (
                  <Stack
                    component="li"
                    key={path}
                    direction="row"
                    spacing={1.25}
                    sx={{
                      alignItems: 'center',
                      pl: 2,
                      pr: 0.75,
                      py: 0.75,
                      '&:hover': { bgcolor: (theme) => alpha(theme.palette.common.white, 0.06) },
                    }}
                  >
                    <Box sx={{ opacity: 0.7, display: 'flex' }}>
                      <Icon size={14} />
                    </Box>
                    <Box sx={{ minWidth: 0, flex: 1 }}>
                      <Typography
                        variant="body2"
                        sx={{
                          fontWeight: 500,
                          whiteSpace: 'nowrap',
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                        }}
                      >
                        {name}
                      </Typography>
                      <Typography
                        variant="caption"
                        sx={{
                          display: 'block',
                          opacity: 0.65,
                          whiteSpace: 'nowrap',
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          fontFamily: 'monospace',
                        }}
                      >
                        {path}
                      </Typography>
                    </Box>
                    {entry?.size != null && (
                      <Typography
                        variant="caption"
                        sx={{
                          opacity: 0.75,
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
                      sx={{ color: 'inherit', opacity: 0.7, '&:hover': { opacity: 1 } }}
                    >
                      <X size={14} />
                    </IconButton>
                  </Stack>
                )
              })}
            </Box>
          )}
          <Box
            sx={{
              px: 1.5,
              py: 1,
              borderTop: (theme) => `1px solid ${alpha(theme.palette.common.white, 0.1)}`,
              display: 'flex',
              justifyContent: 'flex-end',
            }}
          >
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

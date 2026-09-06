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
import { CheckSquare, RotateCcw, X } from 'lucide-react'
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
        // Floats over the page instead of sitting under the list, so picking
        // a file never shifts the panels and the action stays in reach while
        // a long folder scrolls. Offset past the sidebar so it centres on
        // the content, not the window.
        <Box
          sx={{
            position: 'fixed',
            left: { xs: 0, sm: 240 },
            right: 0,
            bottom: { xs: 12, sm: 24 },
            display: 'flex',
            justifyContent: 'center',
            px: 2,
            pointerEvents: 'none',
            zIndex: (theme) => theme.zIndex.appBar,
          }}
        >
          <Stack
            role="toolbar"
            aria-label={t('archives.files.selectionBar')}
            direction="row"
            spacing={1.5}
            sx={{
              pointerEvents: 'auto',
              alignItems: 'center',
              pl: 2,
              pr: 1,
              py: 1,
              borderRadius: 999,
              maxWidth: '100%',
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
            <CheckSquare size={16} aria-hidden />
            <Typography
              variant="body2"
              sx={{ fontWeight: 600, whiteSpace: 'nowrap', fontVariantNumeric: 'tabular-nums' }}
            >
              {t('archives.files.selected', {
                count: selectedCount,
                size: formatBytes(selectedSize),
              })}
            </Typography>
            <Button
              size="small"
              variant="contained"
              disableElevation
              startIcon={<RotateCcw size={14} />}
              onClick={restoreSelection}
              sx={{ borderRadius: 999, whiteSpace: 'nowrap', ml: 0.5 }}
            >
              {t('archives.files.restoreSelection')}
            </Button>
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
        </Box>
      )}
    </Box>
  )
}

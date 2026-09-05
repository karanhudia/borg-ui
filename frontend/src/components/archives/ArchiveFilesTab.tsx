import { useCallback, useRef, useState } from 'react'
import { Box, Button, Stack, Typography, alpha, useMediaQuery, useTheme } from '@mui/material'
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
  onRestorePaths?: (paths: string[], items: RestorePathMetadata[]) => void
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
      setActiveIndex((i) => Math.min(i + 1, Math.max(items.length - 1, 0)))
    } else if (event.key === 'ArrowUp') {
      event.preventDefault()
      setActiveIndex((i) => Math.max(i - 1, 0))
    } else if (event.key === 'Enter') {
      const item = items[activeIndex]
      if (item) {
        activateItem(item)
        if (item.type === 'directory') setActiveIndex(0)
      }
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
      onRestore={() =>
        lastClicked &&
        onRestorePaths?.([lastClicked.path], [{ path: lastClicked.path, type: lastClicked.type }])
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
    <Box onKeyDown={handleKeyDown}>
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
        <Stack
          direction="row"
          spacing={2}
          sx={{
            mt: 3,
            px: 2.5,
            py: 1.5,
            alignItems: 'center',
            justifyContent: 'space-between',
            borderRadius: 2,
            border: 1,
            borderColor: (theme) => alpha(theme.palette.primary.main, 0.3),
            bgcolor: (theme) => alpha(theme.palette.primary.main, 0.06),
          }}
        >
          <Typography variant="body2" sx={{ fontWeight: 600 }}>
            {t('archives.files.selected', {
              count: selectedCount,
              size: formatBytes(selectedSize),
            })}
          </Typography>
          <Button variant="contained" disableElevation onClick={restoreSelection}>
            {t('archives.files.restoreSelection')}
          </Button>
        </Stack>
      )}
    </Box>
  )
}

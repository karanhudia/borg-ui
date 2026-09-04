import { useState } from 'react'
import { Box, Button, Stack, Typography, useMediaQuery, useTheme } from '@mui/material'
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
import type { Repository } from '@/types'

interface ArchiveFilesTabProps {
  repositoryId: number
  repository: Repository
  archive: ArchiveDetailResponse
  onRestorePaths?: (paths: string[]) => void
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

  const handleSelectionChange = (partial: Partial<ArchivePathSelectionData>) => {
    const nextPaths = partial.selectedPaths ?? selection.selectedPaths
    const addedPath = nextPaths.find((p) => !selection.selectedPaths.includes(p))
    if (addedPath) {
      const meta = (partial.selectedItems ?? []).find((item) => item.path === addedPath)
      setLastClicked({
        name: addedPath.split('/').pop() ?? addedPath,
        type: meta?.type ?? 'file',
        path: addedPath,
      })
      if (isMobile) setDetailsOpenMobile(true)
    }
    setSelection((prev) => ({ ...prev, ...partial }))
  }

  const selectedCount = selection.selectedPaths.length

  const archiveRef = getBorgVersion(repository) === 2 ? `aid:${archive.borg_id}` : archive.name

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
      onRestorePaths?.(selection.selectedPaths)
    }
  }

  const detailsPane = (
    <ArchiveFileDetailsPane
      repositoryId={repositoryId}
      selectedPath={lastClicked?.path ?? null}
      selectedEntry={lastClicked}
      onRestore={() => onRestorePaths?.(lastClicked ? [lastClicked.path] : selection.selectedPaths)}
      onDownload={() =>
        lastClicked && downloadArchiveFile(repository, archiveRef, lastClicked.path)
      }
    />
  )

  return (
    <Box onKeyDown={handleKeyDown}>
      <Box sx={{ display: 'flex', gap: 3, flexDirection: { xs: 'column', md: 'row' } }}>
        <Box sx={{ flex: '1 1 60%' }}>
          <ArchivePathSelector
            repository={repository}
            archive={{ id: archive.borg_id, name: archive.name }}
            data={selection}
            onChange={handleSelectionChange}
            onBrowseStateChange={setBrowseState}
          />
        </Box>
        {!isMobile && <Box sx={{ flex: '1 1 40%' }}>{detailsPane}</Box>}
      </Box>

      {isMobile && (
        <ResponsiveDialog open={detailsOpenMobile} onClose={() => setDetailsOpenMobile(false)}>
          {detailsPane}
        </ResponsiveDialog>
      )}

      {selectedCount > 0 && (
        <Stack
          direction="row"
          spacing={2}
          sx={{
            mt: 2,
            p: 2,
            alignItems: 'center',
            borderTop: 1,
            borderColor: 'divider',
          }}
        >
          <Typography variant="body2">
            {t('archives.files.selected', { count: selectedCount, size: formatBytes(0) })}
          </Typography>
          <Button
            variant="contained"
            size="small"
            onClick={() => onRestorePaths?.(selection.selectedPaths)}
          >
            {t('archives.files.restoreSelection')}
          </Button>
        </Stack>
      )}
    </Box>
  )
}

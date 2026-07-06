import { useEffect, useMemo, useState } from 'react'
import { alpha, Box, Typography } from '@mui/material'
import { ShieldCheck } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useQuery } from '@tanstack/react-query'
import { BorgApiClient, type Repository } from '../services/borgApi/client'
import { Archive } from '../types'
import { formatDateCompact, formatBytes as formatBytesUtil } from '../utils/dateUtils'
import { normalizeBrowserPath } from '../utils/storageBrowserPaths'
import StorageBrowserDialog, { type StorageBrowserItem } from './StorageBrowserDialog'

interface ArchiveContentsDialogProps {
  open: boolean
  archive: Archive | null
  repository: Repository | null
  onClose: () => void
  onDownloadFile?: (
    archiveName: string,
    filePath: string,
    size?: number | null
  ) => void | Promise<void>
}

interface RawFileItem {
  name: string
  path: string
  size?: number | null
  type: string
  mtime?: string
  managed?: boolean
  managed_type?: string
}

const RESTORE_CANARY_MANAGED_TYPE = 'restore_canary'

function isRestoreCanaryPath(path?: string) {
  const normalized = normalizeBrowserPath(path)
  return normalized === '.borg-ui' || normalized.startsWith('.borg-ui/')
}

function isRestoreCanaryItem(item: Pick<RawFileItem, 'path' | 'managed_type'>) {
  return item.managed_type === RESTORE_CANARY_MANAGED_TYPE || isRestoreCanaryPath(item.path)
}

export default function ArchiveContentsDialog({
  open,
  archive,
  repository,
  onClose,
  onDownloadFile,
}: ArchiveContentsDialogProps) {
  const { t } = useTranslation()
  const [currentPath, setCurrentPath] = useState('')
  const [downloading, setDownloading] = useState(false)

  useEffect(() => {
    if (open && archive) {
      setCurrentPath('')
    }
  }, [open, archive])

  const { data: archiveContents, isFetching } = useQuery({
    queryKey: ['archive-contents', repository?.id, archive?.name, currentPath],
    queryFn: async () => {
      if (!repository || !archive) {
        throw new Error('Repository or archive not selected')
      }
      return new BorgApiClient(repository).getArchiveContents(archive.id, archive.name, currentPath)
    },
    enabled: !!archive && !!repository && open,
    staleTime: 5 * 60 * 1000,
  })

  const canaryDescription = t('archiveContents.managedCanaryDescription')
  const items = useMemo<StorageBrowserItem[] | null>(() => {
    if (!archiveContents?.data?.items) return null

    return (archiveContents.data.items as RawFileItem[]).map((item) => {
      const managedCanary = isRestoreCanaryItem(item)
      return {
        name: item.name,
        path: normalizeBrowserPath(item.path),
        size: item.size,
        modified: item.mtime,
        downloadPath: item.path,
        type: item.type === 'directory' ? 'directory' : 'file',
        badgeLabel: managedCanary ? t('archiveContents.managedCanaryLabel') : undefined,
        tooltip: managedCanary ? canaryDescription : undefined,
        tone: managedCanary ? 'info' : undefined,
      }
    })
  }, [archiveContents?.data?.items, canaryDescription, t])

  const isInsideCanaryPath = isRestoreCanaryPath(currentPath)

  return (
    <StorageBrowserDialog
      open={open}
      title={t('archiveContents.title')}
      subtitle={archive?.name}
      currentPath={currentPath}
      items={items}
      isLoading={isFetching}
      rootLabel={t('archiveContents.root')}
      closeLabel={t('common.buttons.close')}
      emptyDirectoryLabel={t('archiveContents.emptyDirectory')}
      emptyRootTitle={t('archiveContents.emptyArchive')}
      emptyRootDescription={t('archiveContents.emptyArchiveDesc')}
      noInfoLabel={t('archiveContents.noInfo')}
      showModifiedColumn
      banner={
        isInsideCanaryPath ? (
          <Box
            sx={{
              display: 'flex',
              alignItems: 'flex-start',
              gap: 1,
              px: 1.5,
              py: 1,
              borderRadius: 1,
              bgcolor: (theme) => alpha(theme.palette.info.main, 0.08),
              border: '1px solid',
              borderColor: (theme) => alpha(theme.palette.info.main, 0.25),
              flexShrink: 0,
            }}
          >
            <ShieldCheck size={17} style={{ marginTop: 2, flexShrink: 0 }} />
            <Typography variant="body2" color="text.secondary">
              {t('archiveContents.managedCanaryBanner')}
            </Typography>
          </Box>
        ) : null
      }
      onClose={onClose}
      onNavigate={(path) => setCurrentPath(normalizeBrowserPath(path))}
      onDownloadFile={
        onDownloadFile && archive
          ? async (filePath, size) => {
              setDownloading(true)
              try {
                await onDownloadFile(archive.name, filePath, size)
              } catch {
                // downloadArchiveFile surfaces its own errors; this guard just
                // prevents an unhandled rejection if a handler throws.
              } finally {
                setDownloading(false)
              }
            }
          : undefined
      }
      downloadBusy={downloading}
      downloadLabel={t('archiveContents.downloadFile')}
      formatSize={formatBytesUtil}
      formatModified={formatDateCompact}
    />
  )
}

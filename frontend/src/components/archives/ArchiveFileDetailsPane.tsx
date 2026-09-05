import { Box, Button, Stack, Typography } from '@mui/material'
import { Download, File, Folder } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { formatBytes } from '../../utils/dateUtils'
import FileHistoryPanel from './FileHistoryPanel'
import type { ArchiveItem } from '../ArchivePathSelector'
import type { HistoryEntry } from '../../types/archives'

interface ArchiveFileDetailsPaneProps {
  repositoryId: number
  selectedPath: string | null
  selectedEntry: ArchiveItem | null
  // Restoring the current selection belongs to the Files tab footer. This
  // callback only serves "Restore this" on a specific history entry.
  onRestore: (entry: HistoryEntry) => void
  onDownload: () => void
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <Box sx={{ display: 'grid', gridTemplateColumns: '64px minmax(0, 1fr)', columnGap: 1.5 }}>
      <Typography variant="body2" sx={{ color: 'text.secondary' }}>
        {label}
      </Typography>
      <Typography variant="body2" sx={{ wordBreak: 'break-all' }}>
        {value}
      </Typography>
    </Box>
  )
}

export default function ArchiveFileDetailsPane({
  repositoryId,
  selectedPath,
  selectedEntry,
  onRestore,
  onDownload,
}: ArchiveFileDetailsPaneProps) {
  const { t } = useTranslation()

  if (!selectedPath || !selectedEntry) {
    return (
      <Box sx={{ py: 1 }}>
        <Typography variant="subtitle2">{t('archives.files.folderMetadata')}</Typography>
        <Typography variant="body2" sx={{ color: 'text.secondary', mt: 0.5 }}>
          {t('archives.files.noSelection')}
        </Typography>
      </Box>
    )
  }

  const isFile = selectedEntry.type === 'file'
  const Icon = isFile ? File : Folder

  return (
    <Box>
      <Stack direction="row" spacing={1.5} sx={{ alignItems: 'flex-start', mb: 2 }}>
        <Box
          sx={{
            width: 36,
            height: 36,
            borderRadius: 1.5,
            bgcolor: 'action.hover',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            flexShrink: 0,
            color: 'text.secondary',
          }}
        >
          <Icon size={18} />
        </Box>
        <Box sx={{ minWidth: 0, flex: 1 }}>
          <Typography
            variant="subtitle1"
            sx={{ fontWeight: 600, wordBreak: 'break-all', lineHeight: 1.35 }}
          >
            {selectedEntry.name}
          </Typography>
          <Typography variant="caption" sx={{ color: 'text.secondary' }}>
            {isFile ? t('archives.files.typeFile') : t('archives.files.typeDirectory')}
            {isFile && selectedEntry.size != null ? ` · ${formatBytes(selectedEntry.size)}` : ''}
          </Typography>
        </Box>
      </Stack>
      <Stack spacing={0.75} sx={{ mb: 2 }}>
        <Field label={t('archives.files.path')} value={selectedPath} />
      </Stack>
      {isFile && (
        <Button
          variant="outlined"
          size="small"
          startIcon={<Download size={14} />}
          onClick={onDownload}
          sx={{ mb: 3 }}
        >
          {t('archives.files.download')}
        </Button>
      )}
      <Typography variant="subtitle2" sx={{ mb: 1 }}>
        {t('archives.files.history')}
      </Typography>
      <FileHistoryPanel
        repositoryId={repositoryId}
        path={selectedPath}
        onRestoreEntry={onRestore}
      />
    </Box>
  )
}

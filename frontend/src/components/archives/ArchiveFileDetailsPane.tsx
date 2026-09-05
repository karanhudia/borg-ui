import { Box, Button, Divider, Stack, Typography } from '@mui/material'
import { Download } from 'lucide-react'
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
    <Box sx={{ display: 'flex', gap: 1.5, minWidth: 0 }}>
      <Typography variant="body2" sx={{ color: 'text.secondary', flexShrink: 0, width: 48 }}>
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

  return (
    <Box>
      <Stack
        direction="row"
        spacing={1}
        sx={{ alignItems: 'flex-start', justifyContent: 'space-between', mb: 1.5 }}
      >
        <Typography variant="subtitle1" sx={{ fontWeight: 600, wordBreak: 'break-all' }}>
          {selectedEntry.name}
        </Typography>
        {isFile && (
          <Button
            variant="outlined"
            size="small"
            startIcon={<Download size={14} />}
            onClick={onDownload}
            sx={{ flexShrink: 0 }}
          >
            {t('archives.files.download')}
          </Button>
        )}
      </Stack>
      <Stack spacing={0.5} sx={{ mb: 2 }}>
        <Field label={t('archives.files.path')} value={selectedPath} />
        {isFile && selectedEntry.size != null && (
          <Field label={t('archives.files.size')} value={formatBytes(selectedEntry.size)} />
        )}
      </Stack>
      <Divider sx={{ mb: 2 }} />
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

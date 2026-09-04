import { Box, Button, Divider, Stack, Typography } from '@mui/material'
import { useTranslation } from 'react-i18next'
import { formatBytes } from '../../utils/dateUtils'
import FileHistoryPanel from './FileHistoryPanel'
import type { ArchiveItem } from '../ArchivePathSelector'
import type { HistoryEntry } from '../../types/archives'

interface ArchiveFileDetailsPaneProps {
  repositoryId: number
  selectedPath: string | null
  selectedEntry: ArchiveItem | null
  onRestore: (entry?: HistoryEntry) => void
  onDownload: () => void
}

export default function ArchiveFileDetailsPane({
  repositoryId,
  selectedPath,
  selectedEntry,
  onRestore,
  onDownload,
}: ArchiveFileDetailsPaneProps) {
  const { t } = useTranslation()

  return (
    <Box>
      {!selectedPath || !selectedEntry ? (
        <Typography variant="subtitle2">{t('archives.files.folderMetadata')}</Typography>
      ) : (
        <>
          <Typography variant="subtitle1">{selectedEntry.name}</Typography>
          <Stack spacing={0.5} sx={{ mt: 1, mb: 2 }}>
            {selectedEntry.type === 'file' && (
              <Typography variant="body2" color="text.secondary">
                {t('archives.files.size')}: {formatBytes(selectedEntry.size)}
              </Typography>
            )}
          </Stack>
          <Stack direction="row" spacing={1} sx={{ mb: 2 }}>
            <Button variant="outlined" size="small" onClick={() => onRestore()}>
              {t('archives.files.restore')}
            </Button>
            <Button variant="outlined" size="small" onClick={onDownload}>
              {t('archives.files.download')}
            </Button>
          </Stack>
          <Divider sx={{ mb: 2 }} />
          <Typography variant="subtitle2" sx={{ mb: 1 }}>
            {t('archives.files.history')}
          </Typography>
          <FileHistoryPanel
            repositoryId={repositoryId}
            path={selectedPath}
            onRestoreEntry={(entry) => onRestore(entry)}
          />
        </>
      )}
    </Box>
  )
}

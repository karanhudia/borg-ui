import { Box, Button, Stack, Typography, alpha, useTheme } from '@mui/material'
import { Download, MousePointerClick } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { formatBytes } from '../../utils/dateUtils'
import FileTypeIcon from '../FileTypeIcon'
import FileHistoryPanel from './FileHistoryPanel'
import IndexModeGate from './IndexModeGate'
import { usePlan } from '../../hooks/usePlan'
import type { ArchiveItem } from '../ArchivePathSelector'
import type { HistoryEntry } from '../../types/archives'
import type { IndexMode } from '../../types/operations'

interface ArchiveFileDetailsPaneProps {
  repositoryId: number
  // The repository's index mode (spec 6.8). Defaulted so a caller that
  // predates the mode reads as the behaviour every install had.
  indexMode?: IndexMode
  selectedPath: string | null
  selectedEntry: ArchiveItem | null
  // Restoring the current selection belongs to the Files tab footer. This
  // callback only serves "Restore this" on a specific history entry, and the
  // entry says which archive that version lives in.
  onRestore: (entry: HistoryEntry) => void
  onDownload: () => void
}

function SectionTitle({ children }: { children: string }) {
  return (
    <Typography
      variant="caption"
      sx={{ display: 'block', fontWeight: 600, color: 'text.secondary', mb: 1 }}
    >
      {children}
    </Typography>
  )
}

export default function ArchiveFileDetailsPane({
  repositoryId,
  indexMode = 'full',
  selectedPath,
  selectedEntry,
  onRestore,
  onDownload,
}: ArchiveFileDetailsPaneProps) {
  const { t } = useTranslation()
  const theme = useTheme()
  const { can } = usePlan()

  if (!selectedPath || !selectedEntry) {
    return (
      <Box
        sx={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          textAlign: 'center',
          minHeight: 260,
          p: 3,
          color: 'text.secondary',
        }}
      >
        <Box
          sx={{
            width: 44,
            height: 44,
            borderRadius: '12px',
            bgcolor: alpha(theme.palette.primary.main, 0.08),
            color: 'primary.main',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            mb: 1.5,
          }}
        >
          <MousePointerClick size={22} />
        </Box>
        <Typography variant="subtitle2" sx={{ color: 'text.primary' }}>
          {t('archives.files.folderMetadata')}
        </Typography>
        <Typography variant="body2" sx={{ mt: 0.5, maxWidth: 260 }}>
          {t('archives.files.noSelection')}
        </Typography>
      </Box>
    )
  }

  const historyPanel = (
    <FileHistoryPanel repositoryId={repositoryId} path={selectedPath} onRestoreEntry={onRestore} />
  )
  const isFile = selectedEntry.type === 'file'

  return (
    <Box>
      <Box
        sx={{
          display: 'flex',
          gap: 1.5,
          alignItems: 'flex-start',
          px: 2.5,
          py: 2,
          borderBottom: 1,
          borderColor: 'divider',
          bgcolor: alpha(theme.palette.text.primary, 0.025),
          borderTopLeftRadius: 'inherit',
          borderTopRightRadius: 'inherit',
        }}
      >
        <FileTypeIcon name={selectedEntry.name} type={selectedEntry.type} size={40} />
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
      </Box>

      <Box sx={{ px: 2.5, py: 2 }}>
        <SectionTitle>{t('archives.files.path')}</SectionTitle>
        <Typography
          variant="body2"
          sx={{
            wordBreak: 'break-all',
            fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
            fontSize: '0.8rem',
            px: 1.25,
            py: 1,
            borderRadius: 1.5,
            bgcolor: alpha(theme.palette.text.primary, 0.04),
          }}
        >
          {selectedPath}
        </Typography>
        {isFile && (
          <Stack direction="row" spacing={1} sx={{ mt: 2 }}>
            <Button
              variant="outlined"
              size="small"
              startIcon={<Download size={14} />}
              onClick={onDownload}
            >
              {t('archives.files.download')}
            </Button>
          </Stack>
        )}
      </Box>

      <Box sx={{ px: 2.5, pb: 2, pt: 1, borderTop: 1, borderColor: 'divider' }}>
        <SectionTitle>{t('archives.files.history')}</SectionTitle>
        {/* Plan first, then mode (spec 6.8). FileHistoryPanel carries its
            own PlanGate, so gating it from the outside would answer a
            Community user with the mode instead of the upsell. */}
        {can('archive_history') ? (
          <IndexModeGate mode={indexMode}>{historyPanel}</IndexModeGate>
        ) : (
          historyPanel
        )}
      </Box>
    </Box>
  )
}

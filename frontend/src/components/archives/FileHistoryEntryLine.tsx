import { Box, Button, Typography, useTheme } from '@mui/material'
import { RotateCcw } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import ChangeBadge from './ChangeBadge'
import { changeColor } from './changeStyle'
import { formatBytes, parseBackendDate } from '../../utils/dateUtils'
import type { HistoryEntry } from '../../types/archives'

interface FileHistoryEntryLineProps {
  entry: HistoryEntry
  /** The oldest `added` entry: the version the path first appeared in. */
  isFirst: boolean
  onRestore: (entry: HistoryEntry) => void
}

/** One version of a path in the history panel, and in its locked preview. */
export default function FileHistoryEntryLine({
  entry,
  isFirst,
  onRestore,
}: FileHistoryEntryLineProps) {
  const { t } = useTranslation()
  const theme = useTheme()
  const change = isFirst ? 'added' : entry.change === 'summary' ? 'modified' : entry.change
  const detail = isFirst
    ? t('archives.files.firstSeen')
    : entry.change === 'modified'
      ? `${formatBytes(entry.size_before)} → ${formatBytes(entry.size_after)}`
      : t(`archives.changes.${entry.change === 'summary' ? 'modified' : entry.change}`)
  return (
    <Box
      sx={{
        display: 'grid',
        gridTemplateColumns: '20px minmax(0, 1fr) auto',
        columnGap: 1.5,
        alignItems: 'start',
        py: 1.25,
        borderTop: 1,
        borderColor: 'divider',
        '&:first-of-type': { borderTop: 0 },
      }}
    >
      <Box sx={{ pt: 0.25 }}>
        <ChangeBadge change={change} size={18} />
      </Box>
      <Box sx={{ minWidth: 0 }}>
        <Typography variant="body2" noWrap title={entry.archive_name} sx={{ fontWeight: 600 }}>
          {entry.archive_name}
        </Typography>
        <Typography variant="caption" sx={{ color: 'text.secondary', display: 'block' }}>
          {parseBackendDate(entry.start).toLocaleString()}
          <Box component="span" sx={{ color: changeColor(theme, change), ml: 1, fontWeight: 600 }}>
            {detail}
          </Box>
        </Typography>
      </Box>
      <Button
        size="small"
        startIcon={<RotateCcw size={13} />}
        onClick={() => onRestore(entry)}
        sx={{ mt: -0.5, flexShrink: 0 }}
      >
        {t('archives.files.restoreThis')}
      </Button>
    </Box>
  )
}

import { Box, IconButton, Tooltip, Chip, useTheme, alpha } from '@mui/material'
import { Eye, RotateCcw, HardDrive, Trash2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { formatDate } from '../utils/dateUtils'
import { Archive } from '../types'
import { getArchiveType } from '../utils/archiveGrouping'

interface ArchiveCardProps {
  archive: Archive
  onView: (archive: Archive) => void
  onRestore: (archive: Archive) => void
  onMount: (archive: Archive) => void
  onDelete: (archiveName: string) => void
  mountDisabled?: boolean
  canDelete?: boolean
}

export default function ArchiveCard({
  archive,
  onView,
  onRestore,
  onMount,
  onDelete,
  mountDisabled = false,
  canDelete = true,
}: ArchiveCardProps) {
  const { t } = useTranslation()
  const theme = useTheme()
  const isDark = theme.palette.mode === 'dark'
  const isManual = getArchiveType(archive) === 'manual'
  const archiveTime = archive.start || archive.time

  const iconBtnSx = (color: string) => ({
    width: 28,
    height: 28,
    borderRadius: 1.5,
    color: alpha(color, isDark ? 0.6 : 0.5),
    '&:hover': {
      bgcolor: alpha(color, isDark ? 0.12 : 0.09),
      color: color,
    },
    '&.Mui-disabled': { opacity: 0.28 },
  })

  return (
    <Box
      sx={{
        display: 'grid',
        gridTemplateColumns: '1fr 64px 120px auto',
        alignItems: 'center',
        gap: 1,
        px: 2,
        py: 1.125,
        borderBottom: '1px solid',
        borderBottomColor: isDark ? alpha('#fff', 0.04) : alpha('#000', 0.04),
        borderLeft: '2px solid transparent',
        transition: 'all 150ms ease',
        '&:hover': {
          bgcolor: alpha(theme.palette.primary.main, isDark ? 0.04 : 0.03),
          borderLeftColor: theme.palette.primary.main,
        },
        '@media (max-width: 767px)': {
          display: 'flex',
          flexWrap: 'wrap',
          gap: 0.75,
          px: 1.75,
          py: 1.25,
        },
      }}
    >
      {/* Archive name */}
      <Box
        title={archive.name}
        sx={{
          fontFamily: '"JetBrains Mono","Fira Code",ui-monospace,monospace',
          fontSize: '0.78rem',
          fontWeight: 600,
          color: 'text.primary',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
          minWidth: 0,
          '@media (max-width: 767px)': {
            width: '100%',
            order: 1,
          },
        }}
      >
        {archive.name}
      </Box>

      {/* Type chip */}
      <Box sx={{ '@media (max-width: 767px)': { order: 2 } }}>
        <Chip
          label={isManual ? t('archivesList.manualAbbr', 'MAN') : t('archivesList.scheduledAbbr', 'SCH')}
          size="small"
          sx={{
            height: 18,
            fontSize: '0.6rem',
            fontWeight: 700,
            letterSpacing: '0.05em',
            textTransform: 'uppercase',
            bgcolor: isManual
              ? alpha(theme.palette.primary.main, isDark ? 0.18 : 0.1)
              : alpha(theme.palette.success.main, isDark ? 0.18 : 0.1),
            color: isManual ? 'primary.main' : 'success.main',
            border: '1px solid',
            borderColor: isManual
              ? alpha(theme.palette.primary.main, isDark ? 0.3 : 0.2)
              : alpha(theme.palette.success.main, isDark ? 0.3 : 0.2),
            '& .MuiChip-label': { px: 0.75 },
          }}
        />
      </Box>

      {/* Date */}
      <Box
        sx={{
          fontSize: '0.72rem',
          color: 'text.secondary',
          whiteSpace: 'nowrap',
          '@media (max-width: 767px)': {
            order: 3,
            flex: 1,
          },
        }}
      >
        {formatDate(archiveTime)}
      </Box>

      {/* Actions — always visible */}
      <Box
        sx={{
          display: 'flex',
          gap: 0.25,
          justifyContent: 'flex-end',
          '@media (max-width: 767px)': {
            order: 4,
            ml: 'auto',
          },
        }}
      >
        <Tooltip title={t('archiveCard.viewContents')} arrow>
          <IconButton
            size="small"
            onClick={() => onView(archive)}
            aria-label={t('archiveCard.viewContents')}
            sx={iconBtnSx(theme.palette.primary.main)}
          >
            <Eye size={15} />
          </IconButton>
        </Tooltip>

        <Tooltip title={t('archiveCard.restore')} arrow>
          <IconButton
            size="small"
            onClick={() => onRestore(archive)}
            aria-label={t('archiveCard.restore')}
            sx={iconBtnSx(theme.palette.warning.main)}
          >
            <RotateCcw size={15} />
          </IconButton>
        </Tooltip>

        <Tooltip title={t('archiveCard.mount')} arrow>
          <span>
            <IconButton
              size="small"
              onClick={() => onMount(archive)}
              disabled={mountDisabled}
              aria-label={t('archiveCard.mount')}
              sx={iconBtnSx(theme.palette.info.main)}
            >
              <HardDrive size={15} />
            </IconButton>
          </span>
        </Tooltip>

        {canDelete && (
          <Tooltip title={t('archiveCard.delete')} arrow>
            <IconButton
              size="small"
              onClick={() => onDelete(archive.name)}
              aria-label={t('archiveCard.delete')}
              sx={iconBtnSx(theme.palette.error.main)}
            >
              <Trash2 size={15} />
            </IconButton>
          </Tooltip>
        )}
      </Box>
    </Box>
  )
}

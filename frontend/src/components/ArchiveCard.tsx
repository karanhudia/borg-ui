import { Box, Typography, Button, IconButton, Tooltip, Chip, useTheme, alpha } from '@mui/material'
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

  const iconBtnSx = {
    width: 32,
    height: 32,
    borderRadius: 1.5,
    color: 'text.secondary',
    '&:hover': {
      bgcolor: isDark ? alpha('#fff', 0.07) : alpha('#000', 0.06),
      color: 'text.primary',
    },
    '&.Mui-disabled': { opacity: 0.28 },
  }

  const coloredIconBtnSx = (colorKey: 'primary' | 'success' | 'secondary' | 'warning' | 'info') => {
    const color = (theme.palette[colorKey] as { main: string }).main
    return {
      ...iconBtnSx,
      color: alpha(color, isDark ? 0.65 : 0.55),
      '&:hover': {
        bgcolor: alpha(color, isDark ? 0.12 : 0.09),
        color: color,
      },
      '&.Mui-disabled': { opacity: 0.28 },
    }
  }

  return (
    <Box
      sx={{
        position: 'relative',
        borderRadius: 2,
        bgcolor: 'background.paper',
        overflow: 'hidden',
        boxShadow: isDark
          ? `0 0 0 1px ${alpha('#fff', 0.08)}, 0 4px 16px ${alpha('#000', 0.25)}`
          : `0 0 0 1px ${alpha('#000', 0.08)}, 0 2px 8px ${alpha('#000', 0.07)}`,
        transition: 'all 200ms cubic-bezier(0.16,1,0.3,1)',
        '&:hover': {
          transform: 'translateY(-2px)',
          boxShadow: isDark
            ? `0 0 0 1px ${alpha(theme.palette.primary.main, 0.4)}, 0 8px 24px ${alpha('#000', 0.3)}, 0 2px 8px ${alpha(theme.palette.primary.main, 0.1)}`
            : `0 0 0 1px ${alpha(theme.palette.primary.main, 0.3)}, 0 8px 24px ${alpha('#000', 0.12)}, 0 2px 8px ${alpha(theme.palette.primary.main, 0.08)}`,
        },
      }}
    >
      <Box sx={{ px: { xs: 1.75, sm: 2 }, pt: { xs: 1.75, sm: 2 }, pb: { xs: 1.5, sm: 1.75 } }}>
        {/* ── Header ── */}
        <Box
          sx={{
            display: 'flex',
            alignItems: 'center',
            gap: 1,
            mb: 1.5,
          }}
        >
          {/* Name */}
          <Typography
            title={archive.name}
            sx={{
              fontFamily: '"JetBrains Mono","Fira Code",ui-monospace,monospace',
              fontSize: '0.78rem',
              fontWeight: 600,
              color: 'text.primary',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
              flex: 1,
              minWidth: 0,
            }}
          >
            {archive.name}
          </Typography>

          {/* Right-aligned: type chip + date */}
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75, flexShrink: 0 }}>
            <Chip
              label={isManual ? t('archivesList.manual') : t('archivesList.scheduled')}
              size="small"
              sx={{
                height: 18,
                fontSize: '0.62rem',
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
            <Typography
              sx={{
                fontSize: '0.68rem',
                color: 'text.disabled',
                lineHeight: 1,
                whiteSpace: 'nowrap',
              }}
            >
              {formatDate(archiveTime)}
            </Typography>
          </Box>
        </Box>

        {/* ── Action Bar ── */}
        <Box
          sx={{
            display: 'flex',
            alignItems: 'center',
            gap: 0.5,
            pt: 1.25,
            borderTop: '1px solid',
            borderColor: isDark ? alpha('#fff', 0.06) : alpha('#000', 0.07),
          }}
        >
          {/* Left: secondary icon actions */}
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.25, flex: 1 }}>
            <Tooltip title={t('archiveCard.restore')} arrow>
              <IconButton
                size="small"
                onClick={() => onRestore(archive)}
                aria-label={t('archiveCard.restore')}
                sx={coloredIconBtnSx('warning')}
              >
                <RotateCcw size={16} />
              </IconButton>
            </Tooltip>

            <Tooltip title={t('archiveCard.mount')} arrow>
              <span>
                <IconButton
                  size="small"
                  onClick={() => onMount(archive)}
                  disabled={mountDisabled}
                  aria-label={t('archiveCard.mount')}
                  sx={coloredIconBtnSx('info')}
                >
                  <HardDrive size={16} />
                </IconButton>
              </span>
            </Tooltip>

            {canDelete && (
              <>
                <Box
                  sx={{
                    width: '1px',
                    height: 18,
                    bgcolor: isDark ? alpha('#fff', 0.1) : alpha('#000', 0.1),
                    mx: 0.25,
                    flexShrink: 0,
                  }}
                />
                <Tooltip title={t('archiveCard.delete')} arrow>
                  <IconButton
                    size="small"
                    onClick={() => onDelete(archive.name)}
                    aria-label={t('archiveCard.delete')}
                    sx={{
                      ...iconBtnSx,
                      color: alpha(theme.palette.error.main, 0.6),
                      '&:hover': {
                        color: theme.palette.error.main,
                        bgcolor: alpha(theme.palette.error.main, 0.1),
                      },
                    }}
                  >
                    <Trash2 size={16} />
                  </IconButton>
                </Tooltip>
              </>
            )}
          </Box>

          {/* Right: primary action */}
          <Button
            variant="contained"
            size="small"
            startIcon={<Eye size={13} />}
            onClick={() => onView(archive)}
            sx={{
              textTransform: 'none',
              fontWeight: 600,
              fontSize: '0.78rem',
              height: 30,
              flexShrink: 0,
              borderRadius: 1.5,
              px: 1.5,
              boxShadow: `0 2px 8px ${alpha(theme.palette.primary.main, 0.3)}`,
              '&:hover': {
                boxShadow: `0 4px 14px ${alpha(theme.palette.primary.main, 0.45)}`,
              },
            }}
          >
            {t('common.buttons.view')}
          </Button>
        </Box>
      </Box>
    </Box>
  )
}

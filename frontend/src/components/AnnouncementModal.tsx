import {
  Box,
  Button,
  Chip,
  Dialog,
  IconButton,
  Link,
  Stack,
  useTheme,
  Typography,
} from '@mui/material'
import { alpha } from '@mui/material/styles'
import {
  BellRing,
  ChevronRight,
  ExternalLink,
  ShieldAlert,
  Sparkles,
  Wrench,
  X,
} from 'lucide-react'
import { useTranslation } from 'react-i18next'
import type { Announcement } from '../types/announcements'

interface AnnouncementModalProps {
  announcement: Announcement | null
  open: boolean
  onAcknowledge: () => void
  onSnooze: () => void
  onCtaClick?: () => void
}

function getAnnouncementTone(type: Announcement['type']) {
  switch (type) {
    case 'security_notice':
    case 'migration_notice':
      return 'warning'
    case 'maintenance_notice':
      return 'info'
    default:
      return 'success'
  }
}

function getAnnouncementIcon(type: Announcement['type']) {
  switch (type) {
    case 'security_notice':
    case 'migration_notice':
      return <ShieldAlert size={20} />
    case 'maintenance_notice':
      return <Wrench size={20} />
    default:
      return <BellRing size={20} />
  }
}

export default function AnnouncementModal({
  announcement,
  open,
  onAcknowledge,
  onSnooze,
  onCtaClick,
}: AnnouncementModalProps) {
  const { t } = useTranslation()
  const theme = useTheme()

  if (!announcement) return null

  const isDark = theme.palette.mode === 'dark'
  const tone = getAnnouncementTone(announcement.type)
  const icon = getAnnouncementIcon(announcement.type)
  const accentColor =
    tone === 'warning'
      ? theme.palette.warning.main
      : tone === 'info'
        ? theme.palette.info.main
        : theme.palette.primary.main
  const panelBackground = isDark ? '#18181b' : '#ffffff'
  const foreground = isDark ? '#ffffff' : '#1f2937'
  const mutedText = isDark ? alpha('#ffffff', 0.76) : alpha('#1f2937', 0.82)
  const secondaryText = isDark ? alpha('#ffffff', 0.58) : alpha('#1f2937', 0.5)
  const borderAlpha = isDark ? alpha('#ffffff', 0.08) : alpha('#000000', 0.1)
  const subtleBg = isDark ? alpha('#ffffff', 0.12) : alpha('#000000', 0.06)
  const subtleBorder = isDark ? alpha('#ffffff', 0.12) : alpha('#000000', 0.08)
  const highlightBg = isDark ? alpha('#000000', 0.24) : alpha('#000000', 0.03)
  const glintTop = isDark ? alpha('#ffffff', 0.08) : alpha('#ffffff', 0.6)
  const hoverBg = isDark ? alpha('#ffffff', 0.08) : alpha('#000000', 0.06)

  return (
    <Dialog
      open={open}
      maxWidth="sm"
      fullWidth
      PaperProps={{
        sx: {
          overflow: 'hidden',
          borderRadius: 3,
          color: foreground,
          background: panelBackground,
          border: `1px solid ${borderAlpha}`,
          boxShadow: isDark
            ? `0 28px 80px ${alpha('#000000', 0.52)}`
            : `0 28px 80px ${alpha('#000000', 0.16)}`,
        },
      }}
    >
      <Box sx={{ px: { xs: 2.25, sm: 3 }, pt: 2.25, pb: 1.5 }}>
        <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 1.5 }}>
          <Box
            sx={{
              width: 44,
              height: 44,
              borderRadius: 2,
              bgcolor: alpha(accentColor, 0.18),
              color: accentColor,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              flexShrink: 0,
              border: `1px solid ${alpha(accentColor, 0.32)}`,
              boxShadow: `inset 0 1px 0 ${glintTop}`,
            }}
          >
            {icon}
          </Box>

          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap" sx={{ mb: 1.25 }}>
              <Chip
                size="small"
                icon={<Sparkles size={12} />}
                label={t(`announcements.types.${announcement.type}`)}
                sx={{
                  height: 24,
                  bgcolor: subtleBg,
                  color: foreground,
                  border: `1px solid ${subtleBorder}`,
                  '& .MuiChip-label': {
                    px: 1.2,
                    fontSize: '0.72rem',
                    fontWeight: 700,
                  },
                  '& .MuiChip-icon': {
                    color: mutedText,
                  },
                }}
              />
              {announcement.type === 'update_available' ? (
                <Chip
                  size="small"
                  label="Latest release"
                  sx={{
                    height: 24,
                    bgcolor: alpha(accentColor, 0.16),
                    color: accentColor,
                    border: `1px solid ${alpha(accentColor, 0.28)}`,
                    '& .MuiChip-label': {
                      px: 1.2,
                      fontSize: '0.72rem',
                      fontWeight: 700,
                    },
                  }}
                />
              ) : null}
            </Stack>

            <Typography
              variant="h5"
              sx={{ fontWeight: 800, lineHeight: 1.15, letterSpacing: '-0.02em', mb: 1 }}
            >
              {announcement.title}
            </Typography>

            <Typography
              variant="body1"
              sx={{ color: mutedText, lineHeight: 1.65, maxWidth: '48ch' }}
            >
              {announcement.message}
            </Typography>
          </Box>

          {announcement.dismissible !== false ? (
            <IconButton
              onClick={onAcknowledge}
              size="small"
              aria-label="Close announcement"
              sx={{
                color: secondaryText,
                border: `1px solid ${borderAlpha}`,
                bgcolor: isDark ? alpha('#ffffff', 0.03) : alpha('#000000', 0.02),
                '&:hover': {
                  color: foreground,
                  bgcolor: hoverBg,
                },
              }}
            >
              <X size={18} />
            </IconButton>
          ) : null}
        </Box>
      </Box>

      <Box sx={{ px: { xs: 2.25, sm: 3 }, pb: { xs: 2.25, sm: 3 } }}>
        {announcement.highlights?.length ? (
          <Box
            sx={{
              p: 2,
              mb: 2.25,
              borderRadius: 2.5,
              bgcolor: highlightBg,
              border: `1px solid ${alpha(accentColor, 0.18)}`,
              boxShadow: `inset 0 1px 0 ${isDark ? alpha('#ffffff', 0.04) : alpha('#ffffff', 0.5)}`,
            }}
          >
            <Typography
              variant="overline"
              sx={{
                display: 'block',
                mb: 1.1,
                color: accentColor,
                fontWeight: 800,
                letterSpacing: '0.12em',
              }}
            >
              {t('announcements.highlights')}
            </Typography>

            <Stack spacing={1}>
              {announcement.highlights.map((highlight) => (
                <Box key={highlight} sx={{ display: 'flex', gap: 1.1, alignItems: 'flex-start' }}>
                  <Box
                    sx={{
                      width: 6,
                      height: 6,
                      borderRadius: '50%',
                      mt: '0.55rem',
                      flexShrink: 0,
                      bgcolor: accentColor,
                      boxShadow: `0 0 0 4px ${alpha(accentColor, 0.14)}`,
                    }}
                  />
                  <Typography variant="body2" sx={{ color: mutedText, lineHeight: 1.6 }}>
                    {highlight}
                  </Typography>
                </Box>
              ))}
            </Stack>
          </Box>
        ) : null}

        <Stack
          direction={{ xs: 'column', sm: 'row' }}
          spacing={1.25}
          sx={{ alignItems: { xs: 'stretch', sm: 'center' }, justifyContent: 'space-between' }}
        >
          {announcement.cta_url ? (
            <Link
              href={announcement.cta_url}
              target="_blank"
              rel="noreferrer"
              onClick={onCtaClick}
              underline="none"
              sx={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 0.9,
                fontSize: '0.95rem',
                fontWeight: 700,
                color: accentColor,
                '&:hover': {
                  color: alpha(accentColor, 0.82),
                },
              }}
            >
              {announcement.cta_label || t('announcements.viewDetails')}
              <ExternalLink size={15} />
            </Link>
          ) : (
            <Box />
          )}

          <Stack direction="row" spacing={1.25} sx={{ justifyContent: 'flex-end' }}>
            <Button
              onClick={onSnooze}
              variant="outlined"
              sx={{
                color: mutedText,
                borderColor: isDark ? alpha('#ffffff', 0.16) : alpha('#000000', 0.15),
                bgcolor: isDark ? alpha('#ffffff', 0.04) : alpha('#000000', 0.03),
                '&:hover': {
                  borderColor: isDark ? alpha('#ffffff', 0.28) : alpha('#000000', 0.25),
                  bgcolor: hoverBg,
                },
              }}
            >
              {t('announcements.remindLater')}
            </Button>

            {announcement.dismissible !== false ? (
              <Button
                onClick={onAcknowledge}
                variant="contained"
                endIcon={<ChevronRight size={16} />}
                sx={{
                  bgcolor: accentColor,
                  color: theme.palette.getContrastText(accentColor),
                  '&:hover': {
                    bgcolor: alpha(accentColor, 0.88),
                  },
                }}
              >
                {t('announcements.gotIt')}
              </Button>
            ) : null}
          </Stack>
        </Stack>
      </Box>
    </Dialog>
  )
}

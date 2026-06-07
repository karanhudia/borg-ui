import { Box, Typography } from '@mui/material'
import { alpha, useTheme } from '@mui/material/styles'
import { useTranslation } from 'react-i18next'
import { useUpdateNotice, type UpdateNotice } from '../hooks/useUpdateNotice'

interface SidebarUpdateNoticeViewProps {
  notice: UpdateNotice
  onDismiss: () => void
  onCtaClick?: () => void
}

export function SidebarUpdateNoticeView({
  notice,
  onDismiss,
  onCtaClick,
}: SidebarUpdateNoticeViewProps) {
  const { t } = useTranslation()
  const muiTheme = useTheme()
  const isDark = muiTheme.palette.mode === 'dark'
  const accent = isDark ? '#60a5fa' : '#2563eb'

  return (
    <Box
      role="region"
      aria-label={t('sidebar.update.ariaLabel', 'Software update available')}
      sx={{ mb: 1 }}
    >
      {/* Eyebrow lives OUTSIDE the card so its dot column-aligns with the plan badge dot below. */}
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.625, mb: 0.625 }}>
        <Box
          sx={{
            width: 5,
            height: 5,
            borderRadius: '50%',
            bgcolor: accent,
            flexShrink: 0,
            boxShadow: `0 0 4px ${alpha(accent, 0.5)}`,
          }}
        />
        <Typography
          sx={{
            fontSize: '0.6rem',
            fontWeight: 700,
            color: accent,
            letterSpacing: '0.05em',
            textTransform: 'uppercase',
            lineHeight: 1,
            opacity: 0.95,
          }}
        >
          {t('sidebar.update.title', 'Update available')}
        </Typography>
      </Box>

      {/* Card holds the substantive content: version + actions. */}
      <Box
        sx={{
          px: 1.125,
          py: 0.875,
          borderRadius: 2,
          bgcolor: alpha(accent, isDark ? 0.09 : 0.05),
        }}
      >
        {/* Version as the hero. Wraps cleanly without orphaning a separator. */}
        {notice.version && (
          <Typography
            sx={{
              fontSize: '0.8rem',
              fontWeight: 700,
              color: accent,
              lineHeight: 1.2,
              mb: 0.75,
              wordBreak: 'break-word',
            }}
          >
            {notice.version}
          </Typography>
        )}

        {/* Action row: explicit "Dismiss" word, deliberate. */}
        <Box
          sx={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: notice.ctaUrl ? 'space-between' : 'flex-end',
            gap: 1,
          }}
        >
          {notice.ctaUrl && (
            <Typography
              component="a"
              href={notice.ctaUrl}
              target="_blank"
              rel="noopener noreferrer"
              onClick={onCtaClick}
              sx={{
                fontSize: '0.7rem',
                fontWeight: 600,
                color: accent,
                textDecoration: 'none',
                lineHeight: 1.2,
                '&:hover': { textDecoration: 'underline' },
                '&:focus-visible': {
                  outline: `2px solid ${alpha(accent, 0.55)}`,
                  outlineOffset: 2,
                  borderRadius: 4,
                },
              }}
            >
              {t('sidebar.update.releaseNotes', "See what's new")} →
            </Typography>
          )}
          <Box
            component="button"
            type="button"
            onClick={onDismiss}
            sx={{
              background: 'none',
              border: 'none',
              padding: 0,
              cursor: 'pointer',
              fontFamily: 'inherit',
              fontSize: '0.7rem',
              fontWeight: 600,
              color: muiTheme.palette.text.secondary,
              lineHeight: 1.2,
              transition: 'color 150ms ease',
              '&:hover': { color: muiTheme.palette.text.primary },
              '&:focus-visible': {
                outline: `2px solid ${alpha(muiTheme.palette.text.secondary, 0.5)}`,
                outlineOffset: 2,
                borderRadius: 4,
              },
            }}
          >
            {t('sidebar.update.dismiss', 'Dismiss')}
          </Box>
        </Box>
      </Box>
    </Box>
  )
}

export default function SidebarUpdateNotice() {
  const { notice, dismiss, trackCtaClick } = useUpdateNotice()
  if (!notice) return null
  return <SidebarUpdateNoticeView notice={notice} onDismiss={dismiss} onCtaClick={trackCtaClick} />
}

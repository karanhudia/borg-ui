import { Box, Stack, Typography, alpha, useTheme } from '@mui/material'
import {
  Calendar,
  FileText,
  HardDrive,
  Layers,
  MessageSquareQuote,
  Package,
  Server,
  Tag,
  Timer,
  User,
} from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { formatBytes, formatDurationSeconds, parseBackendDate } from '../../utils/dateUtils'
import type { ArchiveDetailResponse } from '../../types/archives'

interface ArchiveInfoTabProps {
  archive: ArchiveDetailResponse
}

type Tone = 'primary' | 'secondary' | 'success' | 'info' | 'warning'

// The same tint per figure as the chips in the page header, so the tab
// reads as the long form of the header rather than a second design.
function IconBox({ icon, tone, size = 36 }: { icon: React.ReactNode; tone: Tone; size?: number }) {
  const theme = useTheme()
  const color = theme.palette[tone].main
  return (
    <Box
      aria-hidden
      sx={{
        width: size,
        height: size,
        borderRadius: `${Math.round(size * 0.28)}px`,
        flexShrink: 0,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        color,
        bgcolor: alpha(color, theme.palette.mode === 'dark' ? 0.18 : 0.1),
      }}
    >
      {icon}
    </Box>
  )
}

function SizeTile({
  icon,
  tone,
  label,
  value,
}: {
  icon: React.ReactNode
  tone: Tone
  label: string
  value: number | null
}) {
  const { t } = useTranslation()
  const theme = useTheme()
  const color = theme.palette[tone].main
  return (
    <Stack
      direction="row"
      spacing={1.5}
      sx={{
        alignItems: 'center',
        p: 2,
        borderRadius: 2,
        border: `1px solid ${alpha(color, 0.25)}`,
        bgcolor: alpha(color, theme.palette.mode === 'dark' ? 0.08 : 0.04),
        minWidth: 0,
      }}
    >
      <IconBox icon={icon} tone={tone} />
      <Box sx={{ minWidth: 0 }}>
        <Typography variant="caption" sx={{ color: alpha(color, 0.9), fontWeight: 600 }}>
          {label}
        </Typography>
        <Typography
          variant="h6"
          sx={{ fontWeight: 700, lineHeight: 1.2, fontVariantNumeric: 'tabular-nums' }}
        >
          {value != null ? formatBytes(value) : t('common.unknown')}
        </Typography>
      </Box>
    </Stack>
  )
}

function Fact({
  icon,
  tone,
  label,
  value,
}: {
  icon: React.ReactNode
  tone: Tone
  label: string
  value: string | null
}) {
  if (!value) return null
  return (
    <Stack direction="row" spacing={1.5} sx={{ alignItems: 'center', minWidth: 0 }}>
      <IconBox icon={icon} tone={tone} size={32} />
      <Box sx={{ minWidth: 0 }}>
        <Typography variant="caption" sx={{ color: 'text.secondary', display: 'block' }}>
          {label}
        </Typography>
        <Typography
          variant="body2"
          sx={{ fontWeight: 600, wordBreak: 'break-word', fontVariantNumeric: 'tabular-nums' }}
        >
          {value}
        </Typography>
      </Box>
    </Stack>
  )
}

// What the archive cost to store, then the facts about the run. Borg's
// "deduplicated size" is the chunks no other archive has, so for a daily
// backup it is tiny and for an old archive whose data later ones share it
// is zero. That is what deleting the archive would free, which is the
// figure people actually want, so it gets a bar and a sentence.
export default function ArchiveInfoTab({ archive }: ArchiveInfoTabProps) {
  const { t } = useTranslation()
  const theme = useTheme()

  const original = archive.original_size
  const stored = archive.deduplicated_size
  const share = original != null && stored != null && original > 0 ? stored / original : null
  const percent = share != null ? Math.min(100, Math.round(share * 100)) : null
  // Rounding a small non-zero share to "0%" or "1%" would contradict the
  // size next to it; the meter keeps the rounded value.
  const percentLabel = share != null && share > 0 && share < 0.01 ? '< 1' : percent

  return (
    <Stack spacing={3}>
      <Box
        sx={{
          border: 1,
          borderColor: 'divider',
          borderRadius: 2,
          bgcolor: 'background.paper',
          p: 3,
        }}
      >
        <Typography variant="overline" sx={{ color: 'text.secondary', letterSpacing: '0.08em' }}>
          {t('archives.detail.storage')}
        </Typography>
        <Box
          sx={{
            display: 'grid',
            gridTemplateColumns: { xs: '1fr', sm: 'repeat(3, minmax(0, 1fr))' },
            gap: 2,
            mt: 1.5,
          }}
        >
          <SizeTile
            icon={<HardDrive size={18} />}
            tone="success"
            label={t('archives.detail.originalSize')}
            value={archive.original_size}
          />
          <SizeTile
            icon={<Package size={18} />}
            tone="secondary"
            label={t('archives.detail.compressedSize')}
            value={archive.compressed_size}
          />
          <SizeTile
            icon={<Layers size={18} />}
            tone="info"
            label={t('archives.detail.uniqueSize')}
            value={archive.deduplicated_size}
          />
        </Box>
        {percent != null && original != null && stored != null && (
          <Box sx={{ mt: 2.5 }}>
            <Box
              role="meter"
              aria-label={t('archives.detail.storedShareLabel')}
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={percent}
              sx={{
                height: 10,
                borderRadius: 5,
                overflow: 'hidden',
                bgcolor: alpha(theme.palette.success.main, 0.18),
              }}
            >
              <Box
                sx={{
                  width: `${Math.max(percent, 1)}%`,
                  height: '100%',
                  borderRadius: 5,
                  bgcolor: theme.palette.info.main,
                  transition: 'width 300ms ease',
                }}
              />
            </Box>
            <Typography variant="body2" sx={{ mt: 1 }}>
              {t('archives.detail.storedShare', {
                stored: formatBytes(stored),
                percent: percentLabel,
              })}{' '}
              <Typography component="span" variant="body2" sx={{ color: 'text.secondary' }}>
                {t('archives.detail.storedSaved', { size: formatBytes(stored) })}
              </Typography>
            </Typography>
          </Box>
        )}
      </Box>

      <Box
        sx={{
          border: 1,
          borderColor: 'divider',
          borderRadius: 2,
          bgcolor: 'background.paper',
          p: 3,
        }}
      >
        <Typography variant="overline" sx={{ color: 'text.secondary', letterSpacing: '0.08em' }}>
          {t('archives.detail.details')}
        </Typography>
        <Box
          sx={{
            display: 'grid',
            gridTemplateColumns: {
              xs: '1fr',
              sm: 'repeat(2, minmax(0, 1fr))',
              md: 'repeat(3, minmax(0, 1fr))',
            },
            gap: 2.5,
            mt: 1.5,
          }}
        >
          <Fact
            icon={<Tag size={15} />}
            tone="secondary"
            label={t('archives.detail.series')}
            value={archive.series}
          />
          <Fact
            icon={<Calendar size={15} />}
            tone="primary"
            label={t('archives.detail.started')}
            value={parseBackendDate(archive.start).toLocaleString()}
          />
          <Fact
            icon={<Timer size={15} />}
            tone="warning"
            label={t('archives.detail.duration')}
            value={
              archive.duration_seconds != null
                ? formatDurationSeconds(archive.duration_seconds)
                : null
            }
          />
          <Fact
            icon={<FileText size={15} />}
            tone="primary"
            label={t('archives.detail.files')}
            value={archive.nfiles?.toLocaleString() ?? null}
          />
          <Fact
            icon={<Server size={15} />}
            tone="info"
            label={t('archives.detail.hostname')}
            value={archive.hostname}
          />
          <Fact
            icon={<User size={15} />}
            tone="success"
            label={t('archives.detail.username')}
            value={archive.username}
          />
        </Box>
        {archive.comment && (
          <Stack
            direction="row"
            spacing={1.5}
            sx={{
              mt: 3,
              p: 2,
              borderRadius: 2,
              borderLeft: `3px solid ${theme.palette.secondary.main}`,
              bgcolor: alpha(
                theme.palette.secondary.main,
                theme.palette.mode === 'dark' ? 0.08 : 0.04
              ),
            }}
          >
            <Box sx={{ color: 'secondary.main', mt: 0.25 }}>
              <MessageSquareQuote size={16} />
            </Box>
            <Box sx={{ minWidth: 0 }}>
              <Typography variant="caption" sx={{ color: 'text.secondary', display: 'block' }}>
                {t('archives.detail.comment')}
              </Typography>
              <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                {archive.comment}
              </Typography>
            </Box>
          </Stack>
        )}
      </Box>
    </Stack>
  )
}

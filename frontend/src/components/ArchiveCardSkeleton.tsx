import { Box, Skeleton, alpha, useTheme } from '@mui/material'

interface ArchiveCardSkeletonProps {
  index?: number
}

export default function ArchiveCardSkeleton({ index = 0 }: ArchiveCardSkeletonProps) {
  const theme = useTheme()
  const isDark = theme.palette.mode === 'dark'

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
        opacity: 0,
        animation: 'archiveSkeletonFadeIn 0.35s ease forwards',
        animationDelay: `${index * 60}ms`,
        '@keyframes archiveSkeletonFadeIn': {
          from: { opacity: 0, transform: 'translateY(4px)' },
          to: { opacity: 1, transform: 'translateY(0)' },
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
          {/* Archive name (monospace) */}
          <Skeleton
            variant="text"
            width={[160, 200, 140, 180, 152, 190][index % 6]}
            height={18}
            sx={{ borderRadius: 0.5, transform: 'none', flexShrink: 0 }}
          />
          <Box sx={{ flex: 1 }} />

          {/* Right: type chip + date */}
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75, flexShrink: 0 }}>
            <Skeleton variant="rounded" width={60} height={18} sx={{ borderRadius: 3 }} />
            <Skeleton variant="text" width={72} height={14} sx={{ transform: 'none' }} />
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
          {/* Left: icon action placeholders */}
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.25, flex: 1 }}>
            <Skeleton variant="rounded" width={32} height={32} sx={{ borderRadius: 1.5 }} />
            <Skeleton variant="rounded" width={32} height={32} sx={{ borderRadius: 1.5 }} />
          </Box>

          {/* Right: primary View button */}
          <Skeleton variant="rounded" width={64} height={30} sx={{ borderRadius: 1.5 }} />
        </Box>
      </Box>
    </Box>
  )
}

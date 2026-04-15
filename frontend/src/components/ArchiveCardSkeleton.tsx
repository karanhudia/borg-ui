import { Box, Skeleton, alpha, useTheme } from '@mui/material'

interface ArchiveCardSkeletonProps {
  index?: number
}

export default function ArchiveCardSkeleton({ index = 0 }: ArchiveCardSkeletonProps) {
  const theme = useTheme()
  const isDark = theme.palette.mode === 'dark'
  const desktopGridTemplate = 'minmax(0, 1fr) 76px minmax(180px, 220px) 132px'

  return (
    <Box
      sx={{
        display: 'grid',
        gridTemplateColumns: desktopGridTemplate,
        alignItems: 'center',
        gap: 1,
        px: 2,
        py: 1.125,
        borderBottom: '1px solid',
        borderBottomColor: isDark ? alpha('#fff', 0.04) : alpha('#000', 0.04),
        opacity: 0,
        animation: 'archiveSkeletonFadeIn 0.35s ease forwards',
        animationDelay: `${index * 40}ms`,
        '@keyframes archiveSkeletonFadeIn': {
          from: { opacity: 0 },
          to: { opacity: 1 },
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
      <Skeleton
        variant="text"
        width={[160, 200, 140, 180, 152, 190, 170, 210, 145, 185][index % 10]}
        height={16}
        sx={{ borderRadius: 0.5, transform: 'none' }}
      />
      <Skeleton variant="rounded" width={36} height={18} sx={{ borderRadius: 3 }} />
      <Skeleton variant="text" width={90} height={14} sx={{ transform: 'none' }} />
      <Box sx={{ display: 'flex', gap: 0.25, justifyContent: 'flex-end' }}>
        <Skeleton variant="rounded" width={28} height={28} sx={{ borderRadius: 1.5 }} />
        <Skeleton variant="rounded" width={28} height={28} sx={{ borderRadius: 1.5 }} />
        <Skeleton variant="rounded" width={28} height={28} sx={{ borderRadius: 1.5 }} />
        <Skeleton variant="rounded" width={28} height={28} sx={{ borderRadius: 1.5 }} />
      </Box>
    </Box>
  )
}

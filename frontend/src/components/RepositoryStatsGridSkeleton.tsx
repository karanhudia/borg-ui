import { Box, Skeleton, alpha, useTheme } from '@mui/material'

type ColorKey = 'primary' | 'success' | 'info' | 'secondary' | 'warning'

const STAT_COLORS: ColorKey[] = ['primary', 'success', 'info', 'secondary', 'warning']

interface StatCardSkeletonProps {
  colorKey: ColorKey
  index: number
}

function StatCardSkeleton({ colorKey, index }: StatCardSkeletonProps) {
  const theme = useTheme()
  const isDark = theme.palette.mode === 'dark'
  const color = (theme.palette[colorKey] as { main: string }).main

  return (
    <Box
      sx={{
        borderRadius: 2,
        bgcolor: alpha(color, isDark ? 0.1 : 0.07),
        px: 2,
        py: 1.75,
        boxShadow: isDark
          ? `0 0 0 1px ${alpha('#fff', 0.08)}, 0 2px 8px ${alpha('#000', 0.2)}`
          : `0 0 0 1px ${alpha('#000', 0.08)}, 0 2px 6px ${alpha('#000', 0.06)}`,
        opacity: 0,
        animation: 'statsSkeletonFadeIn 0.35s ease forwards',
        animationDelay: `${index * 50}ms`,
        '@keyframes statsSkeletonFadeIn': {
          from: { opacity: 0, transform: 'translateY(4px)' },
          to: { opacity: 1, transform: 'translateY(0)' },
        },
      }}
    >
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <Box>
          {/* Label */}
          <Skeleton
            variant="text"
            width={[64, 72, 68, 76, 80][index]}
            height={10}
            sx={{ transform: 'none', mb: 1, borderRadius: 0.5 }}
          />
          {/* Value */}
          <Skeleton
            variant="text"
            width={[48, 56, 52, 44, 56][index]}
            height={28}
            sx={{ transform: 'none', borderRadius: 0.5 }}
          />
        </Box>
        {/* Icon placeholder */}
        <Skeleton
          variant="rounded"
          width={32}
          height={32}
          sx={{ borderRadius: 1, opacity: 0.5, mt: 0.25 }}
        />
      </Box>
    </Box>
  )
}

export default function RepositoryStatsGridSkeleton() {
  return (
    <Box
      sx={{
        display: 'grid',
        gridTemplateColumns: { xs: '1fr', sm: 'repeat(2, 1fr)', lg: 'repeat(5, 1fr)' },
        gap: 2,
        mb: 0,
      }}
    >
      {STAT_COLORS.map((colorKey, i) => (
        <StatCardSkeleton key={colorKey} colorKey={colorKey} index={i} />
      ))}
    </Box>
  )
}

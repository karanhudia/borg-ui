import { Box, Skeleton, alpha, useTheme } from '@mui/material'

interface RepositoryCardSkeletonProps {
  index?: number
}

const NAME_WIDTHS = [120, 148, 104, 136, 116, 152]
const PATH_WIDTHS = [200, 240, 180, 220, 196, 232]

export default function RepositoryCardSkeleton({ index = 0 }: RepositoryCardSkeletonProps) {
  const theme = useTheme()
  const isDark = theme.palette.mode === 'dark'
  const nameWidth = NAME_WIDTHS[index % NAME_WIDTHS.length]
  const pathWidth = PATH_WIDTHS[index % PATH_WIDTHS.length]

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
        animation: 'skeletonFadeIn 0.4s ease forwards',
        animationDelay: `${index * 80}ms`,
        '@keyframes skeletonFadeIn': {
          from: { opacity: 0, transform: 'translateY(6px)' },
          to: { opacity: 1, transform: 'translateY(0)' },
        },
      }}
    >
      <Box sx={{ px: { xs: 1.75, sm: 2 }, pt: { xs: 1.75, sm: 2 }, pb: { xs: 1.5, sm: 1.75 } }}>
        {/* ── Header ── */}
        <Box
          sx={{
            display: 'flex',
            alignItems: 'flex-start',
            justifyContent: 'space-between',
            gap: 1,
            mb: 1.5,
          }}
        >
          <Box sx={{ minWidth: 0, flex: 1 }}>
            {/* Name row */}
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75, mb: 0.5 }}>
              <Skeleton
                variant="text"
                width={nameWidth}
                height={22}
                sx={{ borderRadius: 0.5, transform: 'none' }}
              />
              <Skeleton
                variant="rounded"
                width={42}
                height={18}
                sx={{ borderRadius: 3, flexShrink: 0 }}
              />
            </Box>
            {/* Path */}
            <Skeleton
              variant="text"
              width={pathWidth}
              height={14}
              sx={{ borderRadius: 0.5, transform: 'none' }}
            />
          </Box>

          {/* Edit button placeholder */}
          <Skeleton
            variant="rounded"
            width={28}
            height={28}
            sx={{ borderRadius: 1, flexShrink: 0 }}
          />
        </Box>

        {/* ── Stats Band ── */}
        <Box
          sx={{
            display: 'grid',
            gridTemplateColumns: { xs: 'repeat(2, 1fr)', sm: 'repeat(4, 1fr)' },
            borderRadius: 1.5,
            border: '1px solid',
            borderColor: isDark ? alpha('#fff', 0.06) : alpha('#000', 0.07),
            overflow: 'hidden',
            mb: 1.5,
            bgcolor: isDark ? alpha('#fff', 0.025) : alpha('#000', 0.018),
          }}
        >
          {[0, 1, 2, 3].map((i) => {
            const isRightColXs = i % 2 === 1
            const isLastSm = i === 3
            const isFirstRowXs = i < 2
            return (
              <Box
                key={i}
                sx={{
                  px: 1.5,
                  py: 1.1,
                  borderRight: isLastSm ? 0 : '1px solid',
                  borderBottom: { xs: isFirstRowXs ? '1px solid' : 0, sm: 0 },
                  borderColor: isDark ? alpha('#fff', 0.06) : alpha('#000', 0.07),
                  ...(isRightColXs && {
                    borderRight: { xs: 0, sm: isLastSm ? 0 : '1px solid' },
                  }),
                }}
              >
                {/* Icon + label row */}
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mb: 0.5 }}>
                  <Skeleton
                    variant="rounded"
                    width={11}
                    height={11}
                    sx={{ borderRadius: 0.5, flexShrink: 0 }}
                  />
                  <Skeleton variant="text" width={40} height={10} sx={{ transform: 'none' }} />
                </Box>
                {/* Value */}
                <Skeleton
                  variant="text"
                  width={[36, 48, 52, 44][i]}
                  height={18}
                  sx={{ transform: 'none' }}
                />
              </Box>
            )
          })}
        </Box>

        {/* ── Secondary Metadata ── */}
        <Box
          sx={{ display: 'flex', gap: { xs: 1.25, sm: 1.75 }, flexWrap: 'wrap', mb: 1.5, px: 0.25 }}
        >
          {[56, 72, 68, 60].map((w, i) => (
            <Skeleton key={i} variant="text" width={w} height={12} sx={{ transform: 'none' }} />
          ))}
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
          {/* Left icon cluster */}
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.25, flex: 1 }}>
            {[0, 1, 2, 3, 4].map((i) => (
              <Skeleton
                key={i}
                variant="rounded"
                width={32}
                height={32}
                sx={{ borderRadius: 1.5 }}
              />
            ))}
          </Box>

          {/* Right: primary action buttons */}
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75, flexShrink: 0 }}>
            <Skeleton variant="rounded" width={72} height={32} sx={{ borderRadius: 1.5 }} />
            <Skeleton variant="rounded" width={96} height={32} sx={{ borderRadius: 1.5 }} />
          </Box>
        </Box>
      </Box>
    </Box>
  )
}

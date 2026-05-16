import { Box, Skeleton, alpha, useTheme } from '@mui/material'

interface EntityCardSkeletonProps {
  // Number of stats grid cells. Defaults to 4 to match check/restore cards.
  statCount?: number
  // 0..1, applied to the whole card so a stack of skeletons reads as hierarchy
  // (top item solid, lower items faded).
  opacity?: number
  // Approximate width of the title text bar (px). Vary across a stack to
  // avoid the "all rows identical" tell of a skeleton.
  titleWidth?: number
  // Include a meta row (timezone etc.) under the stats grid.
  showMeta?: boolean
}

// Shape-matched placeholder for cards rendered via `EntityCard`. Mirrors:
// title + top-right edit icon, stats grid, optional meta row, and the footer
// (toggle + divider + action icons + primary button). Keep in sync with
// `EntityCard.tsx` so loading → loaded swaps are a no-op visually.
export default function EntityCardSkeleton({
  statCount = 4,
  opacity = 1,
  titleWidth = 170,
  showMeta = true,
}: EntityCardSkeletonProps) {
  const theme = useTheme()
  const isDark = theme.palette.mode === 'dark'

  return (
    <Box
      sx={{
        borderRadius: 2,
        bgcolor: 'background.paper',
        overflow: 'hidden',
        boxShadow: isDark
          ? `0 0 0 1px ${alpha('#fff', 0.08)}, 0 4px 16px ${alpha('#000', 0.25)}`
          : `0 0 0 1px ${alpha('#000', 0.08)}, 0 2px 8px ${alpha('#000', 0.07)}`,
        opacity,
      }}
    >
      <Box sx={{ px: { xs: 1.75, sm: 2 }, pt: { xs: 1.75, sm: 2 }, pb: { xs: 1.5, sm: 1.75 } }}>
        {/* Title row: title + subtitle (left) and edit icon (right) */}
        <Box
          sx={{
            display: 'flex',
            alignItems: 'flex-start',
            justifyContent: 'space-between',
            gap: 1,
            mb: 1.5,
          }}
        >
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Skeleton variant="text" width={titleWidth} height={24} sx={{ transform: 'none' }} />
            <Skeleton
              variant="text"
              width={Math.round(titleWidth * 0.7)}
              height={12}
              sx={{ transform: 'none', mt: 0.5 }}
            />
          </Box>
          <Skeleton variant="rounded" width={28} height={28} sx={{ borderRadius: 1 }} />
        </Box>

        {/* Stats grid */}
        <Box
          sx={{
            display: 'grid',
            gridTemplateColumns: {
              xs: 'repeat(2, 1fr)',
              sm: `repeat(${statCount}, 1fr)`,
            },
            borderRadius: 1.5,
            border: '1px solid',
            borderColor: 'divider',
            overflow: 'hidden',
            mb: 1.5,
          }}
        >
          {Array.from({ length: statCount }).map((_, j) => (
            <Box
              key={j}
              sx={{
                px: 1.5,
                py: 1.1,
                borderRight: j < statCount - 1 ? { sm: '1px solid' } : 0,
                borderBottom: {
                  xs: j < statCount - 2 ? '1px solid' : 0,
                  sm: 0,
                },
                borderColor: 'divider',
              }}
            >
              <Skeleton
                variant="text"
                width={42}
                height={10}
                sx={{ transform: 'none', borderRadius: 0.5, mb: 0.5 }}
              />
              <Skeleton
                variant="text"
                width={[58, 48, 54, 44, 50, 46][j] ?? 50}
                height={16}
                sx={{ transform: 'none', borderRadius: 0.5 }}
              />
            </Box>
          ))}
        </Box>

        {showMeta && (
          <Box sx={{ display: 'flex', gap: 1.5, mb: 1.5, px: 0.25 }}>
            <Skeleton variant="text" width={120} height={10} sx={{ transform: 'none' }} />
          </Box>
        )}

        {/* Footer: toggle (switch + label) | divider | action icon(s) | primary CTA */}
        <Box
          sx={{
            display: 'flex',
            alignItems: 'center',
            gap: 0.5,
            pt: 1.25,
            borderTop: '1px solid',
            borderColor: 'divider',
          }}
        >
          {/* Switch + label */}
          <Skeleton variant="rounded" width={32} height={20} sx={{ borderRadius: 10 }} />
          <Skeleton variant="text" width={54} height={14} sx={{ transform: 'none', ml: 0.5 }} />

          <Box
            sx={{
              width: '1px',
              height: 18,
              bgcolor: isDark ? alpha('#fff', 0.1) : alpha('#000', 0.1),
              mx: 0.5,
              flexShrink: 0,
            }}
          />

          {/* Single action icon (delete) */}
          <Skeleton variant="rounded" width={32} height={32} sx={{ borderRadius: 1.5 }} />

          {/* Primary action (Run / Run check) — pushed to the right */}
          <Skeleton variant="rounded" width={88} height={30} sx={{ borderRadius: 1, ml: 'auto' }} />
        </Box>
      </Box>
    </Box>
  )
}

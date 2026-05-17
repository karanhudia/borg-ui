import { alpha, Box, Skeleton, Stack, useTheme } from '@mui/material'

export function BackupPlanCardSkeleton({ index = 0 }: { index?: number }) {
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
        animation: 'backupPlanSkeletonFadeIn 0.28s ease forwards',
        animationDelay: `${index * 45}ms`,
        opacity: 0,
        '@keyframes backupPlanSkeletonFadeIn': {
          from: { opacity: 0, transform: 'translateY(4px)' },
          to: { opacity: 1, transform: 'translateY(0)' },
        },
      }}
    >
      <Box sx={{ px: { xs: 1.75, sm: 2 }, pt: { xs: 1.75, sm: 2 }, pb: { xs: 1.5, sm: 1.75 } }}>
        <Stack direction="row" alignItems="center" justifyContent="space-between" spacing={1.5}>
          <Box sx={{ minWidth: 0, flex: 1 }}>
            <Skeleton variant="text" width="38%" height={26} sx={{ transform: 'none' }} />
            <Skeleton variant="text" width="52%" height={16} sx={{ mt: 0.5, transform: 'none' }} />
          </Box>
          <Stack direction="row" spacing={0.75} alignItems="center">
            <Skeleton variant="rounded" width={92} height={24} sx={{ borderRadius: 1 }} />
            <Skeleton variant="rounded" width={28} height={28} sx={{ borderRadius: 1 }} />
          </Stack>
        </Stack>

        <Box
          sx={{
            display: 'grid',
            gridTemplateColumns: { xs: 'repeat(2, 1fr)', sm: 'repeat(4, 1fr)' },
            gap: 0,
            mt: 1.5,
            borderRadius: 1.5,
            border: '1px solid',
            borderColor: isDark ? alpha('#fff', 0.06) : alpha('#000', 0.07),
            overflow: 'hidden',
          }}
        >
          {[0, 1, 2, 3].map((item) => (
            <Box
              key={item}
              sx={{
                px: 1.5,
                py: 1.1,
                borderRight: { sm: item === 3 ? 0 : '1px solid' },
                borderBottom: { xs: item < 2 ? '1px solid' : 0, sm: 0 },
                borderColor: isDark ? alpha('#fff', 0.06) : alpha('#000', 0.07),
              }}
            >
              <Skeleton variant="text" width="55%" height={12} sx={{ transform: 'none' }} />
              <Skeleton
                variant="text"
                width="72%"
                height={20}
                sx={{ mt: 0.5, transform: 'none' }}
              />
            </Box>
          ))}
        </Box>

        <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mt: 1.5 }}>
          <Stack direction="row" spacing={0.75} alignItems="center">
            <Skeleton variant="rounded" width={82} height={28} sx={{ borderRadius: 1 }} />
            <Skeleton variant="rounded" width={32} height={32} sx={{ borderRadius: 1.5 }} />
            <Skeleton variant="rounded" width={32} height={32} sx={{ borderRadius: 1.5 }} />
          </Stack>
          <Skeleton variant="rounded" width={74} height={30} sx={{ borderRadius: 1 }} />
        </Stack>
      </Box>
    </Box>
  )
}

import { Box, Skeleton, Stack } from '@mui/material'
import type { Tokens } from './tokens'

export function DashboardSkeleton({ T }: { T: Tokens }) {
  return (
    <Box sx={{ color: T.textPrimary }}>
      {/* Health banner skeleton */}
      <Box
        sx={{
          bgcolor: T.bgCard,
          border: `1px solid ${T.border}`,
          borderRadius: '14px',
          mb: 2.5,
          px: 2.5,
          py: 1.75,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: 2,
        }}
      >
        <Stack direction="row" spacing={2} alignItems="center">
          <Skeleton variant="circular" width={8} height={8} />
          <Box>
            <Skeleton
              variant="text"
              width={80}
              height={15}
              sx={{ mb: 0.2, transform: 'none', borderRadius: 0.5 }}
            />
            <Skeleton
              variant="text"
              width={120}
              height={24}
              sx={{ transform: 'none', borderRadius: 0.5 }}
            />
          </Box>
        </Stack>
        <Stack direction="row" spacing={3}>
          {[56, 70, 62, 68].map((w, i) => (
            <Box key={i}>
              <Skeleton
                variant="text"
                width={w}
                height={14}
                sx={{ mb: 0.4, transform: 'none', borderRadius: 0.5 }}
              />
              <Skeleton
                variant="text"
                width={w - 10}
                height={20}
                sx={{ transform: 'none', borderRadius: 0.5 }}
              />
            </Box>
          ))}
        </Stack>
      </Box>

      {/* Bento grid — 220px left + 1fr right (matches real layout) */}
      <Box
        sx={{
          display: 'grid',
          gridTemplateColumns: { xs: '1fr', md: '220px 1fr' },
          gap: 2.5,
          alignItems: 'start',
        }}
      >
        {/* Left column: donut + resources + storage */}
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2.5 }}>
          {/* Success donut card */}
          <Box
            sx={{
              bgcolor: T.bgCard,
              border: `1px solid ${T.border}`,
              borderRadius: '14px',
              p: 2.5,
              textAlign: 'center',
            }}
          >
            <Skeleton
              variant="text"
              width={80}
              height={10}
              sx={{ mx: 'auto', mb: 2, transform: 'none', borderRadius: 0.5 }}
            />
            <Skeleton variant="circular" width={148} height={148} sx={{ mx: 'auto', mb: 2 }} />
            <Stack direction="row" justifyContent="center" spacing={2.5}>
              <Box>
                <Skeleton
                  variant="text"
                  width={32}
                  height={22}
                  sx={{ transform: 'none', borderRadius: 0.5 }}
                />
                <Skeleton
                  variant="text"
                  width={40}
                  height={10}
                  sx={{ mt: 0.25, transform: 'none', borderRadius: 0.5 }}
                />
              </Box>
              <Box sx={{ width: '1px', height: 28, bgcolor: T.border }} />
              <Box>
                <Skeleton
                  variant="text"
                  width={32}
                  height={22}
                  sx={{ transform: 'none', borderRadius: 0.5 }}
                />
                <Skeleton
                  variant="text"
                  width={40}
                  height={10}
                  sx={{ mt: 0.25, transform: 'none', borderRadius: 0.5 }}
                />
              </Box>
            </Stack>
          </Box>

          {/* Resources card (3 arc gauges) */}
          <Box
            sx={{
              bgcolor: T.bgCard,
              border: `1px solid ${T.border}`,
              borderRadius: '14px',
              p: 2.5,
            }}
          >
            <Skeleton
              variant="text"
              width={80}
              height={10}
              sx={{ mb: 2, transform: 'none', borderRadius: 0.5 }}
            />
            <Stack direction="row" justifyContent="space-around">
              {[0, 1, 2].map((i) => (
                <Box key={i} sx={{ textAlign: 'center' }}>
                  <Skeleton
                    variant="circular"
                    width={60}
                    height={60}
                    sx={{ mx: 'auto', mb: 0.75 }}
                  />
                  <Skeleton
                    variant="text"
                    width={28}
                    height={10}
                    sx={{ mx: 'auto', transform: 'none', borderRadius: 0.5 }}
                  />
                </Box>
              ))}
            </Stack>
          </Box>

          {/* Storage donut card */}
          <Box
            sx={{
              bgcolor: T.bgCard,
              border: `1px solid ${T.border}`,
              borderRadius: '14px',
              p: 2.5,
            }}
          >
            <Skeleton
              variant="text"
              width={60}
              height={10}
              sx={{ mb: 1.75, transform: 'none', borderRadius: 0.5 }}
            />
            <Skeleton variant="circular" width={96} height={96} sx={{ mx: 'auto', mb: 1 }} />
          </Box>
        </Box>

        {/* Right column: repo health + activity */}
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2.5 }}>
          {/* Repo health section */}
          <Box
            sx={{
              bgcolor: T.bgCard,
              border: `1px solid ${T.border}`,
              borderRadius: '14px',
              p: 2.5,
            }}
          >
            <Stack
              direction="row"
              alignItems="center"
              justifyContent="space-between"
              sx={{ mb: 2 }}
            >
              <Skeleton
                variant="text"
                width={120}
                height={12}
                sx={{ transform: 'none', borderRadius: 0.5 }}
              />
              <Stack direction="row" spacing={0.75}>
                <Skeleton variant="rounded" width={52} height={19} sx={{ borderRadius: 1 }} />
                <Skeleton variant="rounded" width={52} height={19} sx={{ borderRadius: 1 }} />
              </Stack>
            </Stack>
            <Box
              sx={{
                display: 'grid',
                gridTemplateColumns: { xs: '1fr', sm: 'repeat(2, 1fr)', lg: 'repeat(3, 1fr)' },
                gap: 1.5,
              }}
            >
              {[0, 1, 2, 3, 4, 5].map((i) => (
                <Box
                  key={i}
                  sx={{
                    bgcolor: T.bgCard,
                    border: `1px solid ${T.border}`,
                    borderRadius: '10px',
                    p: 1.5,
                    opacity: Math.max(0.3, 1 - i * 0.08),
                    animation: `dashSkeletonFadeIn 0.4s ease forwards`,
                    animationDelay: `${i * 60}ms`,
                    '@keyframes dashSkeletonFadeIn': {
                      from: { opacity: 0, transform: 'translateY(6px)' },
                      to: { opacity: Math.max(0.3, 1 - i * 0.08), transform: 'translateY(0)' },
                    },
                  }}
                >
                  {/* Top: status dot + type chip | schedule badge */}
                  <Stack
                    direction="row"
                    alignItems="center"
                    justifyContent="space-between"
                    sx={{ mb: 0.75 }}
                  >
                    <Stack direction="row" spacing={0.75} alignItems="center">
                      <Skeleton variant="circular" width={8} height={8} />
                      <Skeleton
                        variant="rounded"
                        width={36}
                        height={15}
                        sx={{ borderRadius: 0.5 }}
                      />
                    </Stack>
                    <Skeleton
                      variant="rounded"
                      width={50}
                      height={15}
                      sx={{ borderRadius: 0.75 }}
                    />
                  </Stack>
                  {/* Repo name */}
                  <Skeleton
                    variant="text"
                    width={[90, 110, 80, 95, 105, 75][i]}
                    height={14}
                    sx={{ transform: 'none', borderRadius: 0.5, mb: 0.3 }}
                  />
                  {/* Stats row */}
                  <Stack direction="row" spacing={1.5} sx={{ mb: 0.9 }}>
                    <Skeleton
                      variant="text"
                      width={28}
                      height={10}
                      sx={{ transform: 'none', borderRadius: 0.5 }}
                    />
                    <Skeleton
                      variant="text"
                      width={36}
                      height={10}
                      sx={{ transform: 'none', borderRadius: 0.5 }}
                    />
                  </Stack>
                  {/* Divider */}
                  <Box sx={{ height: '1px', bgcolor: T.border, mb: 0.9 }} />
                  {/* DimStatusGrid: BACKUP · CHECK · COMPACT */}
                  <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 0.5 }}>
                    {[0, 1, 2].map((j) => (
                      <Box key={j}>
                        <Skeleton
                          variant="text"
                          width={32}
                          height={10}
                          sx={{ transform: 'none', borderRadius: 0.5, mb: 0.25 }}
                        />
                        <Skeleton
                          variant="text"
                          width={28}
                          height={12}
                          sx={{ transform: 'none', borderRadius: 0.5 }}
                        />
                      </Box>
                    ))}
                  </Box>
                </Box>
              ))}
            </Box>
          </Box>

          {/* Activity feed */}
          <Box
            sx={{
              bgcolor: T.bgCard,
              border: `1px solid ${T.border}`,
              borderRadius: '14px',
              p: 2.5,
            }}
          >
            <Stack
              direction="row"
              alignItems="center"
              justifyContent="space-between"
              sx={{ mb: 1.75 }}
            >
              <Skeleton
                variant="text"
                width={100}
                height={10}
                sx={{ transform: 'none', borderRadius: 0.5 }}
              />
              <Skeleton
                variant="text"
                width={60}
                height={12}
                sx={{ transform: 'none', borderRadius: 0.5 }}
              />
            </Stack>
            <Stack spacing={1.25}>
              {[0, 1, 2, 3, 4].map((i) => (
                <Box
                  key={i}
                  sx={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 1.5,
                    opacity: Math.max(0.2, 1 - i * 0.15),
                  }}
                >
                  <Skeleton
                    variant="rounded"
                    width={6}
                    height={6}
                    sx={{ borderRadius: '50%', flexShrink: 0 }}
                  />
                  <Skeleton
                    variant="text"
                    width={[100, 140, 88, 120, 96][i]}
                    height={14}
                    sx={{ transform: 'none', borderRadius: 0.5 }}
                  />
                  <Box sx={{ flex: 1 }} />
                  <Skeleton
                    variant="text"
                    width={56}
                    height={10}
                    sx={{ transform: 'none', borderRadius: 0.5 }}
                  />
                </Box>
              ))}
            </Stack>
          </Box>
        </Box>
      </Box>
    </Box>
  )
}

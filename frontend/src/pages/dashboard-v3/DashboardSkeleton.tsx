import { Box, Skeleton, Stack } from '@mui/material'
import type { Tokens } from './tokens'

/**
 * DashboardSkeleton mirrors the real DashboardV3 layout so the page does
 * not jump when the data lands. Shapes to keep in sync with the live
 * dashboard:
 *
 * - 200px + 1fr bento grid (md+).
 * - Left rail: success donut (96px), resources (3 arc gauges), storage donut.
 * - Right rail: repository health panel (with recent failures strip and
 *   mixed compact + full card grid), then activity lane chart.
 * - Banner stat strip with 5 cells (System Status + 4 stats).
 */

const FULL_CARD_COUNT = 4
const COMPACT_CARD_COUNT = 8
const FAILURES_PLACEHOLDER_COUNT = 3
const NAME_WIDTHS_FULL = [110, 130, 95, 120]
const NAME_WIDTHS_COMPACT = [100, 130, 85, 115, 95, 125, 90, 105]
const LANE_DOT_COUNTS = [12, 10, 8, 5, 2]

const fadeIn = {
  '@keyframes dashSkeletonFadeIn': {
    from: { opacity: 0, transform: 'translateY(6px)' },
    to: { transform: 'translateY(0)' },
  },
}

export function DashboardSkeleton({ T }: { T: Tokens }) {
  return (
    <Box sx={{ color: T.textPrimary }}>
      {/* Health banner */}
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
          <Skeleton variant="circular" width={10} height={10} />
          <Box>
            <Skeleton
              variant="text"
              width={80}
              height={14}
              sx={{ mb: 0.25, transform: 'none', borderRadius: 0.5 }}
            />
            <Skeleton
              variant="text"
              width={120}
              height={20}
              sx={{ transform: 'none', borderRadius: 0.5 }}
            />
          </Box>
        </Stack>
        <Stack direction="row" spacing={3} flexWrap="wrap" useFlexGap>
          {[64, 96, 110, 76].map((w, i) => (
            <Box key={i}>
              <Skeleton
                variant="text"
                width={w - 12}
                height={14}
                sx={{ mb: 0.25, transform: 'none', borderRadius: 0.5 }}
              />
              <Skeleton
                variant="text"
                width={w}
                height={20}
                sx={{ transform: 'none', borderRadius: 0.5 }}
              />
            </Box>
          ))}
        </Stack>
        <Skeleton
          variant="text"
          width={56}
          height={20}
          sx={{ transform: 'none', borderRadius: 0.5 }}
        />
      </Box>

      {/* Bento grid: 200px left + 1fr right (matches real layout) */}
      <Box
        sx={{
          display: 'grid',
          gridTemplateColumns: { xs: '1fr', md: '200px 1fr' },
          gap: 2.5,
          alignItems: 'start',
        }}
      >
        {/* Left column: success donut + resources + storage */}
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
            <Stack
              direction="row"
              alignItems="baseline"
              justifyContent="space-between"
              sx={{ mb: 1.5 }}
            >
              <Skeleton
                variant="text"
                width={92}
                height={14}
                sx={{ transform: 'none', borderRadius: 0.5 }}
              />
              <Skeleton
                variant="text"
                width={40}
                height={16}
                sx={{ transform: 'none', borderRadius: 0.5 }}
              />
            </Stack>
            <Skeleton variant="circular" width={96} height={96} sx={{ mx: 'auto', mb: 1.5 }} />
            <Stack direction="row" justifyContent="center" spacing={1} sx={{ mt: 1 }}>
              <Skeleton
                variant="text"
                width={68}
                height={16}
                sx={{ transform: 'none', borderRadius: 0.5 }}
              />
              <Box sx={{ width: '1px', height: 16, bgcolor: T.border, alignSelf: 'center' }} />
              <Skeleton
                variant="text"
                width={56}
                height={16}
                sx={{ transform: 'none', borderRadius: 0.5 }}
              />
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
            <Stack direction="row" spacing={0.75} alignItems="center" sx={{ mb: 2 }}>
              <Skeleton variant="circular" width={14} height={14} />
              <Skeleton
                variant="text"
                width={72}
                height={14}
                sx={{ transform: 'none', borderRadius: 0.5 }}
              />
            </Stack>
            <Stack direction="row" justifyContent="space-around">
              {[0, 1, 2].map((i) => (
                <Box key={i} sx={{ textAlign: 'center' }}>
                  <Skeleton
                    variant="circular"
                    width={52}
                    height={52}
                    sx={{ mx: 'auto', mb: 0.75 }}
                  />
                  <Skeleton
                    variant="text"
                    width={28}
                    height={12}
                    sx={{ mx: 'auto', transform: 'none', borderRadius: 0.5 }}
                  />
                  <Skeleton
                    variant="text"
                    width={36}
                    height={10}
                    sx={{ mx: 'auto', mt: 0.25, transform: 'none', borderRadius: 0.5 }}
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
            <Stack
              direction="row"
              alignItems="baseline"
              justifyContent="space-between"
              sx={{ mb: 1.5 }}
            >
              <Skeleton
                variant="text"
                width={56}
                height={14}
                sx={{ transform: 'none', borderRadius: 0.5 }}
              />
              <Skeleton
                variant="text"
                width={56}
                height={16}
                sx={{ transform: 'none', borderRadius: 0.5 }}
              />
            </Stack>
            <Skeleton variant="circular" width={96} height={96} sx={{ mx: 'auto', mb: 1.5 }} />
            <Stack spacing={0.65}>
              {[88, 76, 80, 64, 56].map((w, i) => (
                <Stack key={i} direction="row" alignItems="center" spacing={0.75}>
                  <Skeleton variant="circular" width={8} height={8} />
                  <Skeleton
                    variant="text"
                    width={w}
                    height={12}
                    sx={{ transform: 'none', borderRadius: 0.5, flex: 1 }}
                  />
                  <Skeleton
                    variant="text"
                    width={32}
                    height={12}
                    sx={{ transform: 'none', borderRadius: 0.5 }}
                  />
                </Stack>
              ))}
            </Stack>
          </Box>
        </Box>

        {/* Right column: repo health + activity */}
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2.5 }}>
          {/* Repository Health */}
          <Box
            sx={{
              bgcolor: T.bgCard,
              border: `1px solid ${T.border}`,
              borderRadius: '14px',
              p: 2.5,
            }}
          >
            {/* Header: title + 3 status count chips (critical / warn / ok) */}
            <Stack
              direction="row"
              alignItems="center"
              justifyContent="space-between"
              sx={{ mb: 2 }}
            >
              <Stack direction="row" spacing={1} alignItems="center">
                <Skeleton variant="circular" width={14} height={14} />
                <Skeleton
                  variant="text"
                  width={130}
                  height={14}
                  sx={{ transform: 'none', borderRadius: 0.5 }}
                />
              </Stack>
              <Stack direction="row" spacing={0.75}>
                <Skeleton variant="rounded" width={66} height={22} sx={{ borderRadius: 1 }} />
                <Skeleton variant="rounded" width={56} height={22} sx={{ borderRadius: 1 }} />
                <Skeleton variant="rounded" width={48} height={22} sx={{ borderRadius: 1 }} />
              </Stack>
            </Stack>

            {/* Recent failures strip: a red-bordered block sized like the
                live strip when there are failures. Sized once even if empty
                so the page doesn't jump when failures arrive. */}
            <Box
              sx={{
                mb: 2,
                border: `1px solid ${T.border}`,
                borderRadius: '10px',
                p: 1.25,
              }}
            >
              <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 0.75 }}>
                <Skeleton variant="circular" width={14} height={14} />
                <Skeleton
                  variant="text"
                  width={110}
                  height={14}
                  sx={{ transform: 'none', borderRadius: 0.5 }}
                />
              </Stack>
              <Stack spacing={0.4}>
                {Array.from({ length: FAILURES_PLACEHOLDER_COUNT }).map((_, i) => (
                  <Stack key={i} direction="row" spacing={1} alignItems="baseline">
                    <Skeleton
                      variant="text"
                      width={[110, 90, 130][i]}
                      height={14}
                      sx={{ transform: 'none', borderRadius: 0.5 }}
                    />
                    <Skeleton
                      variant="text"
                      width={[80, 56, 96][i]}
                      height={12}
                      sx={{ transform: 'none', borderRadius: 0.5 }}
                    />
                    <Skeleton
                      variant="text"
                      width={[220, 280, 180][i]}
                      height={12}
                      sx={{ transform: 'none', borderRadius: 0.5, flex: 1 }}
                    />
                  </Stack>
                ))}
              </Stack>
            </Box>

            {/* Card grid: mix of full (critical/warning) + compact (healthy)
                cards. The real grid auto-fits at minmax(300px, 1fr); the
                skeleton uses the same. */}
            <Box
              sx={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))',
                gap: 1.5,
              }}
            >
              {/* Full cards (critical / warning) */}
              {Array.from({ length: FULL_CARD_COUNT }).map((_, i) => (
                <Box
                  key={`full-${i}`}
                  sx={{
                    border: `1px solid ${T.border}`,
                    borderRadius: '10px',
                    p: 1.25,
                    opacity: Math.max(0.3, 1 - i * 0.08),
                    animation: `dashSkeletonFadeIn 0.4s ease forwards`,
                    animationDelay: `${i * 60}ms`,
                    ...fadeIn,
                  }}
                >
                  {/* Top row: pulse dot + type chip | schedule pill */}
                  <Stack
                    direction="row"
                    alignItems="center"
                    justifyContent="space-between"
                    sx={{ mb: 0.55 }}
                  >
                    <Stack direction="row" spacing={0.75} alignItems="center">
                      <Skeleton variant="circular" width={10} height={10} />
                      <Skeleton variant="rounded" width={48} height={20} sx={{ borderRadius: 1 }} />
                    </Stack>
                    <Skeleton variant="rounded" width={56} height={20} sx={{ borderRadius: 1 }} />
                  </Stack>
                  {/* Repo name */}
                  <Skeleton
                    variant="text"
                    width={NAME_WIDTHS_FULL[i] ?? 100}
                    height={16}
                    sx={{ transform: 'none', borderRadius: 0.5, mb: 0.4 }}
                  />
                  {/* Stats row */}
                  <Stack direction="row" spacing={1.5} sx={{ mb: 0.9 }}>
                    <Skeleton
                      variant="text"
                      width={36}
                      height={12}
                      sx={{ transform: 'none', borderRadius: 0.5 }}
                    />
                    <Skeleton
                      variant="text"
                      width={48}
                      height={12}
                      sx={{ transform: 'none', borderRadius: 0.5 }}
                    />
                  </Stack>
                  {/* Divider */}
                  <Box sx={{ height: '1px', bgcolor: T.border, mb: 0.9 }} />
                  {/* DimStatusGrid: 2x2 inline cells */}
                  <Box
                    sx={{
                      display: 'grid',
                      gridTemplateColumns: 'repeat(2, minmax(0, 1fr))',
                      columnGap: 1.5,
                      rowGap: 0.75,
                    }}
                  >
                    {[0, 1, 2, 3].map((j) => (
                      <Stack key={j} direction="row" spacing={0.5} alignItems="center">
                        <Skeleton variant="circular" width={12} height={12} />
                        <Skeleton
                          variant="text"
                          width={[52, 44, 60, 56][j]}
                          height={12}
                          sx={{ transform: 'none', borderRadius: 0.5, flexGrow: 1 }}
                        />
                        <Skeleton
                          variant="text"
                          width={[36, 32, 28, 44][j]}
                          height={12}
                          sx={{ transform: 'none', borderRadius: 0.5 }}
                        />
                      </Stack>
                    ))}
                  </Box>
                </Box>
              ))}

              {/* Compact cards (healthy) */}
              {Array.from({ length: COMPACT_CARD_COUNT }).map((_, i) => (
                <Box
                  key={`compact-${i}`}
                  sx={{
                    border: `1px solid ${T.border}`,
                    borderRadius: '10px',
                    p: 1.25,
                    opacity: Math.max(0.25, 0.85 - i * 0.06),
                    animation: `dashSkeletonFadeIn 0.4s ease forwards`,
                    animationDelay: `${(FULL_CARD_COUNT + i) * 60}ms`,
                    ...fadeIn,
                  }}
                >
                  <Stack direction="row" spacing={1} alignItems="center">
                    <Skeleton variant="circular" width={10} height={10} />
                    <Box sx={{ flexGrow: 1, minWidth: 0 }}>
                      <Skeleton
                        variant="text"
                        width={NAME_WIDTHS_COMPACT[i] ?? 100}
                        height={16}
                        sx={{ transform: 'none', borderRadius: 0.5 }}
                      />
                      <Stack direction="row" spacing={0.75} alignItems="center" sx={{ mt: 0.4 }}>
                        <Skeleton
                          variant="rounded"
                          width={48}
                          height={20}
                          sx={{ borderRadius: 1 }}
                        />
                        <Skeleton
                          variant="text"
                          width={120}
                          height={12}
                          sx={{ transform: 'none', borderRadius: 0.5 }}
                        />
                      </Stack>
                    </Box>
                    <Stack alignItems="flex-end" spacing={0.4}>
                      <Skeleton
                        variant="text"
                        width={60}
                        height={12}
                        sx={{ transform: 'none', borderRadius: 0.5 }}
                      />
                      <Skeleton variant="rounded" width={52} height={20} sx={{ borderRadius: 1 }} />
                    </Stack>
                  </Stack>
                </Box>
              ))}
            </Box>
          </Box>

          {/* Activity panel: compact lane chart */}
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
              <Stack direction="row" spacing={1} alignItems="center">
                <Skeleton variant="circular" width={14} height={14} />
                <Skeleton
                  variant="text"
                  width={140}
                  height={14}
                  sx={{ transform: 'none', borderRadius: 0.5 }}
                />
              </Stack>
              <Skeleton
                variant="text"
                width={64}
                height={14}
                sx={{ transform: 'none', borderRadius: 0.5 }}
              />
            </Stack>
            {/* Lane chart: 5 rows, each labelled, with scattered placeholder
                dots along the row. */}
            <Stack spacing={0.5} sx={{ pl: 5, pr: 1 }}>
              {LANE_DOT_COUNTS.map((count, lane) => (
                <Box
                  key={lane}
                  sx={{
                    position: 'relative',
                    height: 14,
                    opacity: Math.max(0.25, 1 - lane * 0.15),
                  }}
                >
                  {/* Lane label sits in the gutter */}
                  <Skeleton
                    variant="text"
                    width={44}
                    height={10}
                    sx={{
                      position: 'absolute',
                      left: -48,
                      top: 2,
                      transform: 'none',
                      borderRadius: 0.5,
                    }}
                  />
                  {Array.from({ length: count }).map((_, dot) => (
                    <Skeleton
                      key={dot}
                      variant="circular"
                      width={6}
                      height={6}
                      sx={{
                        position: 'absolute',
                        left: `${(dot / Math.max(count - 1, 1)) * 95}%`,
                        top: 4,
                      }}
                    />
                  ))}
                </Box>
              ))}
            </Stack>
            {/* Failed-marker legend */}
            <Stack direction="row" spacing={0.65} alignItems="center" sx={{ mt: 1.5 }}>
              <Skeleton variant="circular" width={8} height={8} />
              <Skeleton
                variant="text"
                width={48}
                height={12}
                sx={{ transform: 'none', borderRadius: 0.5 }}
              />
            </Stack>
          </Box>
        </Box>
      </Box>
    </Box>
  )
}

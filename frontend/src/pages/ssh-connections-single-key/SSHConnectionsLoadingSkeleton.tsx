import { Box, Skeleton, Stack, alpha } from '@mui/material'

interface SSHConnectionsLoadingSkeletonProps {
  isDark: boolean
}

export function SSHConnectionsLoadingSkeleton({ isDark }: SSHConnectionsLoadingSkeletonProps) {
  return (
    <Box>
      {/* Header skeleton */}
      <Box sx={{ mb: 4 }}>
        <Skeleton
          variant="text"
          width={200}
          height={36}
          sx={{ transform: 'none', borderRadius: 0.5, mb: 0.75 }}
        />
        <Skeleton
          variant="text"
          width={320}
          height={16}
          sx={{ transform: 'none', borderRadius: 0.5 }}
        />
      </Box>

      {/* Stats band skeleton */}
      <Box
        sx={{
          display: 'grid',
          gridTemplateColumns: 'repeat(3, 1fr)',
          borderRadius: 2,
          border: '1px solid',
          borderColor: isDark ? alpha('#fff', 0.06) : alpha('#000', 0.07),
          overflow: 'hidden',
          mb: 3,
          bgcolor: isDark ? alpha('#fff', 0.025) : alpha('#000', 0.018),
        }}
      >
        {[0, 1, 2].map((i) => (
          <Box
            key={i}
            sx={{
              px: { xs: 1.25, sm: 2 },
              py: { xs: 1.5, sm: 1.75 },
              borderRight: i < 2 ? '1px solid' : 0,
              borderColor: isDark ? alpha('#fff', 0.06) : alpha('#000', 0.07),
            }}
          >
            <Box
              sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mb: { xs: 0.75, sm: 0.5 } }}
            >
              <Skeleton variant="rounded" width={13} height={13} sx={{ borderRadius: 0.5 }} />
              <Skeleton
                variant="text"
                width={80}
                height={12}
                sx={{ transform: 'none', borderRadius: 0.5 }}
              />
            </Box>
            <Skeleton
              variant="text"
              width={32}
              sx={{ transform: 'none', borderRadius: 0.5, height: { xs: 28, sm: 24 } }}
            />
          </Box>
        ))}
      </Box>

      {/* System SSH Key card skeleton */}
      <Box
        sx={{
          borderRadius: 2,
          bgcolor: 'background.paper',
          overflow: 'hidden',
          mb: 3,
          boxShadow: isDark
            ? `0 0 0 1px ${alpha('#fff', 0.08)}, 0 4px 16px ${alpha('#000', 0.25)}`
            : `0 0 0 1px ${alpha('#000', 0.08)}, 0 2px 8px ${alpha('#000', 0.07)}`,
        }}
      >
        <Box sx={{ px: { xs: 2, sm: 2.5 }, pt: { xs: 2, sm: 2.5 }, pb: { xs: 2, sm: 2.5 } }}>
          <Stack direction="row" alignItems="center" spacing={1.5} sx={{ mb: 2 }}>
            <Skeleton
              variant="rounded"
              width={34}
              height={34}
              sx={{ borderRadius: 1.5, flexShrink: 0 }}
            />
            <Skeleton
              variant="text"
              width={140}
              height={24}
              sx={{ transform: 'none', borderRadius: 0.5, flex: 1 }}
            />
            <Skeleton variant="rounded" width={64} height={22} sx={{ borderRadius: 3 }} />
          </Stack>
          <Stack spacing={2}>
            <Box>
              <Skeleton
                variant="text"
                width={48}
                height={20}
                sx={{ transform: 'none', borderRadius: 0.5 }}
              />
              <Skeleton
                variant="text"
                width={80}
                height={20}
                sx={{ transform: 'none', borderRadius: 0.5 }}
              />
            </Box>
            <Box>
              <Skeleton
                variant="text"
                width={80}
                height={20}
                sx={{ transform: 'none', borderRadius: 0.5 }}
              />
              <Skeleton
                variant="text"
                width="60%"
                height={20}
                sx={{ transform: 'none', borderRadius: 0.5 }}
              />
            </Box>
            <Box>
              <Skeleton
                variant="text"
                width={70}
                height={20}
                sx={{ transform: 'none', borderRadius: 0.5, mb: 0.5 }}
              />
              <Skeleton variant="rounded" width="100%" height={55} sx={{ borderRadius: 1 }} />
            </Box>
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
              <Skeleton variant="rounded" width={160} height={36} sx={{ borderRadius: 1 }} />
              <Skeleton variant="rounded" width={140} height={36} sx={{ borderRadius: 1 }} />
              <Skeleton variant="rounded" width={120} height={36} sx={{ borderRadius: 1 }} />
            </Stack>
          </Stack>
        </Box>
      </Box>

      {/* Remote Connections section skeleton */}
      <Box>
        {/* Section header */}
        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
          <Box>
            <Skeleton
              variant="text"
              width={160}
              height={24}
              sx={{ transform: 'none', borderRadius: 0.5, mb: 0.4 }}
            />
            <Skeleton
              variant="text"
              width={120}
              height={14}
              sx={{ transform: 'none', borderRadius: 0.5 }}
            />
          </Box>
          <Skeleton variant="rounded" width={32} height={32} sx={{ borderRadius: 1.5 }} />
        </Box>

        {/* Connection cards — flex wrap matching real RemoteMachineCard layout */}
        <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: { xs: 2, sm: 2.5 } }}>
          {[0, 1, 2].map((i) => (
            <Box
              key={i}
              sx={{
                flex: {
                  xs: '0 0 100%',
                  sm: '0 0 calc(50% - 10px)',
                  md: '0 0 calc(33.333% - 14px)',
                },
                minWidth: 0,
                display: 'flex',
              }}
            >
              <Box
                sx={{
                  width: '100%',
                  display: 'flex',
                  flexDirection: 'column',
                  borderRadius: 2,
                  bgcolor: 'background.paper',
                  boxShadow: isDark
                    ? `0 0 0 1px ${alpha('#fff', 0.08)}, 0 4px 16px ${alpha('#000', 0.25)}`
                    : `0 0 0 1px ${alpha('#000', 0.08)}, 0 2px 8px ${alpha('#000', 0.07)}`,
                  opacity: Math.max(0.4, 1 - i * 0.2),
                }}
              >
                <Box
                  sx={{
                    flex: 1,
                    display: 'flex',
                    flexDirection: 'column',
                    px: { xs: 1.75, sm: 2 },
                    pt: { xs: 1.75, sm: 2 },
                    pb: { xs: 1.5, sm: 1.75 },
                  }}
                >
                  {/* Header: status + name + connection string */}
                  <Box sx={{ mb: 1.5 }}>
                    <Box
                      sx={{
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        mb: 0.5,
                      }}
                    >
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                        <Skeleton variant="circular" width={13} height={13} />
                        <Skeleton
                          variant="text"
                          width={60}
                          height={12}
                          sx={{ transform: 'none', borderRadius: 0.5 }}
                        />
                      </Box>
                      <Skeleton
                        variant="text"
                        width={70}
                        height={10}
                        sx={{ transform: 'none', borderRadius: 0.5 }}
                      />
                    </Box>
                    <Skeleton
                      variant="text"
                      width={[160, 130, 150][i]}
                      height={22}
                      sx={{ transform: 'none', borderRadius: 0.5, mb: 0.25 }}
                    />
                    <Skeleton
                      variant="text"
                      width={[180, 200, 170][i]}
                      height={14}
                      sx={{ transform: 'none', borderRadius: 0.5 }}
                    />
                  </Box>

                  {/* Storage stats band: 2-col + progress bar */}
                  <Box
                    sx={{
                      borderRadius: 1.5,
                      border: '1px solid',
                      borderColor: isDark ? alpha('#fff', 0.06) : alpha('#000', 0.07),
                      overflow: 'hidden',
                      mb: 1.5,
                    }}
                  >
                    <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)' }}>
                      {[0, 1].map((j) => (
                        <Box
                          key={j}
                          sx={{
                            px: { xs: 1.25, sm: 1.5 },
                            py: { xs: 1.25, sm: 1 },
                            borderRight: j === 0 ? '1px solid' : 0,
                            borderColor: isDark ? alpha('#fff', 0.06) : alpha('#000', 0.07),
                          }}
                        >
                          <Skeleton
                            variant="text"
                            width={30}
                            height={10}
                            sx={{ transform: 'none', borderRadius: 0.5, mb: 0.5 }}
                          />
                          <Skeleton
                            variant="text"
                            width={50}
                            height={18}
                            sx={{ transform: 'none', borderRadius: 0.5 }}
                          />
                        </Box>
                      ))}
                    </Box>
                    <Box
                      sx={{
                        px: { xs: 1.25, sm: 1.5 },
                        pb: 1,
                        pt: 0.75,
                        borderTop: '1px solid',
                        borderColor: isDark ? alpha('#fff', 0.05) : alpha('#000', 0.06),
                      }}
                    >
                      <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.5 }}>
                        <Skeleton
                          variant="text"
                          width={50}
                          height={10}
                          sx={{ transform: 'none', borderRadius: 0.5 }}
                        />
                        <Skeleton
                          variant="text"
                          width={60}
                          height={10}
                          sx={{ transform: 'none', borderRadius: 0.5 }}
                        />
                      </Box>
                      <Skeleton
                        variant="rounded"
                        width="100%"
                        height={5}
                        sx={{ borderRadius: 1 }}
                      />
                    </Box>
                  </Box>

                  {/* Action bar */}
                  <Box
                    sx={{
                      mt: 'auto',
                      display: 'flex',
                      alignItems: 'center',
                      gap: { xs: 0.75, sm: 0.5 },
                      pt: { xs: 1.5, sm: 1.25 },
                      borderTop: '1px solid',
                      borderColor: isDark ? alpha('#fff', 0.06) : alpha('#000', 0.07),
                    }}
                  >
                    {[0, 1, 2, 3, 4].map((j) => (
                      <Skeleton
                        key={j}
                        variant="rounded"
                        width={34}
                        height={34}
                        sx={{ borderRadius: 1.5 }}
                      />
                    ))}
                  </Box>
                </Box>
              </Box>
            </Box>
          ))}
        </Box>
      </Box>
    </Box>
  )
}

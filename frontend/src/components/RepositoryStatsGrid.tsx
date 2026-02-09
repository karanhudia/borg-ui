import { Box, Card, CardContent, Stack, Typography } from '@mui/material'
import { Archive as ArchiveIcon, Database, Gauge, Layers } from 'lucide-react'
import { formatBytes as formatBytesUtil } from '../utils/dateUtils'

interface RepositoryStats {
  unique_csize: number
  unique_size: number
  total_size: number
}

interface RepositoryStatsGridProps {
  stats: RepositoryStats
  archivesCount: number
}

export default function RepositoryStatsGrid({ stats, archivesCount }: RepositoryStatsGridProps) {
  const spaceSaved = (stats.total_size || 0) - (stats.unique_csize || 0)
  const compressionRatio =
    stats.unique_size > 0 ? ((1 - stats.unique_csize / stats.unique_size) * 100).toFixed(1) : '0'
  const deduplicationRatio =
    stats.total_size > 0 ? ((1 - stats.unique_size / stats.total_size) * 100).toFixed(1) : '0'

  return (
    <Box
      sx={{
        display: 'grid',
        gridTemplateColumns: { xs: '1fr', sm: 'repeat(2, 1fr)', lg: 'repeat(5, 1fr)' },
        gap: 2,
        mb: 4,
      }}
    >
      {/* Total Archives */}
      <Card sx={{ backgroundColor: '#e3f2fd' }}>
        <CardContent>
          <Stack direction="row" spacing={2} alignItems="center">
            <ArchiveIcon size={32} color="#1565c0" />
            <Box>
              <Typography variant="body2" color="primary.dark" fontWeight={500}>
                Total Archives
              </Typography>
              <Typography variant="h4" fontWeight={700} color="primary.dark">
                {archivesCount}
              </Typography>
            </Box>
          </Stack>
        </CardContent>
      </Card>

      {/* Space Used on Disk */}
      <Card sx={{ backgroundColor: '#e8f5e9' }}>
        <CardContent>
          <Stack direction="row" spacing={2} alignItems="center">
            <Database size={32} color="#2e7d32" />
            <Box>
              <Typography variant="body2" color="success.dark" fontWeight={500}>
                Space Used
              </Typography>
              <Typography
                variant="h4"
                fontWeight={700}
                color="success.dark"
                sx={{ fontSize: '1.5rem' }}
              >
                {formatBytesUtil(stats.unique_csize)}
              </Typography>
            </Box>
          </Stack>
        </CardContent>
      </Card>

      {/* Space Saved */}
      <Card sx={{ backgroundColor: '#e1f5fe' }}>
        <CardContent>
          <Stack direction="row" spacing={2} alignItems="center">
            <Database size={32} color="#0277bd" />
            <Box>
              <Typography variant="body2" sx={{ color: '#0277bd' }} fontWeight={500}>
                Space Saved
              </Typography>
              <Typography
                variant="h4"
                fontWeight={700}
                sx={{ color: '#0277bd', fontSize: '1.5rem' }}
              >
                {spaceSaved > 0 ? formatBytesUtil(spaceSaved) : '0 B'}
              </Typography>
            </Box>
          </Stack>
        </CardContent>
      </Card>

      {/* Compression */}
      <Card sx={{ backgroundColor: '#f3e5f5' }}>
        <CardContent>
          <Stack direction="row" spacing={2} alignItems="center">
            <Gauge size={32} color="#7b1fa2" />
            <Box>
              <Typography variant="body2" color="purple" fontWeight={500}>
                Compression
              </Typography>
              <Typography variant="h4" fontWeight={700} color="purple">
                {compressionRatio}%
              </Typography>
            </Box>
          </Stack>
        </CardContent>
      </Card>

      {/* Deduplication */}
      <Card sx={{ backgroundColor: '#fff3e0' }}>
        <CardContent>
          <Stack direction="row" spacing={2} alignItems="center">
            <Layers size={32} color="#e65100" />
            <Box>
              <Typography variant="body2" sx={{ color: '#e65100' }} fontWeight={500}>
                Deduplication
              </Typography>
              <Typography variant="h4" fontWeight={700} sx={{ color: '#e65100' }}>
                {deduplicationRatio}%
              </Typography>
            </Box>
          </Stack>
        </CardContent>
      </Card>
    </Box>
  )
}

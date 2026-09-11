import type { ComponentType } from 'react'
import { Box, Link, Tooltip, Typography, alpha, useTheme } from '@mui/material'
import { Link as RouterLink } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { ArrowLeft, Loader2, Minimize2, Scissors, ShieldCheck } from 'lucide-react'
import { repositoriesAPI } from '../../services/api'
import { CATEGORY_ICONS } from '../../components/categoryStyle'
import { formatDateTimeFull, formatRelativeTime } from '../../utils/dateUtils'
import type { Repository } from '@/types'

export interface RepositoryStatusCell {
  cell: 'backup' | 'check' | 'prune' | 'compact' | 'index' | 'mirror'
  status: string | null
  completed_at: string | null
  age_seconds: number | null
  threshold_days: number | null
  overdue: boolean | null
  running: boolean
  source: string | null
}

interface RepositoryStatusResponse {
  cells: RepositoryStatusCell[]
  overdue_available: boolean
}

const CELL_ICONS: Record<RepositoryStatusCell['cell'], ComponentType<{ size?: number }>> = {
  backup: CATEGORY_ICONS.backup,
  check: ShieldCheck,
  prune: Scissors,
  compact: Minimize2,
  index: CATEGORY_ICONS.index,
  mirror: CATEGORY_ICONS.mirror,
}

interface RepositoryHeaderProps {
  repositoryId: number
  repository: Repository | undefined
}

// The pinned repository's name and its health per category, from the
// status route the card already reasons with (spec 10.2). The timeline
// below is the same one as the global page.
export default function RepositoryHeader({ repositoryId, repository }: RepositoryHeaderProps) {
  const { t } = useTranslation()
  const theme = useTheme()
  const { data } = useQuery({
    queryKey: ['repository-status', repositoryId],
    queryFn: async () => {
      const response = await repositoriesAPI.getStatus(repositoryId)
      return response.data as RepositoryStatusResponse
    },
    refetchInterval: 15000,
  })
  const cells = data?.cells ?? []

  return (
    <Box
      data-testid="repository-header"
      sx={{
        mb: 3,
        p: 2.5,
        borderRadius: 3,
        border: 1,
        borderColor: 'divider',
        bgcolor: 'background.paper',
      }}
    >
      <Link
        component={RouterLink}
        to="/activity"
        underline="hover"
        sx={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: 0.5,
          mb: 1.5,
          fontSize: '0.8125rem',
        }}
      >
        <ArrowLeft size={14} />
        {t('activity.repositoryView.back')}
      </Link>
      <Typography variant="h5" component="h2" sx={{ fontWeight: 700, wordBreak: 'break-word' }}>
        {repository?.name ?? String(repositoryId)}
      </Typography>
      {repository?.path && (
        <Typography
          variant="caption"
          sx={{ color: 'text.secondary', fontFamily: 'monospace', display: 'block' }}
        >
          {repository.path}
        </Typography>
      )}
      {cells.length > 0 && (
        <Box
          sx={{
            display: 'grid',
            gridTemplateColumns: {
              xs: 'repeat(2, minmax(0, 1fr))',
              sm: 'repeat(3, minmax(0, 1fr))',
              md: `repeat(${Math.min(cells.length, 6)}, minmax(0, 1fr))`,
            },
            gap: 1,
            mt: 2,
          }}
        >
          {cells.map((cell) => {
            const Icon = CELL_ICONS[cell.cell]
            const overdue = cell.overdue === true
            const color = cell.running
              ? theme.palette.primary.main
              : overdue
                ? theme.palette.warning.main
                : cell.completed_at
                  ? theme.palette.success.main
                  : theme.palette.text.disabled
            const value = cell.running
              ? t('activity.health.running')
              : cell.completed_at
                ? formatRelativeTime(cell.completed_at)
                : t('common.never')
            return (
              <Tooltip
                key={cell.cell}
                title={cell.completed_at ? formatDateTimeFull(cell.completed_at) : ''}
                arrow
              >
                <Box
                  data-testid="health-cell"
                  data-cell={cell.cell}
                  sx={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 1,
                    px: 1.25,
                    py: 1,
                    borderRadius: 2,
                    bgcolor: alpha(color, 0.08),
                    minWidth: 0,
                  }}
                >
                  <Box sx={{ color, display: 'flex', flexShrink: 0 }}>
                    {cell.running ? (
                      <Loader2 size={16} className="animate-spin" />
                    ) : (
                      <Icon size={16} />
                    )}
                  </Box>
                  <Box sx={{ minWidth: 0 }}>
                    <Typography
                      variant="caption"
                      sx={{
                        display: 'block',
                        color: 'text.secondary',
                        lineHeight: 1.2,
                        textTransform: 'uppercase',
                        letterSpacing: '0.04em',
                        fontSize: '0.625rem',
                        fontWeight: 600,
                      }}
                    >
                      {t(`activity.health.${cell.cell}`)}
                    </Typography>
                    <Typography variant="body2" sx={{ fontWeight: 600, color }} noWrap>
                      {value}
                      {overdue && !cell.running && ` · ${t('activity.health.overdue')}`}
                    </Typography>
                  </Box>
                </Box>
              </Tooltip>
            )
          })}
        </Box>
      )}
    </Box>
  )
}

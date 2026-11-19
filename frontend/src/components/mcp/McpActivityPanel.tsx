import { Box, Button, Chip, CircularProgress, Stack, Typography, useTheme } from '@mui/material'
import { useInfiniteQuery } from '@tanstack/react-query'
import { History } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { MCP_ACTIVITY_PAGE, mcpAPI, type McpOutcome } from '../../services/api'
import { formatRelativeTime } from '../../utils/dateUtils'
import EmptyStateCard from '../EmptyStateCard'
import { tintChipSx, type Tone } from '../shared/tones'

const OUTCOME_TONE: Record<McpOutcome, Tone> = {
  ok: 'success',
  error: 'error',
  denied_level: 'warning',
  denied_rbac: 'warning',
  needs_confirmation: 'info',
  confirmed: 'info',
}

/** One connection's tool calls, newest first, paged by id. */
export default function McpActivityPanel({ connectionId }: { connectionId: number }) {
  const { t } = useTranslation()
  const theme = useTheme()
  const query = useInfiniteQuery({
    queryKey: ['mcp-activity', connectionId],
    queryFn: ({ pageParam }) => mcpAPI.activity(connectionId, pageParam).then((r) => r.data),
    initialPageParam: undefined as number | undefined,
    getNextPageParam: (last) =>
      last.length === MCP_ACTIVITY_PAGE ? last[last.length - 1].id : undefined,
  })

  if (query.isLoading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', py: 4 }}>
        <CircularProgress size={24} />
      </Box>
    )
  }
  const rows = query.data?.pages.flat() ?? []
  if (rows.length === 0) {
    return (
      <EmptyStateCard
        icon={<History size={28} />}
        title={t('mcp.activity.empty')}
        description={t('mcp.activity.emptyBody')}
      />
    )
  }

  return (
    <Stack spacing={1.5}>
      <Box
        sx={{ border: '1px solid', borderColor: 'divider', borderRadius: 2, overflow: 'hidden' }}
      >
        {rows.map((row) => (
          <Box
            key={row.id}
            sx={{
              display: 'flex',
              alignItems: 'center',
              flexWrap: 'wrap',
              gap: 1,
              px: 2,
              py: 1.25,
              '&:not(:last-of-type)': { borderBottom: '1px solid', borderColor: 'divider' },
            }}
          >
            <Chip
              size="small"
              label={t(`mcp.activity.outcome.${row.outcome}`)}
              sx={tintChipSx(theme, OUTCOME_TONE[row.outcome])}
            />
            <Typography variant="body2" sx={{ fontFamily: 'monospace', minWidth: 0 }}>
              {row.tool}
            </Typography>
            {row.target && (
              <Typography variant="body2" color="text.secondary" noWrap sx={{ minWidth: 0 }}>
                {row.target}
              </Typography>
            )}
            <Typography
              variant="body2"
              color="text.secondary"
              sx={{ ml: 'auto', fontVariantNumeric: 'tabular-nums', whiteSpace: 'nowrap' }}
            >
              {t('mcp.activity.durationMs', { ms: row.duration_ms })} ·{' '}
              {formatRelativeTime(row.created_at)}
            </Typography>
          </Box>
        ))}
      </Box>
      {query.hasNextPage && (
        <Box>
          <Button
            onClick={() => query.fetchNextPage()}
            disabled={query.isFetchingNextPage}
            sx={{ minHeight: 44 }}
          >
            {t('mcp.activity.loadMore')}
          </Button>
        </Box>
      )}
    </Stack>
  )
}

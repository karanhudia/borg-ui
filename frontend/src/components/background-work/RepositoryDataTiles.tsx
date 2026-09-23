import { Box } from '@mui/material'
import { BarChart3, History, ListChecks } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { formatDistanceToNow } from 'date-fns'
import TintedTile from '../shared/TintedTile'
import type { Tone } from '../shared/tones'
import { PLAN_LABEL } from '../../core/features'
import { parseBackendDate } from '../../utils/dateUtils'
import type { HubRepository } from '../../types/operations'

interface RepositoryDataTilesProps {
  repository: HubRepository
  historyAvailable: boolean
  totalHistoryRows: number
}

interface Tile {
  key: string
  label: string
  value: React.ReactNode
  sub?: React.ReactNode
  tone: Tone
  icon: typeof ListChecks
  muted?: boolean
}

const ago = (value: string) => formatDistanceToNow(parseBackendDate(value), { addSuffix: true })

// What each stage keeps for one repository, as the archive header's tinted
// tiles: the archive list, the file history built from it, and the stats.
// The hub table shows only when any of it last changed, so a new stage adds
// a tile here rather than a column there.
export default function RepositoryDataTiles({
  repository,
  historyAvailable,
  totalHistoryRows,
}: RepositoryDataTilesProps) {
  const { t } = useTranslation()
  const mode = repository.index_mode ?? 'full'
  const { history } = repository
  const hub = (key: string, options?: Record<string, unknown>) =>
    t(`operations.background.hub.${key}`, options)

  // An amber "out of date" on a repository nobody indexes is the false
  // alarm the summary counts drop too (spec 6.8), so it is stated plainly.
  const archives: Tile = {
    key: 'archives',
    label: t('operations.background.stage.archives'),
    icon: ListChecks,
    value: hub('rowArchives', { count: repository.archives }),
    sub:
      mode === 'off'
        ? hub('syncOff')
        : repository.sync_state === 'fresh' && repository.last_synced_at
          ? t('archives.sync.fresh', { ago: ago(repository.last_synced_at) })
          : t(`archives.sync.${repository.sync_state}`),
    tone: mode !== 'off' && repository.sync_state === 'stale' ? 'warning' : 'info',
  }

  let fileHistory: Tile = {
    key: 'history',
    label: t('operations.background.stage.history'),
    icon: History,
    tone: 'secondary',
    value: null,
  }
  // Mode before capability before plan, as the hub row read them: an
  // upgrade would not start indexing a repository opted out of it.
  if (mode !== 'full') {
    fileHistory = {
      ...fileHistory,
      muted: true,
      value: hub(mode === 'archives' ? 'modeArchives' : 'modeOff'),
    }
  } else if (
    repository.history_capability === 'agent_unsupported' &&
    (!historyAvailable || (history.indexed === 0 && history.rows === 0))
  ) {
    fileHistory = { ...fileHistory, muted: true, value: hub('historyAgentUnsupported') }
  } else if (!historyAvailable) {
    fileHistory = { ...fileHistory, muted: true, value: PLAN_LABEL.pro }
  } else if (history.rows === 0 && history.indexed === 0) {
    fileHistory = { ...fileHistory, muted: true, value: hub('historyNone') }
  } else {
    const share = totalHistoryRows > 0 ? Math.round((history.rows / totalHistoryRows) * 100) : null
    const parts = [
      hub('historyRows', { count: history.rows }),
      share != null && share > 0 ? hub('historyShare', { percent: share }) : null,
      history.failed > 0 ? hub('historyFailed', { count: history.failed }) : null,
      history.truncated > 0 ? hub('historyTruncated', { count: history.truncated }) : null,
      history.pending > 0 ? hub('historyPending', { count: history.pending }) : null,
    ].filter(Boolean)
    fileHistory = {
      ...fileHistory,
      value: hub('historyCoverage', {
        indexed: history.indexed.toLocaleString(),
        total: repository.archives.toLocaleString(),
      }),
      sub: parts.join(' · '),
      tone: history.failed > 0 || history.truncated > 0 ? 'warning' : 'secondary',
    }
  }

  const stats: Tile = {
    key: 'stats',
    label: t('operations.background.stage.stats'),
    icon: BarChart3,
    tone: 'success',
    muted: repository.last_stats_at == null,
    value: repository.last_stats_at
      ? hub('statsRefreshed', { ago: ago(repository.last_stats_at) })
      : hub('statsNever'),
  }

  return (
    <Box
      sx={{
        display: 'grid',
        gridTemplateColumns: { xs: '1fr', sm: 'repeat(3, minmax(0, 1fr))' },
        gap: 1.5,
      }}
    >
      {[archives, fileHistory, stats].map((tile) => (
        <TintedTile
          key={tile.key}
          testId={`repository-data-${tile.key}`}
          label={tile.label}
          value={tile.value}
          sub={tile.sub}
          tone={tile.tone}
          icon={tile.icon}
          muted={tile.muted}
        />
      ))}
    </Box>
  )
}

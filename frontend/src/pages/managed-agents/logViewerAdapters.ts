import type { LogFetchResult, LogLine } from '../../components/shared/TerminalLogViewer'
import type { AgentJobLogEntryResponse, AgentSessionLogEntryResponse } from '../../services/api'

function formatLogDate(value?: string | null): string {
  if (!value) return 'Never'
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(value))
}

function sliceViewerLines(lines: LogLine[], offset: number): LogFetchResult {
  const start = Math.max(0, offset)
  const visibleLines = lines.slice(start)
  return {
    lines: visibleLines,
    total_lines: lines.length,
    has_more: start + visibleLines.length < lines.length,
  }
}

export function agentJobLogsToViewerResult(
  logs: AgentJobLogEntryResponse[],
  offset = 0
): LogFetchResult {
  return sliceViewerLines(
    logs.map((log) => ({
      line_number: log.sequence,
      content: `${log.stream}: ${log.message}`,
    })),
    offset
  )
}

export function agentSessionLogsToViewerResult(
  logs: AgentSessionLogEntryResponse[],
  offset = 0
): LogFetchResult {
  return sliceViewerLines(
    logs.map((log, index) => {
      const command = log.command_id ? ` command=${log.command_id}` : ''
      const job = log.job_id ? ` job=${log.job_id}` : ''
      return {
        line_number: index + 1,
        content: `${formatLogDate(log.created_at)} ${log.level}/${log.stream}${command}${job}: ${log.message}`,
      }
    }),
    offset
  )
}

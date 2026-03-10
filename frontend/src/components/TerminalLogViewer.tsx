import React, { useEffect, useRef, useState } from 'react'
import { Box, Button, Typography, Paper, Chip } from '@mui/material'
import { ContentCopy, Download } from '@mui/icons-material'
import { PlayCircle } from 'lucide-react'
import { toast } from 'react-hot-toast'
import { useTranslation } from 'react-i18next'

interface LogLine {
  line_number: number
  content: string
}

interface TerminalLogViewerProps {
  jobId: string
  status: string
  jobType?: string // 'backup', 'restore', 'check', 'compact', etc.
  showHeader?: boolean
  onFetchLogs: (offset: number) => Promise<{
    lines: LogLine[]
    total_lines: number
    has_more: boolean
  }>
}

// ---------------------------------------------------------------------------
// JSON syntax highlighting (VS Code Dark+ colour scheme)
// Applied only to lines that start with { or [ and are valid JSON.
// Non-JSON lines (plain borg output, hook script output) are returned as-is.
// ---------------------------------------------------------------------------

// Group 1: object key  (quoted string immediately before ":")
// Group 2: string value
// Group 3: number (integer or float, optional exponent)
// Group 4: keyword (true / false / null)
// Group 5: punctuation
const JSON_TOKEN_REGEX =
  /("(?:[^"\\]|\\.)*")\s*(?=:)|("(?:[^"\\]|\\.)*")|(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)|\b(true|false|null)\b|([{}[\],:])/g

function colorizeJsonLine(content: string): React.ReactNode {
  const trimmed = content.trim()
  if (!trimmed.startsWith('{') && !trimmed.startsWith('[')) return content
  try {
    JSON.parse(trimmed)
  } catch {
    return content
  }

  const parts: React.ReactNode[] = []
  let lastIndex = 0
  JSON_TOKEN_REGEX.lastIndex = 0

  let match: RegExpExecArray | null
  while ((match = JSON_TOKEN_REGEX.exec(content)) !== null) {
    // Emit any unmatched text before this token
    if (match.index > lastIndex) {
      parts.push(content.slice(lastIndex, match.index))
    }

    const [fullMatch, key, stringVal, num, keyword, punct] = match

    if (key) {
      // Colourize only the quoted key; emit trailing whitespace (before the
      // lookahead colon) without colour so spacing is preserved exactly.
      parts.push(
        <span key={match.index} style={{ color: '#9cdcfe' }}>
          {key}
        </span>
      )
      const trailingSpace = fullMatch.slice(key.length)
      if (trailingSpace) parts.push(trailingSpace)
    } else if (stringVal) {
      parts.push(
        <span key={match.index} style={{ color: '#ce9178' }}>
          {stringVal}
        </span>
      )
    } else if (num) {
      parts.push(
        <span key={match.index} style={{ color: '#b5cea8' }}>
          {num}
        </span>
      )
    } else if (keyword) {
      parts.push(
        <span key={match.index} style={{ color: '#569cd6' }}>
          {keyword}
        </span>
      )
    } else if (punct) {
      // Punctuation uses the terminal's default text colour — no span needed.
      parts.push(punct)
    }

    lastIndex = match.index + fullMatch.length
  }

  if (lastIndex < content.length) {
    parts.push(content.slice(lastIndex))
  }

  return <>{parts}</>
}

// ---------------------------------------------------------------------------
// Memoised single-line renderer — prevents re-rendering already-visible lines
// when new lines are appended to the log.
// ---------------------------------------------------------------------------
const MemoizedLogLine = React.memo(({ log }: { log: LogLine }) => (
  <Box sx={{ mb: 0.5 }}>
    <Typography
      component="span"
      sx={{
        color: '#858585',
        fontSize: '0.8rem',
        mr: 2,
        userSelect: 'none',
      }}
    >
      {log.line_number}
    </Typography>
    <Typography component="span" sx={{ color: '#d4d4d4' }}>
      {colorizeJsonLine(log.content)}
    </Typography>
  </Box>
))
MemoizedLogLine.displayName = 'MemoizedLogLine'

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------
export const TerminalLogViewer: React.FC<TerminalLogViewerProps> = ({
  jobId,
  status,
  jobType = 'backup',
  showHeader = true,
  onFetchLogs,
}) => {
  const { t } = useTranslation()
  const [logs, setLogs] = useState<LogLine[]>([])
  const logsRef = useRef<LogLine[]>([])
  const isLoadingRef = useRef(false)
  const logContainerRef = useRef<HTMLDivElement>(null)
  const [autoScroll, setAutoScroll] = useState(true)
  const [totalLines, setTotalLines] = useState(0)
  const [showingTail, setShowingTail] = useState(false)

  // Fetch logs on mount and poll while running
  useEffect(() => {
    const fetchLogs = async () => {
      if (isLoadingRef.current) return

      isLoadingRef.current = true
      try {
        // For running jobs, always fetch from offset 0 (backend returns tail)
        // For completed jobs, fetch next chunk based on current logs length
        const offset = status === 'running' ? 0 : logsRef.current.length
        const result = await onFetchLogs(offset)

        // For completed/failed jobs on initial load: if there are many lines, fetch the tail instead
        if (status !== 'running' && logsRef.current.length === 0 && result.total_lines > 500) {
          // Fetch last 500 lines
          const tailOffset = Math.max(0, result.total_lines - 500)
          const tailResult = await onFetchLogs(tailOffset)
          setLogs(tailResult.lines)
          logsRef.current = tailResult.lines
          setTotalLines(tailResult.total_lines)
          setShowingTail(true)
        } else {
          // Normal behavior
          if (result.lines.length > 0) {
            if (status === 'running') {
              // For running jobs, replace logs entirely (backend sends tail)
              setLogs(result.lines)
              logsRef.current = result.lines
            } else {
              // For completed jobs, append new lines
              setLogs((prev) => {
                const newLogs = [...prev, ...result.lines]
                logsRef.current = newLogs
                return newLogs
              })
            }
          }
          setTotalLines(result.total_lines)
        }
      } catch (error) {
        console.error('Failed to fetch logs:', error)
      } finally {
        isLoadingRef.current = false
      }
    }

    // Initial fetch
    fetchLogs()

    // Poll every 2 seconds while running
    if (status === 'running') {
      const interval = setInterval(fetchLogs, 2000)
      return () => clearInterval(interval)
    }
  }, [status, onFetchLogs])

  // Auto-scroll to bottom when new logs arrive
  useEffect(() => {
    if (autoScroll && logContainerRef.current) {
      logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight
    }
  }, [logs, autoScroll])

  // Handle scroll - disable auto-scroll if user scrolls up
  const handleScroll = () => {
    if (logContainerRef.current) {
      const { scrollTop, scrollHeight, clientHeight } = logContainerRef.current
      const isAtBottom = scrollHeight - scrollTop - clientHeight < 50
      setAutoScroll(isAtBottom)
    }
  }

  // Copy logs to clipboard
  const handleCopyLogs = () => {
    const logText = logs.map((log) => log.content).join('\n')
    navigator.clipboard.writeText(logText)
    toast.success(t('terminalLogViewer.toasts.logsCopied'))
  }

  // Download logs as file
  const handleDownloadLogs = () => {
    const logText = logs.map((log) => log.content).join('\n')
    const blob = new Blob([logText], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `backup_${jobId}_logs.txt`
    a.click()
    URL.revokeObjectURL(url)
    toast.success(t('terminalLogViewer.toasts.logsDownloaded'))
  }

  // Jump to beginning of logs
  const handleJumpToStart = async () => {
    try {
      const result = await onFetchLogs(0)
      setLogs(result.lines)
      logsRef.current = result.lines
      setShowingTail(false)
      if (logContainerRef.current) {
        logContainerRef.current.scrollTop = 0
      }
    } catch (error) {
      console.error('Failed to fetch logs from start:', error)
      toast.error(t('terminalLogViewer.toasts.failedToLoad'))
    }
  }

  return (
    <Box>
      {/* Header */}
      {showHeader && (
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
          <Box>
            <Typography variant="h6" fontWeight={600}>
              {t('terminalLogViewer.title')}
            </Typography>
            {status === 'running' && totalLines > 500 && (
              <Typography variant="caption" color="text.secondary">
                {t('terminalLogViewer.tailLabel', { total: totalLines.toLocaleString() })}
              </Typography>
            )}
            {status !== 'running' && totalLines > 0 && (
              <Typography variant="caption" color="text.secondary">
                {t('terminalLogViewer.linesLabel', { count: logs.length, total: totalLines })}
              </Typography>
            )}
          </Box>
          <Box sx={{ display: 'flex', gap: 1 }}>
            <Button
              size="small"
              startIcon={<ContentCopy sx={{ fontSize: 16 }} />}
              onClick={handleCopyLogs}
              disabled={logs.length === 0}
            >
              {t('terminalLogViewer.copyLogs')}
            </Button>
            <Button
              size="small"
              startIcon={<Download sx={{ fontSize: 16 }} />}
              onClick={handleDownloadLogs}
              disabled={logs.length === 0}
            >
              {t('terminalLogViewer.download')}
            </Button>
          </Box>
        </Box>
      )}

      {/* Status indicator above terminal */}
      {status === 'running' ? (
        <Box sx={{ mb: 1, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Chip
            icon={<PlayCircle size={16} />}
            label={t('terminalLogViewer.liveStreaming')}
            color="info"
            size="small"
            sx={{ fontWeight: 500 }}
          />
          {totalLines > 0 && (
            <Typography variant="caption" color="text.secondary">
              {t('terminalLogViewer.linesDisplayed', { count: logs.length })}
            </Typography>
          )}
        </Box>
      ) : showingTail && totalLines > 500 ? (
        <Box sx={{ mb: 1, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Chip
            label={t('terminalLogViewer.showingLast', { total: totalLines.toLocaleString() })}
            color="warning"
            size="small"
            sx={{ fontWeight: 500 }}
          />
          <Button size="small" onClick={handleJumpToStart} sx={{ minWidth: 'auto' }}>
            {t('terminalLogViewer.jumpToStart')}
          </Button>
        </Box>
      ) : null}

      {/* Terminal */}
      <Paper
        ref={logContainerRef}
        onScroll={handleScroll}
        sx={{
          bgcolor: '#1e1e1e',
          color: '#d4d4d4',
          fontFamily: 'Consolas, Monaco, "Courier New", monospace',
          fontSize: '0.875rem',
          p: 2,
          height: 500,
          overflowY: 'auto',
          overflowX: 'auto',
          whiteSpace: 'pre-wrap',
          wordBreak: 'break-all',
          '&::-webkit-scrollbar': {
            width: '8px',
          },
          '&::-webkit-scrollbar-track': {
            background: '#2d2d2d',
          },
          '&::-webkit-scrollbar-thumb': {
            background: '#555',
            borderRadius: '4px',
          },
          '&::-webkit-scrollbar-thumb:hover': {
            background: '#666',
          },
        }}
      >
        {logs.length === 0 ? (
          <Typography variant="body2" color="text.secondary">
            {status === 'running'
              ? t('terminalLogViewer.waitingForLogs')
              : t('terminalLogViewer.noLogsAvailable')}
          </Typography>
        ) : (
          logs.map((log) => (
            <MemoizedLogLine key={`${jobId}-${log.line_number}`} log={log} />
          ))
        )}

        {/* Running indicator */}
        {status === 'running' && (
          <Box sx={{ display: 'flex', alignItems: 'center', mt: 2 }}>
            <Box
              sx={{
                width: 8,
                height: 8,
                borderRadius: '50%',
                bgcolor: '#4ade80',
                mr: 1,
                animation: 'pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite',
                '@keyframes pulse': {
                  '0%, 100%': { opacity: 1 },
                  '50%': { opacity: 0.5 },
                },
              }}
            />
            <Typography sx={{ color: '#4ade80', fontSize: '0.875rem' }}>
              {t('terminalLog.inProgress', {
                type: jobType.charAt(0).toUpperCase() + jobType.slice(1),
              })}
            </Typography>
          </Box>
        )}
      </Paper>

      {/* Auto-scroll indicator */}
      {!autoScroll && status === 'running' && (
        <Box sx={{ mt: 1, textAlign: 'center' }}>
          <Button
            size="small"
            onClick={() => {
              setAutoScroll(true)
              if (logContainerRef.current) {
                logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight
              }
            }}
          >
            {t('terminalLogViewer.newLogsAvailable')}
          </Button>
        </Box>
      )}
    </Box>
  )
}

export default TerminalLogViewer

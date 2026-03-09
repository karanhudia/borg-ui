import React, { useEffect, useRef, useState, memo } from 'react'
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

// VS Code-style JSON syntax token colors
const JSON_COLORS = {
  key: '#9cdcfe',     // light blue  — property names
  string: '#ce9178',  // orange-red  — string values
  number: '#b5cea8',  // light green — numbers
  keyword: '#569cd6', // blue        — true / false / null
  punct: '#d4d4d4',   // grey-white  — { } [ ] : ,
}

// Colorize a JSON string by tokenizing it with a single-pass regex.
// Falls back to plain text if content is not valid JSON.
function colorizeJsonLine(text: string): React.ReactNode {
  const trimmed = text.trim()
  if (!trimmed.startsWith('{') && !trimmed.startsWith('[')) return text
  try {
    JSON.parse(trimmed)
  } catch {
    return text // not valid JSON — render as-is
  }

  // Tokenize: key strings (followed by :), value strings, numbers, keywords, punctuation
  const TOKEN_RE =
    /("(?:[^"\\]|\\.)*")(?=\s*:)|("(?:[^"\\]|\\.)*")|(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)|(true|false|null)|([{}[\],:])/g

  const parts: React.ReactNode[] = []
  let last = 0
  let m: RegExpExecArray | null

  while ((m = TOKEN_RE.exec(text)) !== null) {
    if (m.index > last) parts.push(text.slice(last, m.index))
    if (m[1])      parts.push(<span key={m.index} style={{ color: JSON_COLORS.key }}>{m[1]}</span>)
    else if (m[2]) parts.push(<span key={m.index} style={{ color: JSON_COLORS.string }}>{m[2]}</span>)
    else if (m[3]) parts.push(<span key={m.index} style={{ color: JSON_COLORS.number }}>{m[3]}</span>)
    else if (m[4]) parts.push(<span key={m.index} style={{ color: JSON_COLORS.keyword }}>{m[4]}</span>)
    else if (m[5]) parts.push(<span key={m.index} style={{ color: JSON_COLORS.punct }}>{m[5]}</span>)
    last = m.index + m[0].length
  }
  if (last < text.length) parts.push(text.slice(last))
  return <>{parts}</>
}

// Memoized log line to avoid re-rendering all lines on every new append
const LogLine = memo(function LogLine({
  lineNumber,
  content,
}: {
  lineNumber: number
  content: string
}) {
  return (
    <Box sx={{ mb: 0.5 }}>
      <Typography
        component="span"
        sx={{ color: '#858585', fontSize: '0.8rem', mr: 2, userSelect: 'none' }}
      >
        {lineNumber}
      </Typography>
      <Typography component="span" sx={{ color: '#d4d4d4' }}>
        {colorizeJsonLine(content)}
      </Typography>
    </Box>
  )
})

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
        // Always fetch from the current end of our accumulated log so we only
        // receive NEW lines.  This preserves pre-script output when borg output
        // starts arriving, and lets the user scroll back to read earlier lines.
        const offset = logsRef.current.length
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
          // Always append new lines (both running and completed)
          if (result.lines.length > 0) {
            setLogs((prev) => {
              const newLogs = [...prev, ...result.lines]
              logsRef.current = newLogs
              return newLogs
            })
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
            <LogLine
              key={`${jobId}-${log.line_number}`}
              lineNumber={log.line_number}
              content={log.content}
            />
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

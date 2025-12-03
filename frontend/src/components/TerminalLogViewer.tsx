import React, { useEffect, useRef, useState } from 'react'
import { Box, Button, Typography, Paper, Chip } from '@mui/material'
import { ContentCopy, Download } from '@mui/icons-material'
import { PlayCircle, CheckCircle } from 'lucide-react'
import { toast } from 'react-hot-toast'

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

export const TerminalLogViewer: React.FC<TerminalLogViewerProps> = ({
  jobId,
  status,
  jobType = 'backup',
  showHeader = true,
  onFetchLogs,
}) => {
  const [logs, setLogs] = useState<LogLine[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const logContainerRef = useRef<HTMLDivElement>(null)
  const [autoScroll, setAutoScroll] = useState(true)
  const [totalLines, setTotalLines] = useState(0)

  // Fetch logs on mount and poll while running
  useEffect(() => {
    const fetchLogs = async () => {
      if (isLoading) return

      setIsLoading(true)
      try {
        // For running jobs, always fetch from offset 0 (backend returns tail)
        // For completed jobs, fetch next chunk based on current logs length
        const offset = status === 'running' ? 0 : logs.length
        const result = await onFetchLogs(offset)

        if (result.lines.length > 0) {
          if (status === 'running') {
            // For running jobs, replace logs entirely (backend sends tail)
            setLogs(result.lines)
          } else {
            // For completed jobs, append new lines
            setLogs((prev) => [...prev, ...result.lines])
          }
        }
        setTotalLines(result.total_lines)
      } catch (error) {
        console.error('Failed to fetch logs:', error)
      } finally {
        setIsLoading(false)
      }
    }

    // Initial fetch
    fetchLogs()

    // Poll every 2 seconds while running
    if (status === 'running') {
      const interval = setInterval(fetchLogs, 2000)
      return () => clearInterval(interval)
    }
  }, [status])

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
    toast.success('Logs copied to clipboard')
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
    toast.success('Logs downloaded')
  }

  return (
    <Box>
      {/* Header */}
      {showHeader && (
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
          <Box>
            <Typography variant="h6" fontWeight={600}>
              Backup Logs
            </Typography>
            {status === 'running' && totalLines > 500 && (
              <Typography variant="caption" color="text.secondary">
                Showing last 500 of {totalLines} lines (live tail)
              </Typography>
            )}
            {status !== 'running' && totalLines > 0 && (
              <Typography variant="caption" color="text.secondary">
                {logs.length} of {totalLines} lines
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
              Copy Logs
            </Button>
            <Button
              size="small"
              startIcon={<Download sx={{ fontSize: 16 }} />}
              onClick={handleDownloadLogs}
              disabled={logs.length === 0}
            >
              Download
            </Button>
          </Box>
        </Box>
      )}

      {/* Status indicator above terminal */}
      <Box sx={{ mb: 1, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        {status === 'running' ? (
          <Chip
            icon={<PlayCircle size={16} />}
            label="Live Streaming (Last 500 lines)"
            color="info"
            size="small"
            sx={{ fontWeight: 500 }}
          />
        ) : (
          <Chip
            icon={<CheckCircle size={16} />}
            label="Completed Logs"
            color="success"
            size="small"
            variant="outlined"
            sx={{ fontWeight: 500 }}
          />
        )}
        {totalLines > 0 && (
          <Typography variant="caption" color="text.secondary">
            {logs.length} lines displayed
          </Typography>
        )}
      </Box>

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
            {status === 'running' ? 'Waiting for logs...' : 'No logs available'}
          </Typography>
        ) : (
          logs.map((log) => (
            <Box key={log.line_number} sx={{ mb: 0.5 }}>
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
                {log.content}
              </Typography>
            </Box>
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
              {jobType.charAt(0).toUpperCase() + jobType.slice(1)} in progress...
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
            New logs available - Click to scroll to bottom
          </Button>
        </Box>
      )}
    </Box>
  )
}

export default TerminalLogViewer

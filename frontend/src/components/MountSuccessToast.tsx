import { useState } from 'react'
import { Box, Typography, IconButton, alpha, useTheme } from '@mui/material'
import { HardDrive, Copy, Check, X } from 'lucide-react'
import { toast } from 'react-hot-toast'

interface MountSuccessToastProps {
  toastId: string
  command: string
}

export default function MountSuccessToast({ toastId, command }: MountSuccessToastProps) {
  const theme = useTheme()
  const isDark = theme.palette.mode === 'dark'
  const [copied, setCopied] = useState(false)

  const borderColor = isDark ? alpha('#fff', 0.1) : alpha('#000', 0.1)
  const surface = isDark ? '#1e2124' : '#ffffff'

  const handleCopy = () => {
    navigator.clipboard.writeText(command).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }

  return (
    <Box
      sx={{
        display: 'flex',
        flexDirection: 'column',
        gap: 1.25,
        p: 1.5,
        bgcolor: surface,
        border: '1px solid',
        borderColor,
        borderRadius: 2,
        boxShadow: isDark ? '0 8px 32px rgba(0,0,0,0.5)' : '0 8px 24px rgba(0,0,0,0.12)',
        maxWidth: 480,
        width: '100%',
      }}
    >
      {/* Header */}
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.25 }}>
        <Box
          sx={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            width: 30,
            height: 30,
            borderRadius: 1.25,
            bgcolor: alpha(theme.palette.success.main, isDark ? 0.18 : 0.1),
            color: theme.palette.success.main,
            flexShrink: 0,
          }}
        >
          <HardDrive size={15} />
        </Box>
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Typography
            variant="body2"
            fontWeight={600}
            sx={{ fontSize: '0.82rem', lineHeight: 1.3 }}
          >
            Archive Mounted
          </Typography>
          <Typography variant="caption" color="text.secondary" sx={{ fontSize: '0.72rem' }}>
            Access via Docker:
          </Typography>
        </Box>
        <IconButton
          size="small"
          onClick={() => toast.dismiss(toastId)}
          sx={{ color: 'text.disabled', flexShrink: 0, p: 0.25 }}
        >
          <X size={13} />
        </IconButton>
      </Box>

      {/* Command block */}
      <Box
        sx={{
          display: 'flex',
          alignItems: 'center',
          gap: 1,
          px: 1.25,
          py: 0.75,
          bgcolor: isDark ? alpha('#000', 0.4) : alpha('#000', 0.04),
          border: '1px solid',
          borderColor,
          borderRadius: 1.25,
        }}
      >
        <Typography
          component="code"
          sx={{
            flex: 1,
            fontSize: '0.7rem',
            fontFamily: 'ui-monospace, "Cascadia Code", "Fira Code", monospace',
            color: isDark ? alpha('#fff', 0.82) : alpha('#000', 0.8),
            wordBreak: 'break-all',
            lineHeight: 1.5,
          }}
        >
          {command}
        </Typography>
        <IconButton
          size="small"
          onClick={handleCopy}
          title={copied ? 'Copied!' : 'Copy command'}
          sx={{
            flexShrink: 0,
            color: copied ? 'success.main' : 'text.disabled',
            p: 0.5,
            transition: 'color 150ms',
            '&:hover': { color: copied ? 'success.main' : 'text.secondary' },
          }}
        >
          {copied ? <Check size={13} /> : <Copy size={13} />}
        </IconButton>
      </Box>
    </Box>
  )
}

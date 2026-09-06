import { Check, XCircle, Loader2, AlertTriangle, Circle, MinusCircle } from 'lucide-react'
import { useTheme } from '@mui/material'

const STATUS_ICON: Record<string, typeof Check> = {
  completed: Check,
  completed_with_warnings: AlertTriangle,
  running: Loader2,
  pending: Circle,
  queued: Circle,
  failed: XCircle,
  cancelled: XCircle,
  skipped: MinusCircle,
}

interface RunStatusIconProps {
  status: string
  size?: number
}

export default function RunStatusIcon({ status, size = 14 }: RunStatusIconProps) {
  const theme = useTheme()
  const Icon = STATUS_ICON[status] ?? AlertTriangle
  const color =
    {
      completed: theme.palette.success.main,
      completed_with_warnings: theme.palette.warning.main,
      running: theme.palette.primary.main,
      failed: theme.palette.error.main,
      cancelled: theme.palette.text.disabled,
      skipped: theme.palette.text.disabled,
    }[status] ?? theme.palette.text.secondary
  return (
    <Icon
      size={size}
      color={color}
      aria-hidden
      className={status === 'running' ? 'animate-spin' : undefined}
      style={{ flexShrink: 0 }}
    />
  )
}

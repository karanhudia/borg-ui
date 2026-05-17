import { CircularProgress } from '@mui/material'
import { AlertTriangle, Ban, CheckCircle2, MinusCircle, XCircle } from 'lucide-react'

import { isActiveRun } from '../runStatus'

interface RunStatusLeadIconProps {
  status?: string
  size?: number
}

export function RunStatusLeadIcon({ status, size = 13 }: RunStatusLeadIconProps) {
  if (status === 'completed') return <CheckCircle2 size={size} />
  if (status === 'completed_with_warnings' || status === 'partial' || status === 'skipped')
    return <AlertTriangle size={size} />
  if (status === 'failed') return <XCircle size={size} />
  if (status === 'cancelled') return <Ban size={size} />
  if (isActiveRun(status)) return <CircularProgress size={11} thickness={5} />
  return <MinusCircle size={size} />
}

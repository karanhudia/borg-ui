import { Box, Typography, Chip } from '@mui/material'
import type { ReactNode } from 'react'
import PipelineRepositoryCard from './PipelineRepositoryCard'
import type { OperationItem } from '../../types/operations'

interface PipelineStageColumnProps {
  stage: {
    key: string
    label: string
    operations: OperationItem[]
  }
  workerControl?: ReactNode
  onRetry?: (operationId: number) => void
}

export default function PipelineStageColumn({
  stage,
  workerControl,
  onRetry,
}: PipelineStageColumnProps) {
  return (
    <Box sx={{ minWidth: 200, flex: 1 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
        <Typography variant="subtitle2">{stage.label}</Typography>
        <Chip size="small" label={stage.operations.length} />
      </Box>
      {stage.operations.map((op) => (
        <PipelineRepositoryCard key={op.id} operation={op} onRetry={onRetry} />
      ))}
      {workerControl}
    </Box>
  )
}

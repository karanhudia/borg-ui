import { useEffect, useState } from 'react'
import type { SyntheticEvent } from 'react'
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Box,
  Stack,
  TextField,
  Typography,
} from '@mui/material'
import { ChevronDown, Network } from 'lucide-react'

export interface DiagnosticsTcpTargetLabels {
  summary: string
  description: string
  host: string
  hostHelper: string
  port: string
  portHelper?: string
  portError?: string
  timeout: string
  timeoutHelper: string
  timeoutError?: string
}

interface DiagnosticsTcpTargetFieldsProps {
  targetHost: string
  targetPort: string
  targetTimeout: string
  onTargetHostChange: (value: string) => void
  onTargetPortChange: (value: string) => void
  onTargetTimeoutChange: (value: string) => void
  hasTarget: boolean
  portInvalid: boolean
  timeoutInvalid: boolean
  timeoutInputProps: {
    min: number
    max: number
    step: number
  }
  labels: DiagnosticsTcpTargetLabels
  defaultExpanded?: boolean
}

export default function DiagnosticsTcpTargetFields({
  targetHost,
  targetPort,
  targetTimeout,
  onTargetHostChange,
  onTargetPortChange,
  onTargetTimeoutChange,
  hasTarget,
  portInvalid,
  timeoutInvalid,
  timeoutInputProps,
  labels,
  defaultExpanded = false,
}: DiagnosticsTcpTargetFieldsProps) {
  const [expanded, setExpanded] = useState(defaultExpanded)
  const [detailsMounted, setDetailsMounted] = useState(defaultExpanded)

  useEffect(() => {
    if (!defaultExpanded) return
    setExpanded(true)
    setDetailsMounted(true)
  }, [defaultExpanded])

  const handleExpandedChange = (_: SyntheticEvent, nextExpanded: boolean) => {
    if (nextExpanded) setDetailsMounted(true)
    setExpanded(nextExpanded)
  }

  return (
    <Accordion
      expanded={expanded}
      onChange={handleExpandedChange}
      disableGutters
      elevation={0}
      sx={{
        border: '1px solid',
        borderColor: 'divider',
        borderRadius: 1.5,
        '&:before': { display: 'none' },
        '&.Mui-expanded': { m: 0 },
      }}
    >
      <AccordionSummary
        expandIcon={<ChevronDown size={16} />}
        sx={{
          minHeight: 52,
          '&.Mui-expanded': { minHeight: 52 },
          '& .MuiAccordionSummary-content': {
            my: 1,
            minWidth: 0,
          },
          '& .MuiAccordionSummary-content.Mui-expanded': { my: 1 },
        }}
      >
        <Stack direction="row" spacing={1.25} alignItems="flex-start" sx={{ minWidth: 0 }}>
          <Box sx={{ color: 'text.secondary', display: 'flex', pt: 0.25 }}>
            <Network size={17} />
          </Box>
          <Box sx={{ minWidth: 0 }}>
            <Typography fontWeight={700} variant="body2">
              {labels.summary}
            </Typography>
            <Typography color="text.secondary" variant="caption">
              {labels.description}
            </Typography>
          </Box>
        </Stack>
      </AccordionSummary>

      {detailsMounted && (
        <AccordionDetails sx={{ pt: 0, px: 2, pb: 2 }}>
          <Box
            sx={{
              display: 'grid',
              gridTemplateColumns: { xs: '1fr', sm: 'minmax(0, 1fr) 120px 150px' },
              gap: 1.25,
            }}
          >
            <TextField
              label={labels.host}
              value={targetHost}
              onChange={(event) => onTargetHostChange(event.target.value)}
              placeholder="postgres.internal"
              size="small"
              helperText={labels.hostHelper}
            />
            <TextField
              label={labels.port}
              value={targetPort}
              onChange={(event) => onTargetPortChange(event.target.value)}
              placeholder="5432"
              size="small"
              type="number"
              inputProps={{ min: 1, max: 65535 }}
              required={hasTarget}
              error={portInvalid}
              helperText={portInvalid ? labels.portError : labels.portHelper}
            />
            <TextField
              label={labels.timeout}
              value={targetTimeout}
              onChange={(event) => onTargetTimeoutChange(event.target.value)}
              size="small"
              type="number"
              inputProps={timeoutInputProps}
              required={hasTarget}
              error={timeoutInvalid}
              helperText={timeoutInvalid ? labels.timeoutError : labels.timeoutHelper}
            />
          </Box>
        </AccordionDetails>
      )}
    </Accordion>
  )
}

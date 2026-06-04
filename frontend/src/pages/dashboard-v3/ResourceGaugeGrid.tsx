import type { ReactNode } from 'react'
import { Box } from '@mui/material'

export function ResourceGaugeGrid({ children }: { children: ReactNode }) {
  return (
    <Box
      data-testid="dashboard-resource-gauge-grid"
      style={{ gridTemplateColumns: 'repeat(3, minmax(0, 1fr))' }}
      sx={{
        display: 'grid',
        justifyItems: 'center',
        columnGap: 0.75,
      }}
    >
      {children}
    </Box>
  )
}

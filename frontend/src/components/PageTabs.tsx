import { ReactNode, SyntheticEvent } from 'react'
import { Box, Tabs } from '@mui/material'

export interface PageTabsProps {
  value: unknown
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  onChange: (event: SyntheticEvent, value: any) => void
  children: ReactNode
  ariaLabel?: string
  scrollable?: boolean
}

export default function PageTabs({
  value,
  onChange,
  children,
  ariaLabel,
  scrollable = false,
}: PageTabsProps) {
  return (
    <Box sx={{ borderBottom: 1, borderColor: 'divider', mb: 3 }}>
      <Tabs
        value={value}
        onChange={onChange}
        aria-label={ariaLabel}
        variant={scrollable ? 'scrollable' : 'standard'}
        scrollButtons={scrollable ? 'auto' : false}
      >
        {children}
      </Tabs>
    </Box>
  )
}

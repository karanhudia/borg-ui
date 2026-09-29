import { Box, Button } from '@mui/material'
import { Plus } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { useQuickStart } from './quickStartContext'

/** The sidebar's "New backup" action. Renders nothing when Quick Start is unavailable. */
export default function QuickStartSidebarButton({ onOpened }: { onOpened?: () => void }) {
  const { t } = useTranslation()
  const quickStart = useQuickStart()
  if (!quickStart) return null
  return (
    <Box sx={{ px: 1.5, pt: 1.5, pb: 0.5 }}>
      <Button
        fullWidth
        variant="contained"
        startIcon={<Plus size={16} />}
        onClick={() => {
          quickStart.openQuickStart()
          onOpened?.()
        }}
        sx={{ justifyContent: 'flex-start', px: 1.5 }}
      >
        {t('quickStart.newBackup')}
      </Button>
    </Box>
  )
}

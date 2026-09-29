import { Button, IconButton, Tooltip } from '@mui/material'
import { Plus } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { useQuickStart } from './quickStartContext'

/** The header's "New backup" action. Renders nothing when Quick Start is unavailable. */
export default function QuickStartHeaderButton() {
  const { t } = useTranslation()
  const quickStart = useQuickStart()
  if (!quickStart) return null
  const label = t('quickStart.title')
  return (
    <>
      <Button
        variant="contained"
        size="small"
        startIcon={<Plus size={16} />}
        onClick={quickStart.openQuickStart}
        sx={{ mr: 1.5, display: { xs: 'none', sm: 'inline-flex' }, whiteSpace: 'nowrap' }}
      >
        {label}
      </Button>
      <Tooltip title={label}>
        <IconButton
          color="primary"
          aria-label={label}
          onClick={quickStart.openQuickStart}
          sx={{ mr: 0.5, display: { xs: 'inline-flex', sm: 'none' } }}
        >
          <Plus size={20} />
        </IconButton>
      </Tooltip>
    </>
  )
}

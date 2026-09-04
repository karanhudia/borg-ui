import { useState } from 'react'
import { Button, Menu, MenuItem } from '@mui/material'
import { ChevronDown } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import type { RebuildStage } from '../../types/operations'

const STAGES: RebuildStage[] = ['stats', 'archives', 'history']

interface RebuildMenuProps {
  onSelect: (stage: RebuildStage) => void
}

export default function RebuildMenu({ onSelect }: RebuildMenuProps) {
  const { t } = useTranslation()
  const [anchorEl, setAnchorEl] = useState<HTMLElement | null>(null)

  return (
    <>
      <Button
        endIcon={<ChevronDown size={14} />}
        onClick={(e) => setAnchorEl(e.currentTarget)}
        variant="outlined"
        size="small"
      >
        {t('operations.background.rebuildFrom').replace(' from', '…')}
      </Button>
      <Menu anchorEl={anchorEl} open={!!anchorEl} onClose={() => setAnchorEl(null)}>
        {STAGES.map((stage) => (
          <MenuItem
            key={stage}
            onClick={() => {
              onSelect(stage)
              setAnchorEl(null)
            }}
          >
            {t(`operations.background.rebuildStage.${stage}`)}
          </MenuItem>
        ))}
      </Menu>
    </>
  )
}

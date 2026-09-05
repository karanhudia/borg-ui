import { useState } from 'react'
import { Button, Menu, MenuItem } from '@mui/material'
import { ChevronDown } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import PlanGate from '../shared/PlanGate'
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
        {t('operations.background.rebuildMenu')}
      </Button>
      <Menu anchorEl={anchorEl} open={!!anchorEl} onClose={() => setAnchorEl(null)}>
        {STAGES.map((stage) => {
          const item = (
            <MenuItem
              key={stage}
              onClick={() => {
                onSelect(stage)
                setAnchorEl(null)
              }}
            >
              {t(`operations.background.rebuildStage.${stage}`)}
            </MenuItem>
          )
          if (stage !== 'history') return item
          return (
            <PlanGate
              key={stage}
              feature="archive_history"
              disabled
              surface="background_work"
              operation="rebuild_history"
            >
              {item}
            </PlanGate>
          )
        })}
      </Menu>
    </>
  )
}

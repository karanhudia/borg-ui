import { useState } from 'react'
import { Button, IconButton, Menu, MenuItem, Tooltip } from '@mui/material'
import { ChevronDown, RotateCw } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import PlanGate from '../shared/PlanGate'
import type { RebuildStage } from '../../types/operations'

const STAGES: RebuildStage[] = ['stats', 'archives', 'history']

interface RebuildMenuProps {
  onSelect: (stage: RebuildStage) => void
  // `icon` is the quiet per-row form; `button` is the labelled form.
  variant?: 'button' | 'icon'
  label?: string
}

export default function RebuildMenu({ onSelect, variant = 'button', label }: RebuildMenuProps) {
  const { t } = useTranslation()
  const [anchorEl, setAnchorEl] = useState<HTMLElement | null>(null)
  const title = label ?? t('operations.background.rebuildMenu')

  return (
    <>
      {variant === 'icon' ? (
        <Tooltip title={title}>
          <IconButton size="small" aria-label={title} onClick={(e) => setAnchorEl(e.currentTarget)}>
            <RotateCw size={16} />
          </IconButton>
        </Tooltip>
      ) : (
        <Button
          endIcon={<ChevronDown size={14} />}
          onClick={(e) => setAnchorEl(e.currentTarget)}
          variant="outlined"
          size="small"
        >
          {title}
        </Button>
      )}
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

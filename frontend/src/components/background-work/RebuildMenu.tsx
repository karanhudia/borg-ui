import { useState } from 'react'
import {
  Button,
  IconButton,
  ListItemText,
  ListSubheader,
  Menu,
  MenuItem,
  Tooltip,
  Typography,
} from '@mui/material'
import { ChevronDown, RotateCw } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import PlanGate from '../shared/PlanGate'
import { REBUILD_STAGES } from './repositoryTrack'
import type { RebuildStage } from '../../types/operations'

interface RebuildMenuProps {
  onSelect: (stage: RebuildStage) => void
  // `icon` is the quiet per-row form; `button` is the labelled form.
  variant?: 'button' | 'icon'
  label?: string
}

// The three derived-data stages in the order the runner builds them, each
// with what it feeds and what it costs, so the choice explains itself
// where it is made.
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
      <Menu
        anchorEl={anchorEl}
        open={!!anchorEl}
        onClose={() => setAnchorEl(null)}
        slotProps={{ paper: { sx: { maxWidth: 360 } } }}
      >
        <ListSubheader disableSticky sx={{ lineHeight: 1.4, py: 1, whiteSpace: 'normal' }}>
          <Typography variant="caption" sx={{ color: 'text.secondary' }}>
            {t('operations.background.rebuildMenuHint')}
          </Typography>
        </ListSubheader>
        {REBUILD_STAGES.map((stage, index) => {
          const item = (
            <MenuItem
              key={stage}
              onClick={() => {
                onSelect(stage)
                setAnchorEl(null)
              }}
              sx={{ alignItems: 'flex-start', whiteSpace: 'normal' }}
            >
              <ListItemText
                primary={`${index + 1}. ${t(`operations.background.stages.${stage}.title`)}`}
                secondary={`${t(`operations.background.stages.${stage}.what`)} ${t(`operations.background.stages.${stage}.cost`)}`}
                slotProps={{
                  primary: { sx: { fontWeight: 600 } },
                  secondary: { sx: { fontSize: '0.75rem' } },
                }}
              />
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

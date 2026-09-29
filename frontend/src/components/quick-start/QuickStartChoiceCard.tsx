import type { ReactNode } from 'react'
import { Box, ButtonBase, Stack, Typography, alpha } from '@mui/material'
import { CheckCircle2 } from 'lucide-react'

interface QuickStartChoiceCardProps {
  icon: ReactNode
  title: ReactNode
  description: ReactNode
  selected: boolean
  onSelect: () => void
  disabled?: boolean
  badge?: ReactNode
}

/** One option in a Quick Start radio group. Place inside `role="radiogroup"`. */
export default function QuickStartChoiceCard({
  icon,
  title,
  description,
  selected,
  onSelect,
  disabled = false,
  badge,
}: QuickStartChoiceCardProps) {
  return (
    <ButtonBase
      role="radio"
      aria-checked={selected}
      disabled={disabled}
      onClick={onSelect}
      focusRipple
      sx={(theme) => ({
        display: 'flex',
        width: '100%',
        textAlign: 'left',
        alignItems: 'flex-start',
        gap: 1.5,
        p: 2,
        borderRadius: 2,
        border: '1px solid',
        borderColor: selected ? 'primary.main' : 'divider',
        bgcolor: selected
          ? alpha(theme.palette.primary.main, theme.palette.mode === 'dark' ? 0.16 : 0.06)
          : 'transparent',
        opacity: disabled ? 0.6 : 1,
        transition: 'border-color 150ms ease-out, background-color 150ms ease-out',
        '&:hover': disabled
          ? undefined
          : { borderColor: selected ? 'primary.main' : 'text.secondary' },
        '&.Mui-focusVisible': {
          outline: `2px solid ${theme.palette.primary.main}`,
          outlineOffset: 2,
        },
      })}
    >
      <Box
        sx={{
          display: 'flex',
          flexShrink: 0,
          mt: 0.25,
          color: selected ? 'primary.main' : 'text.secondary',
        }}
      >
        {icon}
      </Box>
      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Stack direction="row" spacing={1} sx={{ alignItems: 'center', flexWrap: 'wrap' }}>
          <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
            {title}
          </Typography>
          {badge}
        </Stack>
        <Typography variant="body2" sx={{ color: 'text.secondary', mt: 0.25 }}>
          {description}
        </Typography>
      </Box>
      <Box
        aria-hidden
        sx={{
          display: 'flex',
          flexShrink: 0,
          color: 'primary.main',
          visibility: selected ? 'visible' : 'hidden',
        }}
      >
        <CheckCircle2 size={18} />
      </Box>
    </ButtonBase>
  )
}

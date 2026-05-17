import React from 'react'
import { Link } from 'react-router-dom'
import { Box, ListItem, ListItemButton, ListItemIcon, ListItemText, Tooltip } from '@mui/material'
import { Lock } from 'lucide-react'

interface NavItemProps {
  name: string
  href: string
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  icon: React.ComponentType<any>
  isActive: boolean
  isEnabled: boolean
  disabledReason?: string
  navLabel: (name: string) => string
  disabled?: boolean
  /** Optional trailing slot (e.g. a small "NEW" badge). */
  badge?: React.ReactNode
}

export default function NavItem({
  name,
  href,
  icon: Icon,
  isActive,
  isEnabled,
  disabledReason,
  navLabel,
  badge,
}: NavItemProps) {
  const button = (
    <ListItemButton
      component={isEnabled ? Link : 'div'}
      to={isEnabled ? href : undefined}
      selected={isActive}
      disabled={!isEnabled}
      aria-current={isActive ? 'page' : undefined}
      sx={{
        pl: 2,
        pr: 1.5,
        py: 0.625,
        minHeight: 36,
        borderLeft: '2px solid transparent',
        borderRadius: 0,
        transition: 'background-color 150ms ease, border-color 150ms ease',
        '&.Mui-selected': {
          backgroundColor: 'rgba(5,150,105,0.08)',
          borderLeftColor: '#059669',
          '&:hover': { backgroundColor: 'rgba(5,150,105,0.12)' },
          '& .MuiListItemIcon-root': { color: '#34d399' },
        },
        '&:hover': { backgroundColor: 'rgba(255,255,255,0.04)' },
        '&.Mui-disabled': { opacity: 0.5, cursor: 'not-allowed' },
      }}
    >
      <ListItemIcon sx={{ color: isActive ? '#34d399' : 'text.secondary', minWidth: 32 }}>
        {isEnabled ? <Icon size={18} /> : <Lock size={18} />}
      </ListItemIcon>
      <ListItemText
        primary={navLabel(name)}
        primaryTypographyProps={{
          fontSize: '0.8125rem',
          fontWeight: isActive ? 500 : 400,
          color: isActive ? 'text.primary' : isEnabled ? 'text.secondary' : 'text.disabled',
        }}
      />
      {badge && <Box sx={{ ml: 1, display: 'flex', alignItems: 'center' }}>{badge}</Box>}
    </ListItemButton>
  )

  return (
    <ListItem disablePadding>
      {!isEnabled && disabledReason ? (
        <Tooltip title={disabledReason} arrow placement="right">
          <Box sx={{ width: '100%' }}>{button}</Box>
        </Tooltip>
      ) : (
        button
      )}
    </ListItem>
  )
}

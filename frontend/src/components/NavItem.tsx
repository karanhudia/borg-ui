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
}

export default function NavItem({
  name,
  href,
  icon: Icon,
  isActive,
  isEnabled,
  disabledReason,
  navLabel,
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
        '&.Mui-selected': {
          backgroundColor: 'primary.main',
          color: 'white',
          '&:hover': { backgroundColor: 'primary.dark' },
          '& .MuiListItemIcon-root': { color: 'white' },
        },
        '&.Mui-disabled': { opacity: 0.5, cursor: 'not-allowed' },
      }}
    >
      <ListItemIcon sx={{ color: isActive ? 'white' : 'text.secondary', minWidth: 32 }}>
        {isEnabled ? <Icon size={18} /> : <Lock size={18} />}
      </ListItemIcon>
      <ListItemText
        primary={navLabel(name)}
        primaryTypographyProps={{
          fontSize: '0.8125rem',
          fontWeight: isActive ? 600 : 400,
          color: isActive ? 'white' : isEnabled ? 'inherit' : 'text.disabled',
        }}
      />
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

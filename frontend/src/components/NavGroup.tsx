import React from 'react'
import { Link } from 'react-router-dom'
import {
  Box,
  Collapse,
  List,
  ListItem,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  Tooltip,
} from '@mui/material'
import { ChevronDown, ChevronRight } from 'lucide-react'

interface SubItem {
  name: string
  href?: string
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  icon: React.ComponentType<any>
  disabled?: boolean
}

interface NavGroupProps {
  name: string
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  icon: React.ComponentType<any>
  subItems: SubItem[]
  isExpanded: boolean
  onToggle: () => void
  currentPath: string
  navLabel: (name: string) => string
}

export default function NavGroup({
  name,
  icon: Icon,
  subItems,
  isExpanded,
  onToggle,
  currentPath,
  navLabel,
}: NavGroupProps) {
  const isAnySubItemActive = subItems.some((sub) => sub.href && currentPath.startsWith(sub.href))

  return (
    <React.Fragment>
      <ListItem disablePadding>
        <ListItemButton
          onClick={onToggle}
          sx={{
            pl: 2,
            pr: 1.5,
            py: 0.625,
            minHeight: 36,
            borderLeft: '2px solid transparent',
            borderRadius: 0,
            borderLeftColor: isAnySubItemActive ? '#059669' : 'transparent',
            backgroundColor: isAnySubItemActive ? 'rgba(5,150,105,0.06)' : 'transparent',
            transition: 'background-color 150ms ease, border-color 150ms ease',
            '&:hover': { backgroundColor: 'rgba(255,255,255,0.04)' },
          }}
        >
          <ListItemIcon
            sx={{
              color: isAnySubItemActive ? '#34d399' : 'text.secondary',
              minWidth: 32,
            }}
          >
            <Icon size={18} />
          </ListItemIcon>
          <ListItemText
            primary={navLabel(name)}
            primaryTypographyProps={{
              fontSize: '0.8125rem',
              fontWeight: isAnySubItemActive ? 500 : 400,
              color: isAnySubItemActive ? 'text.primary' : 'text.secondary',
            }}
          />
          {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </ListItemButton>
      </ListItem>

      <Collapse in={isExpanded} timeout="auto" unmountOnExit>
        <List
          component="div"
          disablePadding
          sx={{
            position: 'relative',
            '&::before': {
              content: '""',
              position: 'absolute',
              left: '24px',
              top: 0,
              bottom: 0,
              width: '1px',
              backgroundColor: isAnySubItemActive ? 'rgba(5,150,105,0.28)' : 'divider',
              opacity: isAnySubItemActive ? 1 : 0.5,
            },
          }}
        >
          {subItems.map((subItem) => {
            const isActive = subItem.href ? currentPath.startsWith(subItem.href) : false
            const SubIcon = subItem.icon
            const isDisabled = subItem.disabled === true

            const button = (
              <ListItemButton
                component={isDisabled ? 'div' : Link}
                to={isDisabled ? undefined : (subItem.href ?? '#')}
                selected={isActive}
                aria-current={isActive ? 'page' : undefined}
                sx={{
                  pl: 5.5,
                  pr: 1.5,
                  py: 0.5,
                  minHeight: 32,
                  borderLeft: '2px solid transparent',
                  borderRadius: 0,
                  transition: 'background-color 150ms ease, border-color 150ms ease',
                  ...(isDisabled ? { opacity: 0.4, pointerEvents: 'none' } : {}),
                  '&.Mui-selected': {
                    backgroundColor: 'rgba(5,150,105,0.08)',
                    borderLeftColor: '#059669',
                    '&:hover': { backgroundColor: 'rgba(5,150,105,0.12)' },
                    '& .MuiListItemIcon-root': { color: '#34d399' },
                  },
                  '&:hover': { backgroundColor: 'rgba(255,255,255,0.04)' },
                }}
              >
                <ListItemIcon sx={{ color: isActive ? '#34d399' : 'text.secondary', minWidth: 28 }}>
                  <SubIcon size={15} />
                </ListItemIcon>
                <ListItemText
                  primary={navLabel(subItem.name)}
                  primaryTypographyProps={{
                    fontSize: '0.8rem',
                    fontWeight: isActive ? 500 : 400,
                    color: isActive ? 'text.primary' : 'text.secondary',
                  }}
                />
              </ListItemButton>
            )

            return (
              <ListItem key={subItem.name} disablePadding>
                {isDisabled ? (
                  <Tooltip title="Coming soon" arrow placement="right">
                    <Box sx={{ width: '100%' }}>{button}</Box>
                  </Tooltip>
                ) : (
                  button
                )}
              </ListItem>
            )
          })}
        </List>
      </Collapse>
    </React.Fragment>
  )
}

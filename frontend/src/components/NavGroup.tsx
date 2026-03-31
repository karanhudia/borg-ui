import React from 'react'
import { Link } from 'react-router-dom'
import { Collapse, List, ListItem, ListItemButton, ListItemIcon, ListItemText } from '@mui/material'
import { ChevronDown, ChevronRight } from 'lucide-react'

interface SubItem {
  name: string
  href: string
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  icon: React.ComponentType<any>
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
  const isAnySubItemActive = subItems.some((sub) => currentPath.startsWith(sub.href))

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
            '&:hover': { backgroundColor: 'action.hover' },
          }}
        >
          <ListItemIcon
            sx={{
              color: isAnySubItemActive ? 'primary.main' : 'text.secondary',
              minWidth: 32,
            }}
          >
            <Icon size={18} />
          </ListItemIcon>
          <ListItemText
            primary={navLabel(name)}
            primaryTypographyProps={{
              fontSize: '0.8125rem',
              fontWeight: isAnySubItemActive ? 600 : 400,
              color: isAnySubItemActive ? 'primary.main' : 'inherit',
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
              backgroundColor: 'divider',
              opacity: 0.5,
            },
          }}
        >
          {subItems.map((subItem) => {
            const isActive = currentPath.startsWith(subItem.href)
            const SubIcon = subItem.icon

            return (
              <ListItem key={subItem.name} disablePadding>
                <ListItemButton
                  component={Link}
                  to={subItem.href}
                  selected={isActive}
                  aria-current={isActive ? 'page' : undefined}
                  sx={{
                    pl: 6,
                    pr: 1.5,
                    py: 0.5,
                    minHeight: 32,
                    '&.Mui-selected': {
                      backgroundColor: 'primary.main',
                      color: 'white',
                      '&:hover': { backgroundColor: 'primary.dark' },
                      '& .MuiListItemIcon-root': { color: 'white' },
                    },
                    '&:hover': {
                      backgroundColor: isActive ? 'primary.main' : 'action.hover',
                    },
                  }}
                >
                  <ListItemIcon sx={{ color: isActive ? 'white' : 'text.secondary', minWidth: 28 }}>
                    <SubIcon size={16} />
                  </ListItemIcon>
                  <ListItemText
                    primary={navLabel(subItem.name)}
                    primaryTypographyProps={{
                      fontSize: '0.8125rem',
                      fontWeight: isActive ? 500 : 400,
                      color: isActive ? 'white' : 'inherit',
                    }}
                  />
                </ListItemButton>
              </ListItem>
            )
          })}
        </List>
      </Collapse>
    </React.Fragment>
  )
}

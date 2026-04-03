import { useState } from 'react'
import {
  AppBar,
  Avatar,
  Box,
  Divider,
  IconButton,
  Popover,
  Toolbar,
  Typography,
} from '@mui/material'
import { alpha, useTheme as useMuiTheme } from '@mui/material/styles'
import { ChevronDown, LogOut, Menu, Shield } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useAuth } from '../hooks/useAuth'
import { formatRoleLabel } from '../utils/rolePresentation'

const drawerWidth = 240
const headerHeight = 64

interface AppHeaderProps {
  onToggleMobileMenu: () => void
}

function getRoleBadgeStyles(roleLabel: string, isDark: boolean) {
  if (roleLabel === 'Admin') {
    return {
      backgroundColor: isDark ? 'rgba(5,150,105,0.15)' : 'rgba(5,150,105,0.08)',
      color: isDark ? '#6ee7b7' : '#059669',
    }
  }

  if (roleLabel === 'Operator') {
    return {
      backgroundColor: isDark ? 'rgba(59,130,246,0.15)' : 'rgba(59,130,246,0.08)',
      color: isDark ? '#93bbfd' : '#2563eb',
    }
  }

  return {
    backgroundColor: isDark ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.04)',
    color: 'text.secondary',
  }
}

export default function AppHeader({ onToggleMobileMenu }: AppHeaderProps) {
  const { t } = useTranslation()
  const { user, logout } = useAuth()
  const muiTheme = useMuiTheme()
  const isDark = muiTheme.palette.mode === 'dark'
  const [anchorEl, setAnchorEl] = useState<HTMLElement | null>(null)
  const open = Boolean(anchorEl)

  const displayName = user?.full_name?.trim() || user?.username || user?.email || ''
  const roleLabel = formatRoleLabel(user?.role)
  const roleBadgeStyles = getRoleBadgeStyles(roleLabel, isDark)
  const companyLabel =
    user?.deployment_type === 'enterprise'
      ? user.enterprise_name?.trim() || 'Enterprise deployment'
      : ''

  const initials = displayName
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase() || '')
    .join('')

  return (
    <AppBar
      position="fixed"
      elevation={0}
      sx={{
        width: { sm: `calc(100% - ${drawerWidth}px)` },
        ml: { sm: `${drawerWidth}px` },
        backgroundColor: alpha(muiTheme.palette.background.default, isDark ? 0.9 : 0.82),
        color: 'text.primary',
        backdropFilter: 'blur(14px)',
        borderBottom: `1px solid ${alpha(muiTheme.palette.divider, isDark ? 0.7 : 0.5)}`,
      }}
    >
      <Toolbar
        sx={{
          px: { xs: 2, sm: 3 },
          minHeight: { xs: headerHeight, sm: headerHeight },
          height: headerHeight,
        }}
      >
        <IconButton
          color="inherit"
          aria-label="open drawer"
          edge="start"
          onClick={onToggleMobileMenu}
          sx={{ mr: 2, display: { sm: 'none' } }}
        >
          <Menu size={22} />
        </IconButton>

        <Box sx={{ flexGrow: 1 }} />

        <Box
          component="button"
          onClick={(e: React.MouseEvent<HTMLButtonElement>) => setAnchorEl(e.currentTarget)}
          aria-label="User menu"
          aria-haspopup="true"
          aria-expanded={open}
          sx={{
            display: 'flex',
            alignItems: 'center',
            gap: 1,
            px: 1,
            py: 0.5,
            border: 'none',
            borderRadius: 2,
            cursor: 'pointer',
            bgcolor: open
              ? isDark
                ? 'rgba(255,255,255,0.08)'
                : 'rgba(0,0,0,0.05)'
              : 'transparent',
            transition: 'background-color 150ms',
            '&:hover': {
              bgcolor: isDark ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.04)',
            },
            color: 'inherit',
            fontFamily: 'inherit',
          }}
        >
          <Avatar
            sx={{
              width: 32,
              height: 32,
              fontSize: '0.8rem',
              fontWeight: 700,
              bgcolor: 'rgba(5,150,105,0.15)',
              color: '#34d399',
              border: '1.5px solid rgba(5,150,105,0.3)',
            }}
          >
            {initials}
          </Avatar>
          <Typography
            variant="body2"
            noWrap
            sx={{
              fontWeight: 600,
              maxWidth: { xs: 120, sm: 200 },
              display: { xs: 'none', sm: 'block' },
              fontSize: '0.875rem',
            }}
          >
            {displayName}
          </Typography>
          <ChevronDown
            size={15}
            style={{
              opacity: 0.5,
              transition: 'transform 150ms',
              transform: open ? 'rotate(180deg)' : 'rotate(0deg)',
            }}
          />
        </Box>

        <Popover
          open={open}
          anchorEl={anchorEl}
          onClose={() => setAnchorEl(null)}
          anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
          transformOrigin={{ vertical: 'top', horizontal: 'right' }}
          slotProps={{
            paper: {
              sx: {
                mt: 1,
                width: 240,
                borderRadius: 3,
                border: `1px solid ${alpha(muiTheme.palette.divider, isDark ? 0.4 : 0.2)}`,
                boxShadow: isDark
                  ? '0 16px 48px rgba(0,0,0,0.55)'
                  : '0 16px 48px rgba(15,23,42,0.14)',
                bgcolor: muiTheme.palette.background.paper,
                overflow: 'hidden',
              },
            },
          }}
        >
          <Box sx={{ px: 2, py: 1.5 }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75 }}>
              <Typography variant="body2" noWrap sx={{ fontWeight: 700 }}>
                {displayName}
              </Typography>
              {roleLabel && (
                <Box
                  sx={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: 0.35,
                    fontSize: '0.65rem',
                    fontWeight: 600,
                    px: 0.75,
                    py: 0.2,
                    borderRadius: 1,
                    bgcolor: roleBadgeStyles.backgroundColor,
                    color: roleBadgeStyles.color,
                    flexShrink: 0,
                  }}
                >
                  <Shield size={10} />
                  {roleLabel}
                </Box>
              )}
            </Box>
            <Typography
              variant="caption"
              noWrap
              sx={{ color: 'text.secondary', display: 'block', mt: 0.25 }}
            >
              {companyLabel || 'Individual deployment'}
            </Typography>
          </Box>

          <Divider />

          <Box
            component="button"
            onClick={() => {
              setAnchorEl(null)
              logout()
            }}
            sx={{
              display: 'flex',
              alignItems: 'center',
              gap: 1,
              width: '100%',
              px: 2,
              py: 1.25,
              border: 'none',
              bgcolor: 'transparent',
              color: isDark ? '#f87171' : '#dc2626',
              cursor: 'pointer',
              fontFamily: 'inherit',
              fontSize: '0.8125rem',
              fontWeight: 500,
              transition: 'background-color 150ms',
              '&:hover': {
                bgcolor: isDark ? 'rgba(248,113,113,0.08)' : 'rgba(220,38,38,0.05)',
              },
            }}
          >
            <LogOut size={15} />
            {t('navigation.logout')}
          </Box>
        </Popover>
      </Toolbar>
    </AppBar>
  )
}

import { AppBar, Box, Button, IconButton, Toolbar, Typography } from '@mui/material'
import { alpha, useTheme as useMuiTheme } from '@mui/material/styles'
import { LogOut, Menu } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useAuth } from '../hooks/useAuth'

const drawerWidth = 240

interface AppHeaderProps {
  onToggleMobileMenu: () => void
}

export default function AppHeader({ onToggleMobileMenu }: AppHeaderProps) {
  const { t } = useTranslation()
  const { user, logout } = useAuth()
  const muiTheme = useMuiTheme()
  const isDark = muiTheme.palette.mode === 'dark'

  const displayName = user?.full_name?.trim() || user?.username || user?.email || ''
  const roleLabel =
    user?.role === 'admin' ? 'Admin' : user?.role === 'operator' ? 'Operator' : 'Viewer'
  const secondaryLabel = user?.full_name?.trim()
    ? roleLabel
    : user?.email && user.email !== displayName
      ? `${roleLabel} • ${user.email}`
      : roleLabel

  return (
    <AppBar
      position="fixed"
      sx={{
        width: { sm: `calc(100% - ${drawerWidth}px)` },
        ml: { sm: `${drawerWidth}px` },
        backgroundColor: alpha(muiTheme.palette.background.default, isDark ? 0.9 : 0.82),
        color: 'text.primary',
        boxShadow: isDark ? '0 8px 24px rgba(0,0,0,0.28)' : '0 8px 24px rgba(15,23,42,0.06)',
        backdropFilter: 'blur(14px)',
        borderBottom: `1px solid ${alpha(muiTheme.palette.divider, isDark ? 0.7 : 0.5)}`,
      }}
    >
      <Toolbar sx={{ px: { xs: 2, sm: 3 }, pr: { xs: 2, sm: 6 } }}>
        <IconButton
          color="inherit"
          aria-label="open drawer"
          edge="start"
          onClick={onToggleMobileMenu}
          sx={{ mr: 2, display: { sm: 'none' } }}
        >
          <Menu size={24} />
        </IconButton>
        <Box sx={{ flexGrow: 1 }} />
        <Box sx={{ display: 'flex', alignItems: 'center', gap: { xs: 1, md: 2 } }}>
          <Box
            sx={{
              minWidth: 0,
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'flex-end',
              pr: { xs: 0.25, md: 0.5 },
            }}
          >
            <Typography variant="subtitle2" sx={{ fontWeight: 700, lineHeight: 1.2 }} noWrap>
              {displayName}
            </Typography>
            <Typography
              variant="caption"
              color="text.secondary"
              noWrap
              sx={{ maxWidth: { xs: 120, md: 280 } }}
            >
              {secondaryLabel}
            </Typography>
          </Box>
          <Button
            variant="outlined"
            size="small"
            startIcon={<LogOut size={18} />}
            onClick={logout}
            sx={{
              textTransform: 'none',
              borderColor: 'divider',
              color: 'text.primary',
              borderRadius: 999,
              minWidth: 0,
              px: { xs: 1.25, md: 1.5 },
              py: 0.625,
              bgcolor: alpha(muiTheme.palette.background.paper, isDark ? 0.42 : 0.72),
              '&:hover': {
                borderColor: 'rgba(255,255,255,0.18)',
                backgroundColor: isDark ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.04)',
              },
            }}
          >
            {t('navigation.logout')}
          </Button>
        </Box>
      </Toolbar>
    </AppBar>
  )
}

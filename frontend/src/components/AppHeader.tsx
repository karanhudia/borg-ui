import { type MouseEvent, useState } from 'react'
import { AppBar, Avatar, Box, IconButton, Popover, Toolbar, Typography } from '@mui/material'
import { alpha, useTheme as useMuiTheme } from '@mui/material/styles'
import {
  Bell,
  ChevronDown,
  ChevronRight,
  LogOut,
  Menu,
  Palette,
  Shield,
  Sparkles,
  User,
} from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useAuth } from '../hooks/useAuth'
import { useAnalytics } from '../hooks/useAnalytics'
import { formatRoleLabel } from '../utils/rolePresentation'
import PlanInfoDrawer from './PlanInfoDrawer'
import { usePlan } from '../hooks/usePlan'
import { useNavigate } from 'react-router-dom'
import { PLAN_LABEL } from '../core/features'
import { getProfileMenuColors, getRoleBadgeStyles } from './profileMenuColors'

const drawerWidth = 240
const headerHeight = 64

interface AppHeaderProps {
  onToggleMobileMenu: () => void
}

export default function AppHeader({ onToggleMobileMenu }: AppHeaderProps) {
  const { t } = useTranslation()
  const { user, logout } = useAuth()
  const { trackAuth, trackNavigation, trackPlan, EventAction } = useAnalytics()
  const muiTheme = useMuiTheme()
  const isDark = muiTheme.palette.mode === 'dark'
  const menuColors = getProfileMenuColors(muiTheme)
  const { plan, features, entitlement } = usePlan()
  const [anchorEl, setAnchorEl] = useState<HTMLElement | null>(null)
  const [planDrawerOpen, setPlanDrawerOpen] = useState(false)
  const open = Boolean(anchorEl)
  const navigate = useNavigate()

  const displayName = user?.full_name?.trim() || user?.username || user?.email || ''
  const roleLabel = formatRoleLabel(user?.role)
  const roleBadgeStyles = getRoleBadgeStyles(roleLabel, isDark)
  const companyLabel =
    user?.deployment_type === 'enterprise'
      ? user.enterprise_name?.trim() || 'Enterprise deployment'
      : ''

  const isFullAccess = entitlement?.is_full_access && entitlement.status === 'active'
  const planLabel = isFullAccess ? t('plan.fullAccessLabel', 'Full Access') : PLAN_LABEL[plan]
  const planDescription =
    plan === 'enterprise' || isFullAccess
      ? t('plan.descriptionEnterprise', 'All Enterprise features unlocked')
      : plan === 'pro'
        ? t('plan.descriptionPro', 'All Pro features unlocked')
        : t('plan.descriptionCommunity', 'Core backup features included')

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
          onClick={(e: MouseEvent<HTMLButtonElement>) => {
            setAnchorEl(e.currentTarget)
            trackNavigation(EventAction.VIEW, { surface: 'user_menu' })
          }}
          aria-label="User menu"
          aria-haspopup="true"
          aria-expanded={open}
          sx={{
            display: 'flex',
            alignItems: 'center',
            gap: 1,
            px: 1,
            py: 1,
            border: 'none',
            borderRadius: '12px',
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
              borderRadius: '8px',
              bgcolor: menuColors.avatar.surface,
              color: menuColors.avatar.color,
              border: `1.5px solid ${menuColors.avatar.border}`,
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
                width: 300,
                borderRadius: 3,
                border: `1px solid ${alpha(muiTheme.palette.divider, isDark ? 0.4 : 0.2)}`,
                boxShadow: isDark
                  ? '0 16px 48px rgba(0,0,0,0.55)'
                  : '0 16px 48px rgba(15,23,42,0.14)',
                bgcolor: menuColors.menuSurface,
                overflow: 'hidden',
              },
            },
          }}
        >
          {/* ── 1. Hero header ── */}
          <Box
            sx={{
              px: 1.75,
              py: 1.5,
              display: 'flex',
              alignItems: 'center',
              gap: 1.5,
              bgcolor: menuColors.heroSurface,
              borderBottom: `1px solid ${alpha(muiTheme.palette.divider, 0.06)}`,
            }}
          >
            <Avatar
              sx={{
                width: 46,
                height: 46,
                fontSize: '1rem',
                fontWeight: 800,
                borderRadius: '12px',
                bgcolor: menuColors.avatar.surface,
                color: menuColors.avatar.color,
                border: `1.5px solid ${menuColors.avatar.border}`,
              }}
            >
              {initials}
            </Avatar>
            <Box sx={{ minWidth: 0 }}>
              <Typography variant="body2" noWrap sx={{ fontWeight: 700, fontSize: '0.875rem' }}>
                {displayName}
              </Typography>
              <Typography
                variant="caption"
                noWrap
                sx={{ color: 'text.secondary', display: 'block', mt: 0.25 }}
              >
                {companyLabel || t('settings.account.profile.deployment.individual', 'Individual')}
              </Typography>
              {roleLabel && (
                <Box
                  sx={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: 0.4,
                    fontSize: '0.57rem',
                    fontWeight: 700,
                    textTransform: 'uppercase',
                    letterSpacing: '0.04em',
                    px: 0.75,
                    py: 0.25,
                    mt: 0.75,
                    borderRadius: 0.75,
                    bgcolor: roleBadgeStyles.backgroundColor,
                    color: roleBadgeStyles.color,
                  }}
                >
                  <Shield size={9} />
                  {roleLabel}
                </Box>
              )}
            </Box>
          </Box>

          {/* ── 2. Plan card ── */}
          <Box sx={{ px: 1.25, py: 1.125 }}>
            <Box
              component="button"
              onClick={() => {
                setAnchorEl(null)
                trackPlan(EventAction.VIEW, { surface: 'user_menu', operation: 'open_drawer' })
                setPlanDrawerOpen(true)
              }}
              sx={{
                display: 'flex',
                alignItems: 'center',
                gap: 1.25,
                width: '100%',
                p: 1.25,
                border: `1px solid ${menuColors.plan.border}`,
                borderRadius: 2.5,
                cursor: 'pointer',
                fontFamily: 'inherit',
                backgroundColor: menuColors.plan.surface,
                position: 'relative',
                overflow: 'hidden',
                transition: 'all 0.18s ease',
                '&:hover': {
                  backgroundColor: menuColors.plan.hoverSurface,
                  borderColor: menuColors.plan.iconBorder,
                },
              }}
            >
              <Box
                sx={{
                  width: 30,
                  height: 30,
                  borderRadius: 2,
                  bgcolor: menuColors.plan.iconSurface,
                  border: `1px solid ${menuColors.plan.iconBorder}`,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  flexShrink: 0,
                  position: 'relative',
                  zIndex: 1,
                }}
              >
                <Sparkles size={15} style={{ color: menuColors.plan.accent }} />
              </Box>
              <Box
                sx={{ flex: 1, minWidth: 0, textAlign: 'left', position: 'relative', zIndex: 1 }}
              >
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75 }}>
                  <Typography
                    sx={{ fontSize: '0.78rem', fontWeight: 700, color: menuColors.plan.accent }}
                  >
                    {planLabel} {t('plan.planSuffix', 'Plan')}
                  </Typography>
                  <Box
                    sx={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: 0.4,
                      fontSize: '0.55rem',
                      fontWeight: 700,
                      textTransform: 'uppercase',
                      letterSpacing: '0.05em',
                      px: 0.6,
                      py: 0.2,
                      borderRadius: 0.5,
                      bgcolor: menuColors.plan.statusSurface,
                      color: menuColors.plan.accent,
                      border: `1px solid ${menuColors.plan.statusBorder}`,
                    }}
                  >
                    <Box
                      sx={{
                        width: 4,
                        height: 4,
                        borderRadius: '50%',
                        bgcolor: menuColors.plan.accent,
                      }}
                    />
                    {t('plan.activeStatus', 'Active')}
                  </Box>
                </Box>
                <Typography
                  sx={{ fontSize: '0.61rem', color: menuColors.plan.description, mt: 0.25 }}
                >
                  {planDescription}
                </Typography>
              </Box>
              <ChevronRight
                size={14}
                style={{
                  color: menuColors.plan.accent,
                  flexShrink: 0,
                  position: 'relative',
                  zIndex: 1,
                }}
              />
            </Box>
          </Box>

          {/* ── 3. Settings nav links ── */}
          <Box
            sx={{
              borderTop: `1px solid ${alpha(muiTheme.palette.divider, 0.05)}`,
              pt: 0.5,
              pb: 0.5,
            }}
          >
            <Typography
              sx={{
                fontSize: '0.57rem',
                fontWeight: 700,
                textTransform: 'uppercase',
                letterSpacing: '0.09em',
                color: menuColors.sectionText,
                px: 1.75,
                pt: 0.75,
                pb: 0.375,
                display: 'block',
              }}
            >
              {t('navigation.sections.settings', 'Settings')}
            </Typography>

            {(
              [
                {
                  icon: User,
                  label: t('navigation.settings.accountAndSecurity', 'Account & Security'),
                  desc: t(
                    'navigation.menu.accountAndSecurityDesc',
                    'Profile, password, 2FA, passkeys'
                  ),
                  route: '/settings/account',
                },
                {
                  icon: Palette,
                  label: t('navigation.settings.appearance', 'Appearance'),
                  desc: t('navigation.menu.appearanceDesc', 'Theme, language'),
                  route: '/settings/appearance',
                },
                {
                  icon: Bell,
                  label: t('navigation.settings.notifications', 'Notifications'),
                  desc: t('navigation.menu.notificationsDesc', 'Alerts & preferences'),
                  route: '/settings/notifications',
                },
              ] as const
            ).map(({ icon: Icon, label, desc, route }) => (
              <Box
                key={route + label}
                component="button"
                onClick={() => {
                  setAnchorEl(null)
                  navigate(route)
                }}
                sx={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 1.25,
                  width: '100%',
                  px: 1.5,
                  py: 0.875,
                  border: 'none',
                  bgcolor: 'transparent',
                  cursor: 'pointer',
                  fontFamily: 'inherit',
                  transition: 'background-color 150ms',
                  '&:hover': {
                    bgcolor: isDark ? 'rgba(255,255,255,0.04)' : 'rgba(0,0,0,0.03)',
                  },
                }}
              >
                <Box
                  sx={{
                    width: 28,
                    height: 28,
                    borderRadius: 2,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    flexShrink: 0,
                    bgcolor: menuColors.navIcon.surface,
                    border: `1px solid ${alpha(muiTheme.palette.divider, isDark ? 0.07 : 0.05)}`,
                  }}
                >
                  <Icon size={14} style={{ color: menuColors.navIcon.color }} />
                </Box>
                <Box sx={{ flex: 1, textAlign: 'left' }}>
                  <Typography
                    sx={{
                      fontSize: '0.77rem',
                      fontWeight: 600,
                      color: 'text.primary',
                      lineHeight: 1.2,
                    }}
                  >
                    {label}
                  </Typography>
                  <Typography
                    sx={{ fontSize: '0.59rem', color: menuColors.navDescription, mt: 0.125 }}
                  >
                    {desc}
                  </Typography>
                </Box>
                <ChevronRight
                  size={13}
                  style={{ color: menuColors.navIcon.chevron, flexShrink: 0 }}
                />
              </Box>
            ))}
          </Box>

          {/* ── 4. Logout (danger zone) ── */}
          <Box sx={{ borderTop: `1px solid ${alpha(muiTheme.palette.divider, 0.05)}`, py: 0.625 }}>
            <Box
              component="button"
              onClick={() => {
                setAnchorEl(null)
                trackAuth(EventAction.LOGOUT, { surface: 'user_menu' })
                logout()
              }}
              sx={{
                display: 'flex',
                alignItems: 'center',
                gap: 1.25,
                width: '100%',
                px: 1.5,
                py: 0.875,
                border: 'none',
                bgcolor: 'transparent',
                cursor: 'pointer',
                fontFamily: 'inherit',
                transition: 'background-color 150ms',
                '&:hover': {
                  bgcolor: isDark ? 'rgba(248,113,113,0.07)' : 'rgba(220,38,38,0.04)',
                },
              }}
            >
              <Box
                sx={{
                  width: 28,
                  height: 28,
                  borderRadius: 2,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  flexShrink: 0,
                  bgcolor: isDark ? 'rgba(248,113,113,0.07)' : 'rgba(220,38,38,0.04)',
                  border: `1px solid ${alpha(isDark ? '#f87171' : '#dc2626', 0.12)}`,
                }}
              >
                <LogOut size={14} style={{ color: isDark ? '#f87171' : '#dc2626' }} />
              </Box>
              <Typography
                sx={{ fontSize: '0.77rem', fontWeight: 600, color: isDark ? '#f87171' : '#dc2626' }}
              >
                {t('navigation.logout')}
              </Typography>
            </Box>
          </Box>
        </Popover>

        <PlanInfoDrawer
          open={planDrawerOpen}
          onClose={() => setPlanDrawerOpen(false)}
          plan={plan}
          features={features}
          entitlement={entitlement}
        />
      </Toolbar>
    </AppBar>
  )
}

import type { Theme } from '@mui/material/styles'

export interface ProfileMenuContrastPair {
  name: string
  foreground: string
  background: string
}

export function getProfileMenuColors(muiTheme: Theme) {
  const isDark = muiTheme.palette.mode === 'dark'

  return {
    menuSurface: isDark ? '#27272a' : '#ffffff',
    heroSurface: isDark ? '#1d3029' : '#f0fdf4',
    sectionText: isDark ? '#d4d4d8' : '#4b5563',
    navDescription: isDark ? '#d4d4d8' : '#4b5563',
    navIcon: {
      surface: isDark ? '#343438' : '#f1f5f9',
      color: isDark ? '#cbd5e1' : '#475569',
      chevron: isDark ? '#cbd5e1' : '#64748b',
    },
    avatar: {
      surface: isDark ? '#12392e' : '#ecfdf5',
      color: isDark ? '#6ee7b7' : '#047857',
      border: isDark ? '#2dd4bf66' : '#86efac',
    },
    plan: {
      surface: isDark ? '#312e41' : '#f5f3ff',
      hoverSurface: isDark ? '#373052' : '#ede9fe',
      border: isDark ? '#7c3aed80' : '#c4b5fd',
      iconSurface: isDark ? '#3b315d' : '#ede9fe',
      iconBorder: isDark ? '#8b5cf680' : '#c4b5fd',
      accent: isDark ? '#ddd6fe' : '#5b21b6',
      description: isDark ? '#d4d4d8' : '#4b5563',
      statusSurface: isDark ? '#3b315d' : '#ede9fe',
      statusBorder: isDark ? '#8b5cf680' : '#c4b5fd',
    },
  }
}

export function getRoleBadgeStyles(roleLabel: string, isDark: boolean) {
  if (roleLabel === 'Admin') {
    return {
      backgroundColor: isDark ? '#12392e' : '#ecfdf5',
      color: isDark ? '#6ee7b7' : '#047857',
    }
  }

  if (roleLabel === 'Operator') {
    return {
      backgroundColor: isDark ? '#1e2f4f' : '#eff6ff',
      color: isDark ? '#bfdbfe' : '#1d4ed8',
    }
  }

  return {
    backgroundColor: isDark ? '#343438' : '#f3f4f6',
    color: isDark ? '#d4d4d8' : '#4b5563',
  }
}

export function getProfileMenuContrastPairs(muiTheme: Theme): ProfileMenuContrastPair[] {
  const isDark = muiTheme.palette.mode === 'dark'
  const colors = getProfileMenuColors(muiTheme)
  const adminRole = getRoleBadgeStyles('Admin', isDark)
  const operatorRole = getRoleBadgeStyles('Operator', isDark)
  const defaultRole = getRoleBadgeStyles('', isDark)

  return [
    {
      name: `${muiTheme.palette.mode} profile avatar initials`,
      foreground: colors.avatar.color,
      background: colors.avatar.surface,
    },
    {
      name: `${muiTheme.palette.mode} admin role badge`,
      foreground: adminRole.color,
      background: adminRole.backgroundColor,
    },
    {
      name: `${muiTheme.palette.mode} operator role badge`,
      foreground: operatorRole.color,
      background: operatorRole.backgroundColor,
    },
    {
      name: `${muiTheme.palette.mode} default role badge`,
      foreground: defaultRole.color,
      background: defaultRole.backgroundColor,
    },
    {
      name: `${muiTheme.palette.mode} plan label`,
      foreground: colors.plan.accent,
      background: colors.plan.surface,
    },
    {
      name: `${muiTheme.palette.mode} plan description`,
      foreground: colors.plan.description,
      background: colors.plan.surface,
    },
    {
      name: `${muiTheme.palette.mode} plan status`,
      foreground: colors.plan.accent,
      background: colors.plan.statusSurface,
    },
    {
      name: `${muiTheme.palette.mode} settings section label`,
      foreground: colors.sectionText,
      background: colors.menuSurface,
    },
    {
      name: `${muiTheme.palette.mode} settings item description`,
      foreground: colors.navDescription,
      background: colors.menuSurface,
    },
  ]
}

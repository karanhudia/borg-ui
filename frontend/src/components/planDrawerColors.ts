import type { Theme } from '@mui/material/styles'
import type { Plan } from '../core/features'
import { getProfileMenuColors } from './profileMenuColors'

export interface PlanDrawerContrastPair {
  name: string
  foreground: string
  background: string
}

export interface PlanDrawerPlanColors {
  surface: string
  hoverSurface: string
  border: string
  iconSurface: string
  iconBorder: string
  accent: string
  description: string
  statusSurface: string
  statusBorder: string
}

export interface PlanDrawerColors {
  paper: string
  sectionText: string
  secondaryText: string
  plans: Record<Plan, PlanDrawerPlanColors>
}

export function getPlanDrawerColors(muiTheme: Theme): PlanDrawerColors {
  const isDark = muiTheme.palette.mode === 'dark'
  const profileMenuColors = getProfileMenuColors(muiTheme)

  return {
    paper: isDark ? '#27272a' : '#ffffff',
    sectionText: profileMenuColors.sectionText,
    secondaryText: profileMenuColors.navDescription,
    plans: {
      community: {
        surface: isDark ? '#343438' : '#f8fafc',
        hoverSurface: isDark ? '#3f3f46' : '#f1f5f9',
        border: isDark ? '#71717a80' : '#cbd5e1',
        iconSurface: isDark ? '#3f3f46' : '#f1f5f9',
        iconBorder: isDark ? '#71717a80' : '#cbd5e1',
        accent: isDark ? '#cbd5e1' : '#475569',
        description: profileMenuColors.navDescription,
        statusSurface: isDark ? '#3f3f46' : '#f1f5f9',
        statusBorder: isDark ? '#71717a80' : '#cbd5e1',
      },
      pro: { ...profileMenuColors.plan },
      enterprise: {
        surface: isDark ? '#3f2e11' : '#fffbeb',
        hoverSurface: isDark ? '#4d3510' : '#fef3c7',
        border: isDark ? '#f59e0b80' : '#fcd34d',
        iconSurface: isDark ? '#5a3b0d' : '#fef3c7',
        iconBorder: isDark ? '#f59e0b80' : '#fcd34d',
        accent: isDark ? '#fde68a' : '#92400e',
        description: profileMenuColors.navDescription,
        statusSurface: isDark ? '#5a3b0d' : '#fef3c7',
        statusBorder: isDark ? '#f59e0b80' : '#fcd34d',
      },
    },
  }
}

export function getPlanDrawerContrastPairs(muiTheme: Theme): PlanDrawerContrastPair[] {
  const colors = getPlanDrawerColors(muiTheme)
  const planPairs = Object.entries(colors.plans).flatMap(([plan, planColors]) => [
    {
      name: `${muiTheme.palette.mode} ${plan} drawer accent on paper`,
      foreground: planColors.accent,
      background: colors.paper,
    },
    {
      name: `${muiTheme.palette.mode} ${plan} drawer tile label`,
      foreground: planColors.accent,
      background: planColors.surface,
    },
    {
      name: `${muiTheme.palette.mode} ${plan} drawer tile hover label`,
      foreground: planColors.accent,
      background: planColors.hoverSurface,
    },
    {
      name: `${muiTheme.palette.mode} ${plan} drawer tile hover secondary label`,
      foreground: colors.secondaryText,
      background: planColors.hoverSurface,
    },
    {
      name: `${muiTheme.palette.mode} ${plan} drawer icon`,
      foreground: planColors.accent,
      background: planColors.iconSurface,
    },
    {
      name: `${muiTheme.palette.mode} ${plan} drawer status label`,
      foreground: planColors.accent,
      background: planColors.statusSurface,
    },
    {
      name: `${muiTheme.palette.mode} ${plan} drawer description`,
      foreground: planColors.description,
      background: planColors.surface,
    },
    {
      name: `${muiTheme.palette.mode} ${plan} drawer description on paper`,
      foreground: planColors.description,
      background: colors.paper,
    },
  ])

  return [
    {
      name: `${muiTheme.palette.mode} drawer section label`,
      foreground: colors.sectionText,
      background: colors.paper,
    },
    {
      name: `${muiTheme.palette.mode} drawer secondary text`,
      foreground: colors.secondaryText,
      background: colors.paper,
    },
    ...planPairs,
  ]
}

import React from 'react'

export const makeT = (isDark: boolean) => ({
  bgCard: isDark ? 'rgba(255,255,255,0.05)' : 'rgba(0,0,0,0.03)',
  bgCardHover: isDark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.05)',
  border: isDark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.1)',
  borderHover: isDark ? 'rgba(255,255,255,0.18)' : 'rgba(0,0,0,0.22)',
  textPrimary: isDark ? '#e2e8f0' : '#1e293b',
  textMuted: isDark ? '#94a3b8' : '#64748b',
  textDim: isDark ? '#64748b' : '#94a3b8',
  green: '#22c55e',
  greenDim: isDark ? 'rgba(34,197,94,0.1)' : 'rgba(34,197,94,0.12)',
  greenGlow: 'rgba(34,197,94,0.25)',
  amber: '#f59e0b',
  amberDim: isDark ? 'rgba(245,158,11,0.1)' : 'rgba(245,158,11,0.12)',
  red: '#ef4444',
  redDim: isDark ? 'rgba(239,68,68,0.1)' : 'rgba(239,68,68,0.12)',
  blue: '#3b82f6',
  blueDim: isDark ? 'rgba(59,130,246,0.1)' : 'rgba(59,130,246,0.12)',
  indigo: '#6366f1',
  indigoDim: isDark ? 'rgba(99,102,241,0.12)' : 'rgba(99,102,241,0.1)',
  mono: '"JetBrains Mono","Fira Code","Cascadia Code",ui-monospace,monospace',
  radius: '14px',
  // SVG / internal
  svgTrack: isDark ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.1)',
  colShade: isDark ? 'rgba(255,255,255,0.015)' : 'rgba(0,0,0,0.02)',
  barBg: isDark ? 'rgba(255,255,255,0.05)' : 'rgba(0,0,0,0.07)',
  repoBadgeBg: isDark ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.05)',
  hoverBg: isDark ? 'rgba(255,255,255,0.05)' : 'rgba(0,0,0,0.04)',
  todayCol: isDark ? 'rgba(99,102,241,0.06)' : 'rgba(99,102,241,0.08)',
  axisLabel: isDark ? '#475569' : '#94a3b8',
  insetLine: isDark ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.06)',
})

export type Tokens = ReturnType<typeof makeT>

export const TokenContext = React.createContext<Tokens>(makeT(true))
export const useT = () => React.useContext(TokenContext)

export const STATUS = {
  healthy: { color: '#22c55e', dim: 'rgba(34,197,94,0.10)', glow: 'rgba(34,197,94,0.3)' },
  warning: { color: '#f59e0b', dim: 'rgba(245,158,11,0.13)', glow: 'rgba(245,158,11,0.3)' },
  critical: { color: '#ef4444', dim: 'rgba(239,68,68,0.15)', glow: 'rgba(239,68,68,0.3)' },
  unknown: { color: '#64748b', dim: 'rgba(100,116,139,0.05)', glow: 'transparent' },
}

export const SEG_COLORS = ['#6366f1', '#3b82f6', '#22c55e', '#f59e0b', '#ec4899']

// Job type → chart color
export const JOB_COLOR: Record<string, string> = {
  backup: '#22c55e',
  check: '#3b82f6',
  compact: '#6366f1',
  restore: '#f59e0b',
  prune: '#ec4899',
}

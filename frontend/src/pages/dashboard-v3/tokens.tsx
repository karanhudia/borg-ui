import React from 'react'

export const makeT = (isDark: boolean) => ({
  // Surfaces and borders are kept NEUTRAL (true gray) on purpose. This page
  // is impeccable's "Full palette" tier, not Restrained: status colors (red,
  // amber, green), destination-type chips (blue/indigo/violet/cyan), and
  // chart hues are already doing load-bearing color work. Tinting the
  // surface toward brand emerald would add a fifth color voice competing
  // with the four already on the page.
  //
  // Brand identity is preserved by chrome (logo, theme-color, sidebar
  // active state, healthy-status green which sits in the brand family),
  // not by surface tint. This follows the canonical reference dashboards
  // (Linear, Stripe, Vercel): neutral surfaces, brand lives in chrome.
  bgCard: isDark ? 'rgba(255,255,255,0.04)' : 'rgba(0,0,0,0.025)',
  bgCardHover: isDark ? 'rgba(255,255,255,0.07)' : 'rgba(0,0,0,0.05)',
  border: isDark ? 'rgba(255,255,255,0.10)' : 'rgba(0,0,0,0.10)',
  borderHover: isDark ? 'rgba(255,255,255,0.18)' : 'rgba(0,0,0,0.18)',
  textPrimary: isDark ? '#e2e8f0' : '#1e293b',
  textMuted: isDark ? '#94a3b8' : '#64748b',
  textDim: isDark ? '#64748b' : '#94a3b8',
  green: '#22c55e',
  greenDim: isDark ? 'rgba(34,197,94,0.1)' : 'rgba(34,197,94,0.12)',
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
  healthy: { color: '#22c55e', dim: 'rgba(34,197,94,0.10)' },
  warning: { color: '#f59e0b', dim: 'rgba(245,158,11,0.13)' },
  critical: { color: '#ef4444', dim: 'rgba(239,68,68,0.15)' },
  unknown: { color: '#64748b', dim: 'rgba(100,116,139,0.05)' },
}

/**
 * Surface vocabulary on the dashboard is INTENTIONALLY two-tone:
 *
 * - "Brand surface" via `T.bgCard` (~4% emerald). Used for every panel
 *   and for healthy repo cards. The page reads as Borg UI without any
 *   colored cards.
 * - "Status surface" via the card's status color at ~5% alpha (see
 *   `RepositoryHealthPanel.tsx` non-healthy branch). Used for warning
 *   and critical repo cards so they register as different at a glance.
 *   The 15% wall-of-color original is deliberately gone.
 *
 * Do not "unify" these into a single surface token. The brand-surface
 * is the default; the status-surface is opt-in per card and only on
 * critical/warning state. Healthy stays on brand by design.
 */

export const SEG_COLORS = ['#6366f1', '#3b82f6', '#22c55e', '#f59e0b', '#ec4899']

// Job type → chart color
export const JOB_COLOR: Record<string, string> = {
  backup: '#22c55e',
  check: '#3b82f6',
  compact: '#6366f1',
  restore: '#f59e0b',
  prune: '#ec4899',
}

// Repository destination type → accent color. Picked so chips are
// distinguishable from status colors (green/amber/red) and from each
// other. LOCAL is the brand blue since it's the default destination.
export const TYPE_COLOR: Record<string, string> = {
  local: '#3b82f6',
  ssh: '#6366f1',
  sftp: '#8b5cf6',
  rclone: '#06b6d4',
}

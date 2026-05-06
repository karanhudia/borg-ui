import { ReactNode } from 'react'
import { Box, Typography, IconButton, Button, Tooltip, useTheme, alpha } from '@mui/material'

export interface StatItem {
  icon: ReactNode
  label: string
  value: string
  tooltip?: ReactNode
  color?: 'primary' | 'success' | 'warning' | 'info' | 'secondary'
}

export interface MetaItem {
  label: string
  value: string
  tooltip?: ReactNode
}

export interface ActionItem {
  icon: ReactNode
  tooltip: string
  onClick: () => void
  color?: 'default' | 'primary' | 'error' | 'warning' | 'success'
  sx?: object
  disabled?: boolean
  hidden?: boolean
}

export interface PrimaryAction {
  label: string
  icon: ReactNode
  onClick: () => void
  disabled?: boolean
  color?: string
}

export interface EntityCardProps {
  title: string
  subtitle?: string
  badge?: ReactNode
  stats: StatItem[]
  meta?: MetaItem[]
  tags?: ReactNode
  actions: ActionItem[]
  primaryAction?: PrimaryAction
  accentColor?: string
  isHighlighted?: boolean
}

const DEFAULT_ACCENT = '#059669'
const HIGHLIGHT_ACCENT = '#f59e0b'

export default function EntityCard({
  title,
  subtitle,
  badge,
  stats,
  meta,
  tags,
  actions,
  primaryAction,
  accentColor = DEFAULT_ACCENT,
  isHighlighted = false,
}: EntityCardProps) {
  const theme = useTheme()
  const isDark = theme.palette.mode === 'dark'
  const effectiveAccent = isHighlighted ? HIGHLIGHT_ACCENT : accentColor

  const iconBtnSx = {
    width: 32,
    height: 32,
    borderRadius: 1.5,
    color: 'text.secondary',
    '&:hover': {
      bgcolor: isDark ? alpha('#fff', 0.07) : alpha('#000', 0.06),
      color: 'text.primary',
    },
  }

  const colorMap: Record<string, string> = {
    primary: theme.palette.primary.main,
    error: theme.palette.error.main,
    warning: theme.palette.warning.main,
    success: theme.palette.success.main,
  }

  return (
    <Box
      sx={{
        position: 'relative',
        borderRadius: 2,
        bgcolor: 'background.paper',
        overflow: 'hidden',
        maxWidth: '100%',
        minWidth: 0,
        boxShadow: isDark
          ? `0 0 0 1px ${alpha('#fff', 0.08)}, 0 4px 16px ${alpha('#000', 0.25)}`
          : `0 0 0 1px ${alpha('#000', 0.08)}, 0 2px 8px ${alpha('#000', 0.07)}`,
        transition: 'all 200ms cubic-bezier(0.16,1,0.3,1)',
        '&:hover': {
          transform: 'translateY(-2px)',
          boxShadow: isDark
            ? `0 0 0 1px ${alpha(effectiveAccent, 0.4)}, 0 8px 24px ${alpha('#000', 0.3)}, 0 2px 8px ${alpha(effectiveAccent, 0.1)}`
            : `0 0 0 1px ${alpha(effectiveAccent, 0.3)}, 0 8px 24px ${alpha('#000', 0.12)}, 0 2px 8px ${alpha(effectiveAccent, 0.08)}`,
        },
      }}
    >
      <Box sx={{ px: { xs: 1.75, sm: 2 }, pt: { xs: 1.75, sm: 2 }, pb: { xs: 1.5, sm: 1.75 } }}>
        <Box
          sx={{
            display: 'flex',
            alignItems: 'flex-start',
            justifyContent: 'space-between',
            gap: 1,
            mb: 1.5,
          }}
        >
          <Box sx={{ minWidth: 0, flex: 1 }}>
            <Typography variant="subtitle1" fontWeight={700} noWrap sx={{ lineHeight: 1.3 }}>
              {title}
            </Typography>
            {subtitle && (
              <Typography
                variant="body2"
                noWrap
                sx={{ fontSize: '0.7rem', color: 'text.disabled', lineHeight: 1.4 }}
              >
                {subtitle}
              </Typography>
            )}
          </Box>

          {badge && <Box sx={{ flexShrink: 0 }}>{badge}</Box>}
        </Box>

        <Box
          sx={{
            display: 'grid',
            gridTemplateColumns: { xs: 'repeat(2, 1fr)', sm: `repeat(${stats.length}, 1fr)` },
            borderRadius: 1.5,
            border: '1px solid',
            borderColor: isDark ? alpha('#fff', 0.06) : alpha('#000', 0.07),
            overflow: 'hidden',
            mb: 1.5,
            bgcolor: isDark ? alpha('#fff', 0.025) : alpha('#000', 0.018),
          }}
        >
          {stats.map((stat, i) => {
            const isRightColXs = i % 2 === 1
            const isLastSm = i === stats.length - 1
            const isFirstRowXs = i < 2
            const statColor = stat.color
              ? alpha((theme.palette[stat.color] as { main: string }).main, 0.7)
              : undefined
            return (
              <Tooltip
                key={stat.label}
                title={stat.tooltip || ''}
                arrow
                slotProps={{ tooltip: { sx: { whiteSpace: 'pre-line' } } }}
              >
                <Box
                  sx={{
                    px: 1.5,
                    py: 1.1,
                    cursor: stat.tooltip ? 'help' : 'default',
                    borderRight: isLastSm ? 0 : '1px solid',
                    borderBottom: { xs: isFirstRowXs ? '1px solid' : 0, sm: 0 },
                    borderColor: isDark ? alpha('#fff', 0.06) : alpha('#000', 0.07),
                    ...(isRightColXs && {
                      borderRight: { xs: 0, sm: isLastSm ? 0 : '1px solid' },
                    }),
                  }}
                >
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mb: 0.35 }}>
                    <Box
                      sx={{
                        color: statColor ?? 'text.disabled',
                        display: 'flex',
                        alignItems: 'center',
                      }}
                    >
                      {stat.icon}
                    </Box>
                    <Typography
                      sx={{
                        fontSize: '0.58rem',
                        fontWeight: 700,
                        textTransform: 'uppercase',
                        letterSpacing: '0.07em',
                        color: statColor ?? 'text.disabled',
                        lineHeight: 1,
                      }}
                    >
                      {stat.label}
                    </Typography>
                  </Box>
                  <Typography
                    variant="body2"
                    fontWeight={600}
                    noWrap
                    sx={{ fontVariantNumeric: 'tabular-nums', fontSize: '0.85rem' }}
                  >
                    {stat.value}
                  </Typography>
                </Box>
              </Tooltip>
            )
          })}
        </Box>

        {meta && meta.length > 0 && (
          <Box
            sx={{
              display: 'flex',
              gap: { xs: 1.25, sm: 1.75 },
              flexWrap: 'wrap',
              mb: 1.5,
              px: 0.25,
            }}
          >
            {meta.map((m) => (
              <Tooltip
                key={m.label}
                title={m.tooltip || ''}
                arrow
                slotProps={{ tooltip: { sx: { whiteSpace: 'pre-line' } } }}
              >
                <Box
                  sx={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 0.4,
                    cursor: m.tooltip ? 'help' : 'default',
                  }}
                >
                  <Typography sx={{ fontSize: '0.68rem', color: 'text.disabled', lineHeight: 1 }}>
                    {m.label}:
                  </Typography>
                  <Typography
                    sx={{
                      fontSize: '0.68rem',
                      fontWeight: 600,
                      color: 'text.secondary',
                      lineHeight: 1,
                    }}
                  >
                    {m.value}
                  </Typography>
                </Box>
              </Tooltip>
            ))}
          </Box>
        )}

        {tags && <Box sx={{ mb: 1.5 }}>{tags}</Box>}

        <Box
          sx={{
            display: 'flex',
            alignItems: 'center',
            gap: 0.5,
            pt: 1.25,
            borderTop: '1px solid',
            borderColor: isDark ? alpha('#fff', 0.06) : alpha('#000', 0.07),
          }}
        >
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.25 }}>
            {actions
              .filter((a) => !a.hidden)
              .map((action, i) => {
                const actionColor =
                  action.color && action.color !== 'default' ? colorMap[action.color] : undefined

                const resolvedSx = actionColor
                  ? {
                      ...iconBtnSx,
                      color: alpha(actionColor, 0.6),
                      '&:hover': {
                        color: actionColor,
                        bgcolor: alpha(actionColor, 0.1),
                      },
                      ...action.sx,
                    }
                  : { ...iconBtnSx, ...action.sx }

                return (
                  <Tooltip key={i} title={action.tooltip} arrow>
                    <span>
                      <IconButton
                        size="small"
                        aria-label={action.tooltip}
                        onClick={action.onClick}
                        disabled={action.disabled}
                        sx={resolvedSx}
                      >
                        {action.icon}
                      </IconButton>
                    </span>
                  </Tooltip>
                )
              })}
          </Box>

          {primaryAction && (
            <Tooltip title={primaryAction.label} arrow>
              <span style={{ marginLeft: 'auto' }}>
                <Button
                  variant="contained"
                  size="small"
                  startIcon={primaryAction.icon}
                  onClick={primaryAction.onClick}
                  disabled={primaryAction.disabled}
                  sx={{
                    bgcolor: primaryAction.color ?? effectiveAccent,
                    color: '#fff',
                    fontSize: '0.78rem',
                    height: 30,
                    flexShrink: 0,
                    px: { xs: 0.85, sm: 1.5 },
                    minWidth: 'unset',
                    boxShadow: `0 2px 10px ${alpha(primaryAction.color ?? effectiveAccent, 0.38)}`,
                    '& .MuiButton-startIcon': {
                      mr: { xs: 0, sm: 0.5 },
                      ml: { xs: 0, sm: '-2px' },
                    },
                    '&:hover': {
                      bgcolor: primaryAction.color ?? effectiveAccent,
                      filter: 'brightness(0.88)',
                      boxShadow: `0 4px 18px ${alpha(primaryAction.color ?? effectiveAccent, 0.5)}`,
                    },
                    '&.Mui-disabled': {
                      bgcolor: isDark ? alpha('#fff', 0.08) : alpha('#000', 0.08),
                      color: 'text.disabled',
                      boxShadow: 'none',
                    },
                  }}
                >
                  <Box component="span" sx={{ display: { xs: 'none', sm: 'inline' } }}>
                    {primaryAction.label}
                  </Box>
                </Button>
              </span>
            </Tooltip>
          )}
        </Box>
      </Box>
    </Box>
  )
}

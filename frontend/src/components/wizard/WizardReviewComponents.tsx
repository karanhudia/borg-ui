import type { ReactNode } from 'react'
import { Box, Tooltip, Typography, alpha, useTheme } from '@mui/material'

export function ReviewIconBadge({ icon, accentColor }: { icon: ReactNode; accentColor: string }) {
  return (
    <Box
      sx={{
        width: 28,
        height: 28,
        borderRadius: '8px',
        bgcolor: alpha(accentColor, 0.15),
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        color: accentColor,
        flexShrink: 0,
      }}
    >
      {icon}
    </Box>
  )
}

export function ReviewCodePill({
  children,
  block,
  tooltip,
  maxChars,
}: {
  children: ReactNode
  /** Render as a full-width block (rare — use only when value is intentionally on its own line). */
  block?: boolean
  /** Override the tooltip content. Defaults to `children`. */
  tooltip?: ReactNode
  /** Soft character-based width cap (translates to ch units). */
  maxChars?: number
}) {
  const theme = useTheme()
  return (
    <Tooltip title={tooltip ?? children} placement="top">
      <Typography
        component="span"
        sx={{
          fontFamily: 'monospace',
          fontSize: '0.72rem',
          px: 0.75,
          py: 0.15,
          borderRadius: '4px',
          bgcolor: alpha(theme.palette.text.primary, theme.palette.mode === 'dark' ? 0.08 : 0.06),
          color: 'text.primary',
          maxWidth: maxChars ? `${maxChars}ch` : '100%',
          width: block ? '100%' : undefined,
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
          display: block ? 'block' : 'inline-block',
          verticalAlign: 'middle',
          cursor: 'default',
          lineHeight: 1.6,
        }}
      >
        {children}
      </Typography>
    </Tooltip>
  )
}

/**
 * Stacked variant of ReviewAttrRow: label sits above the value(s) so long
 * content (paths, exclude patterns, archive templates) gets the full card
 * width instead of fighting the label for room.
 */
export function ReviewAttrStack({
  label,
  trailing,
  children,
}: {
  label: string
  /** Optional content rendered on the right side of the label header (e.g. a count chip). */
  trailing?: ReactNode
  children: ReactNode
}) {
  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5, minWidth: 0 }}>
      <Box
        sx={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 1,
          minWidth: 0,
        }}
      >
        <Typography
          variant="caption"
          sx={{ color: 'text.disabled', fontSize: '0.7rem', flexShrink: 0 }}
        >
          {label}
        </Typography>
        {trailing}
      </Box>
      <Box
        sx={{
          display: 'flex',
          flexDirection: 'column',
          gap: 0.4,
          minWidth: 0,
        }}
      >
        {children}
      </Box>
    </Box>
  )
}

export function ReviewAttrRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <Box
      sx={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: 1,
        minWidth: 0,
      }}
    >
      <Typography
        variant="caption"
        sx={{ color: 'text.disabled', fontSize: '0.7rem', flexShrink: 0 }}
      >
        {label}
      </Typography>
      <Box
        sx={{
          minWidth: 0,
          display: 'flex',
          alignItems: 'center',
          gap: 0.5,
          flexWrap: 'wrap',
          justifyContent: 'flex-end',
        }}
      >
        {children}
      </Box>
    </Box>
  )
}

export function ReviewSectionCard({
  icon,
  label,
  accentColor,
  trailing,
  fullWidth,
  children,
}: {
  icon: ReactNode
  label: string
  accentColor: string
  /** Optional content rendered on the right of the header (e.g. a status indicator). */
  trailing?: ReactNode
  /** Spans both columns when placed inside ReviewSectionGrid. */
  fullWidth?: boolean
  children: ReactNode
}) {
  const theme = useTheme()
  return (
    <Box
      sx={{
        borderRadius: 2,
        bgcolor: alpha(accentColor, theme.palette.mode === 'dark' ? 0.06 : 0.04),
        border: '1px solid',
        borderColor: alpha(accentColor, theme.palette.mode === 'dark' ? 0.18 : 0.14),
        p: 1.75,
        display: 'flex',
        flexDirection: 'column',
        gap: 1.25,
        minWidth: 0,
        overflow: 'hidden',
        height: '100%',
        gridColumn: fullWidth ? { sm: '1 / -1' } : undefined,
      }}
    >
      <Box
        sx={{
          display: 'flex',
          alignItems: 'center',
          gap: 1,
          justifyContent: 'space-between',
        }}
      >
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, minWidth: 0 }}>
          <ReviewIconBadge icon={icon} accentColor={accentColor} />
          <Typography
            variant="caption"
            sx={{
              color: 'text.secondary',
              fontWeight: 700,
              fontSize: '0.68rem',
              letterSpacing: '0.06em',
              textTransform: 'uppercase',
              whiteSpace: 'nowrap',
            }}
          >
            {label}
          </Typography>
        </Box>
        {trailing}
      </Box>

      <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.75 }}>{children}</Box>
    </Box>
  )
}

/**
 * Compact enabled/disabled (or generic status) indicator with a colored dot
 * plus label. Replaces small filled chips that visually compete with content.
 */
export function ReviewStatus({
  enabled,
  label,
  tone,
}: {
  enabled: boolean
  label: string
  /** Force a tone regardless of `enabled`. Useful for neutral states. */
  tone?: 'success' | 'muted' | 'warning'
}) {
  const theme = useTheme()
  const resolvedTone = tone ?? (enabled ? 'success' : 'muted')
  const color =
    resolvedTone === 'success'
      ? theme.palette.success.main
      : resolvedTone === 'warning'
        ? theme.palette.warning.main
        : theme.palette.text.disabled
  return (
    <Box sx={{ display: 'inline-flex', alignItems: 'center', gap: 0.625, minWidth: 0 }}>
      <Box
        sx={{
          width: 6,
          height: 6,
          borderRadius: '50%',
          bgcolor: color,
          flexShrink: 0,
        }}
      />
      <Typography
        component="span"
        sx={{
          fontSize: '0.72rem',
          fontWeight: 600,
          color: resolvedTone === 'muted' ? 'text.disabled' : 'text.primary',
          lineHeight: 1.4,
        }}
      >
        {label}
      </Typography>
    </Box>
  )
}

/** Small uppercase count label used inside ReviewAttrStack trailing slot. */
export function ReviewCount({ children }: { children: ReactNode }) {
  return (
    <Typography
      component="span"
      variant="caption"
      sx={{
        color: 'text.disabled',
        fontSize: '0.65rem',
        fontWeight: 600,
        letterSpacing: '0.04em',
      }}
    >
      {children}
    </Typography>
  )
}

export function ReviewSectionGrid({ children }: { children: ReactNode }) {
  return (
    <Box
      sx={{
        display: 'grid',
        gridTemplateColumns: { xs: '1fr', sm: '1fr 1fr' },
        // Stretch siblings so cards in the same row share height. Combined with
        // h:100% on the card itself, this keeps side-by-side blocks visually
        // aligned. Each card caps its dynamic content (e.g. source pills) so
        // the row height stays bounded.
        alignItems: 'stretch',
        gap: 1.25,
        minWidth: 0,
        overflow: 'hidden',
      }}
    >
      {children}
    </Box>
  )
}

export function ReviewKicker({ children }: { children: ReactNode }) {
  return (
    <Typography
      variant="caption"
      sx={{
        color: 'text.disabled',
        fontWeight: 700,
        fontSize: '0.6rem',
        letterSpacing: '0.12em',
        textTransform: 'uppercase',
      }}
    >
      {children}
    </Typography>
  )
}

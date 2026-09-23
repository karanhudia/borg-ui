import { createTheme, alpha } from '@mui/material/styles'
import type { Theme } from '@mui/material/styles'

// What a row is about: the repository, the script, the step. Blended rather
// than full contrast, so a list of them does not read as a wall of emphasis
// and the heading above them keeps the weight.
export const subjectText = (theme: Theme) => alpha(theme.palette.text.primary, 0.82)

// Create a custom theme for Borg UI
export const theme = createTheme({
  palette: {
    mode: 'light',
    // Every `main` below is used as text on white, on gray-50 and on the
    // 8-16% tints chips and stat tiles lay under it, so each one clears
    // WCAG AA 4.5:1 on all of those, and white text on it clears 4.5:1 too.
    // `light` keeps the brighter shade for fills, borders and icons.
    primary: {
      main: '#1d4ed8', // Blue 700
      light: '#2563eb', // Blue 600
      dark: '#1e40af', // Blue 800
      contrastText: '#ffffff',
    },
    secondary: {
      main: '#6d28d9', // Violet 700
      light: '#7c3aed', // Violet 600
      dark: '#5b21b6', // Violet 800
      contrastText: '#ffffff',
    },
    success: {
      main: '#15733a', // Between Green 700 and 800
      light: '#16a34a', // Green 600
      dark: '#166534', // Green 800
      contrastText: '#ffffff',
    },
    error: {
      main: '#b91c1c', // Red 700
      light: '#dc2626', // Red 600
      dark: '#991b1b', // Red 800
      contrastText: '#ffffff',
    },
    warning: {
      main: '#96500a', // Amber-orange, kept 30 degrees away from error red
      light: '#ea580c', // Orange 600
      dark: '#9a3412', // Orange 800
      contrastText: '#ffffff',
    },
    info: {
      main: '#0c6780', // Between Cyan 700 and 800
      light: '#0891b2', // Cyan 600
      dark: '#155e75', // Cyan 800
      contrastText: '#ffffff',
    },
    background: {
      default: '#f9fafb', // Gray 50
      paper: '#ffffff',
    },
    text: {
      primary: '#111827', // Gray 900
      secondary: '#4b5563', // Gray 600 (WCAG AA on tinted surfaces: 7.04:1 on gray-100)
      // Lighter than secondary, but still 4.5:1 on tinted surfaces: 136
      // call sites use it for quiet captions, not only disabled controls.
      disabled: '#5f6672',
    },
  },
  typography: {
    fontFamily: [
      '-apple-system',
      'BlinkMacSystemFont',
      '"Segoe UI"',
      'Roboto',
      '"Helvetica Neue"',
      'Arial',
      'sans-serif',
      '"Apple Color Emoji"',
      '"Segoe UI Emoji"',
      '"Segoe UI Symbol"',
    ].join(','),
    h1: {
      fontSize: '2.25rem',
      fontWeight: 700,
      lineHeight: 1.2,
    },
    h2: {
      fontSize: '1.875rem',
      fontWeight: 600,
      lineHeight: 1.3,
    },
    h3: {
      fontSize: '1.5rem',
      fontWeight: 600,
      lineHeight: 1.4,
    },
    h4: {
      fontSize: '1.25rem',
      fontWeight: 600,
      lineHeight: 1.5,
    },
    h5: {
      fontSize: '1.125rem',
      fontWeight: 600,
      lineHeight: 1.5,
    },
    h6: {
      fontSize: '1rem',
      fontWeight: 600,
      lineHeight: 1.5,
    },
    body1: {
      fontSize: '1rem',
      lineHeight: 1.5,
    },
    body2: {
      fontSize: '0.875rem',
      lineHeight: 1.5,
    },
    button: {
      textTransform: 'none',
      fontWeight: 500,
    },
  },
  shape: {
    borderRadius: 8,
  },
  spacing: 8, // 8px baseline
  components: {
    MuiButton: {
      styleOverrides: {
        root: {
          borderRadius: 12,
          padding: '8px 16px',
          fontSize: '0.875rem',
          fontWeight: 600,
          textTransform: 'none',
          boxShadow: 'none',
          '&:hover': {
            boxShadow: 'none',
          },
        },
        contained: {
          '&:hover': {
            boxShadow: '0 1px 2px 0 rgb(0 0 0 / 0.05)',
          },
        },
      },
    },
    MuiCard: {
      styleOverrides: {
        root: {
          boxShadow: '0 1px 3px 0 rgb(0 0 0 / 0.1), 0 1px 2px -1px rgb(0 0 0 / 0.1)',
          borderRadius: 8,
        },
      },
    },
    MuiTextField: {
      defaultProps: {
        variant: 'outlined',
        size: 'small',
      },
    },
    MuiSelect: {
      defaultProps: {
        variant: 'outlined',
        size: 'small',
      },
    },
    MuiChip: {
      styleOverrides: {
        root: {
          borderRadius: 6,
        },
      },
    },
    MuiAlert: {
      styleOverrides: {
        root: {
          borderRadius: 6,
        },
      },
    },
  },
})

// Dark theme variant
export const darkTheme = createTheme({
  ...theme,
  palette: {
    mode: 'dark',
    // Same rule as light, against zinc-800 paper and its 16% tints. The
    // mains are 300/400 shades, so filled controls carry dark text.
    // Without these, success/warning/error/info fell back to MUI's
    // defaults, and its #f44336 error red fails as text on paper.
    primary: {
      main: '#6aabfa', // Blue 400, lifted
      light: '#93c5fd', // Blue 300
      dark: '#3b82f6', // Blue 500
      contrastText: '#0f172a',
    },
    secondary: {
      main: '#ae96fb', // Between Violet 300 and 400
      light: '#c4b5fd', // Violet 300
      dark: '#8b5cf6', // Violet 500
      contrastText: '#0f172a',
    },
    success: {
      main: '#4ade80', // Green 400
      light: '#86efac', // Green 300
      dark: '#22c55e', // Green 500
      contrastText: '#0f172a',
    },
    error: {
      main: '#f98080', // Red 400, lifted
      light: '#fca5a5', // Red 300
      dark: '#ef4444', // Red 500
      contrastText: '#0f172a',
    },
    warning: {
      main: '#fb923c', // Orange 400
      light: '#fdba74', // Orange 300
      dark: '#f97316', // Orange 500
      contrastText: '#0f172a',
    },
    info: {
      main: '#22d3ee', // Cyan 400
      light: '#67e8f9', // Cyan 300
      dark: '#06b6d4', // Cyan 500
      contrastText: '#0f172a',
    },
    background: {
      default: '#1a1a1a', // Soft dark gray
      paper: '#27272a', // Zinc 800
    },
    text: {
      primary: '#fafafa', // Zinc 50
      secondary: '#adadb5', // Zinc 400, lifted for 4.5:1 on chip fills
      // Opaque on purpose: MUI's default is white at 50%, which composites
      // to about 4:1 on chip fills.
      disabled: '#a9a9b1',
    },
  },
})

export type ResolvedThemeMode = 'light' | 'dark'
export type ThemeMode = ResolvedThemeMode | 'auto'

export const themes: Record<ResolvedThemeMode, typeof theme> = {
  light: theme,
  dark: darkTheme,
}

export const availableThemes = [
  { id: 'auto', labelKey: 'settings.appearance.themeOptions.auto', icon: 'Monitor' },
  { id: 'light', labelKey: 'settings.appearance.themeOptions.light', icon: 'Sun' },
  { id: 'dark', labelKey: 'settings.appearance.themeOptions.dark', icon: 'Moon' },
]

export const getTheme = (mode: ResolvedThemeMode) => themes[mode]

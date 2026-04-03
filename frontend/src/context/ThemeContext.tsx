import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react'
import { ThemeProvider as MuiThemeProvider } from '@mui/material/styles'
import { ResolvedThemeMode, ThemeMode, getTheme } from '../theme'

interface ThemeContextType {
  mode: ThemeMode
  effectiveMode: ResolvedThemeMode
  toggleTheme: () => void
  setTheme: (mode: ThemeMode) => void
}

const ThemeContext = createContext<ThemeContextType | undefined>(undefined)

function getSystemThemePreference(): ResolvedThemeMode {
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

export const ThemeProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  // Initialize theme from localStorage or system preference
  const [mode, setMode] = useState<ThemeMode>(() => {
    const savedMode = localStorage.getItem('theme') as ThemeMode
    if (savedMode === 'light' || savedMode === 'dark' || savedMode === 'auto') {
      return savedMode
    }
    return 'auto'
  })
  const [effectiveMode, setEffectiveMode] = useState<ResolvedThemeMode>(() =>
    mode === 'auto' ? getSystemThemePreference() : mode
  )

  useEffect(() => {
    if (mode !== 'auto') {
      setEffectiveMode(mode)
      return
    }

    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)')
    const handleChange = (event?: MediaQueryListEvent) => {
      const prefersDark = event ? event.matches : mediaQuery.matches
      setEffectiveMode(prefersDark ? 'dark' : 'light')
    }

    handleChange()

    if (typeof mediaQuery.addEventListener === 'function') {
      mediaQuery.addEventListener('change', handleChange)
      return () => mediaQuery.removeEventListener('change', handleChange)
    }

    mediaQuery.addListener(handleChange)
    return () => mediaQuery.removeListener(handleChange)
  }, [mode])

  // Update localStorage and document class when mode changes
  useEffect(() => {
    localStorage.setItem('theme', mode)

    // Update Tailwind dark mode class
    if (effectiveMode === 'dark') {
      document.documentElement.classList.add('dark')
    } else {
      document.documentElement.classList.remove('dark')
    }
  }, [effectiveMode, mode])

  const toggleTheme = () => {
    setMode((prevMode) => {
      const themeKeys: ThemeMode[] = ['auto', 'light', 'dark']
      const currentIndex = themeKeys.indexOf(prevMode)
      const nextIndex = (currentIndex + 1) % themeKeys.length
      return themeKeys[nextIndex]
    })
  }

  const setTheme = (newMode: ThemeMode) => {
    if (newMode === 'light' || newMode === 'dark' || newMode === 'auto') {
      setMode(newMode)
    }
  }

  const activeTheme = getTheme(effectiveMode)

  return (
    <ThemeContext.Provider value={{ mode, effectiveMode, toggleTheme, setTheme }}>
      <MuiThemeProvider theme={activeTheme}>{children}</MuiThemeProvider>
    </ThemeContext.Provider>
  )
}

// eslint-disable-next-line react-refresh/only-export-components
export const useTheme = () => {
  const context = useContext(ThemeContext)
  if (context === undefined) {
    throw new Error('useTheme must be used within a ThemeProvider')
  }
  return context
}

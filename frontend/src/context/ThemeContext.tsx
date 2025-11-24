import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { ThemeProvider as MuiThemeProvider } from '@mui/material/styles';
import { ThemeMode, getTheme, themes } from '../theme';

interface ThemeContextType {
  mode: ThemeMode;
  toggleTheme: () => void;
  setTheme: (mode: ThemeMode) => void;
}

const ThemeContext = createContext<ThemeContextType | undefined>(undefined);

export const ThemeProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  // Initialize theme from localStorage or system preference
  const [mode, setMode] = useState<ThemeMode>(() => {
    const savedMode = localStorage.getItem('theme') as ThemeMode;
    if (savedMode && themes[savedMode]) {
      return savedMode;
    }
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  });

  // Update localStorage and document class when mode changes
  useEffect(() => {
    localStorage.setItem('theme', mode);

    // Update Tailwind dark mode class
    if (mode === 'dark') {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }
  }, [mode]);

  const toggleTheme = () => {
    setMode((prevMode) => {
      const themeKeys = Object.keys(themes) as ThemeMode[];
      const currentIndex = themeKeys.indexOf(prevMode);
      const nextIndex = (currentIndex + 1) % themeKeys.length;
      return themeKeys[nextIndex];
    });
  };

  const setTheme = (newMode: ThemeMode) => {
    if (themes[newMode]) {
      setMode(newMode);
    }
  };

  const activeTheme = getTheme(mode);

  return (
    <ThemeContext.Provider value={{ mode, toggleTheme, setTheme }}>
      <MuiThemeProvider theme={activeTheme}>
        {children}
      </MuiThemeProvider>
    </ThemeContext.Provider>
  );
};

export const useTheme = () => {
  const context = useContext(ThemeContext);
  if (context === undefined) {
    throw new Error('useTheme must be used within a ThemeProvider');
  }
  return context;
};

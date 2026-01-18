import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Toaster } from 'react-hot-toast'
import CssBaseline from '@mui/material/CssBaseline'
import { AuthProvider } from './hooks/useAuth.tsx'
import { AppProvider } from './context/AppContext'
import { ThemeProvider } from './context/ThemeContext'
import App from './App.tsx'
import './index.css'
import { initMatomo } from './utils/matomo'

// Initialize Matomo analytics
initMatomo()

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
      // SWR caching strategy: data stays fresh for 30s, cached for 5min
      staleTime: 30 * 1000, // 30 seconds - data considered fresh
      gcTime: 5 * 60 * 1000, // 5 minutes - data kept in cache (formerly cacheTime)
    },
  },
})

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ThemeProvider>
      <CssBaseline />
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <AuthProvider>
            <AppProvider>
              <App />
              <Toaster position="top-right" />
            </AppProvider>
          </AuthProvider>
        </BrowserRouter>
      </QueryClientProvider>
    </ThemeProvider>
  </React.StrictMode>
)

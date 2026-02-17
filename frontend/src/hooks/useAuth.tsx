import React, { useState, useEffect, createContext, useContext } from 'react'
import { authAPI, setProxyAuthMode } from '../services/api'

interface User {
  id: number
  username: string
  email: string
  is_admin: boolean
  must_change_password?: boolean
}

interface AuthContextType {
  user: User | null
  isAuthenticated: boolean
  isLoading: boolean
  mustChangePassword: boolean
  proxyAuthEnabled: boolean
  login: (username: string, password: string) => Promise<boolean>
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [proxyAuthEnabled, setProxyAuthEnabled] = useState(false)

  useEffect(() => {
    const initAuth = async () => {
      try {
        // First, check if proxy authentication is enabled
        const configResponse = await authAPI.getAuthConfig()
        const { proxy_auth_enabled } = configResponse.data
        setProxyAuthEnabled(proxy_auth_enabled)
        setProxyAuthMode(proxy_auth_enabled) // Update API interceptor

        if (proxy_auth_enabled) {
          // Proxy auth mode: backend auto-creates default user if no proxy header present
          // Just try to get the profile - backend will handle everything
          let retries = 3
          let success = false

          while (retries > 0 && !success) {
            try {
              const profileResponse = await authAPI.getProfile()
              setUser(profileResponse.data)
              success = true
            } catch (error) {
              console.error('Failed to get profile in proxy auth mode, retrying...', error)
              retries--
              if (retries > 0) {
                await new Promise((resolve) => setTimeout(resolve, 1000)) // Wait 1 second before retry
              }
            }
          }

          if (!success) {
            console.error('Failed to authenticate after retries')
          }
        } else {
          // JWT auth mode: check for token
          const token = localStorage.getItem('access_token')
          if (token) {
            try {
              const profileResponse = await authAPI.getProfile()
              setUser(profileResponse.data)
            } catch (error) {
              console.error('Failed to get profile with JWT:', error)
              localStorage.removeItem('access_token')
            }
          }
        }
      } catch (error) {
        console.error('Failed to check auth config:', error)
        // Default to JWT auth mode if config check fails
        setProxyAuthEnabled(false)
        const token = localStorage.getItem('access_token')
        if (token) {
          try {
            const profileResponse = await authAPI.getProfile()
            setUser(profileResponse.data)
          } catch {
            localStorage.removeItem('access_token')
          }
        }
      } finally {
        setIsLoading(false)
      }
    }

    initAuth()
  }, [])

  const login = async (username: string, password: string): Promise<boolean> => {
    const response = await authAPI.login(username, password)
    const { access_token, must_change_password } = response.data
    localStorage.setItem('access_token', access_token)

    const profileResponse = await authAPI.getProfile()
    setUser(profileResponse.data)

    // Return true if user must change password
    return must_change_password || false
  }

  const logout = async () => {
    try {
      await authAPI.logout()
    } catch {
      // Ignore logout errors
    }
    localStorage.removeItem('access_token')
    setUser(null)
  }

  const value = {
    user,
    isAuthenticated: !!user,
    isLoading,
    mustChangePassword: user?.must_change_password || false,
    proxyAuthEnabled,
    login,
    logout,
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAuth() {
  const context = useContext(AuthContext)
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}

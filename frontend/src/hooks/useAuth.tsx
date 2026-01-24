import React, { useState, useEffect, createContext, useContext } from 'react'
import { authAPI } from '../services/api'

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
  login: (username: string, password: string) => Promise<boolean>
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    const token = localStorage.getItem('access_token')
    if (token) {
      authAPI
        .getProfile()
        .then((response) => {
          setUser(response.data)
        })
        .catch(() => {
          console.error('Failed to get profile')
          localStorage.removeItem('access_token')
        })
        .finally(() => {
          setIsLoading(false)
        })
    } else {
      setIsLoading(false)
    }
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

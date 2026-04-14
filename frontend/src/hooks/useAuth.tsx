import React, { useState, useEffect, createContext, useContext } from 'react'
import { authAPI, setProxyAuthMode, AuthUserResponse, ProxyAuthWarning } from '../services/api'
import { translateBackendKey } from '../utils/translateBackendKey'
import { clearRecentPasswordLogin, markRecentPasswordLogin } from '../utils/passkeyPrompt'
import { getDefaultPasskeyDeviceName } from '../utils/passkeyDeviceName'

interface User extends AuthUserResponse {
  id: number
}

interface AuthContextType {
  user: User | null
  isAuthenticated: boolean
  isLoading: boolean
  hasGlobalPermission: (permission: string) => boolean
  mustChangePassword: boolean
  proxyAuthEnabled: boolean
  proxyAuthHeader: string | null
  proxyAuthWarnings: ProxyAuthWarning[]
  authError: string | null
  login: (
    username: string,
    password: string
  ) => Promise<
    | { mustChangePassword: boolean; totpRequired: false }
    | { mustChangePassword: boolean; totpRequired: true; loginChallengeToken: string }
  >
  verifyTotpLogin: (
    loginChallengeToken: string,
    code: string
  ) => Promise<{ mustChangePassword: boolean }>
  loginWithPasskey: () => Promise<{ mustChangePassword: boolean }>
  canEnrollPasskeyFromRecentLogin: boolean
  enrollPasskeyFromRecentLogin: () => Promise<void>
  clearRecentPasskeyEnrollmentState: () => void
  logout: () => Promise<void>
  refreshUser: () => Promise<void>
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [proxyAuthEnabled, setProxyAuthEnabled] = useState(false)
  const [proxyAuthHeader, setProxyAuthHeader] = useState<string | null>(null)
  const [proxyAuthWarnings, setProxyAuthWarnings] = useState<ProxyAuthWarning[]>([])
  const [authError, setAuthError] = useState<string | null>(null)
  const [recentPasswordForPasskeyPrompt, setRecentPasswordForPasskeyPrompt] = useState<
    string | null
  >(null)

  const clearRecentPasskeyEnrollmentState = () => {
    setRecentPasswordForPasskeyPrompt(null)
  }

  const refreshUser = async () => {
    const profileResponse = await authAPI.getProfile()
    setUser(profileResponse.data)
  }

  const extractAuthError = (error: unknown): { status: number | null; detail: unknown } => {
    if (!error || typeof error !== 'object' || !('response' in error)) {
      return { status: null, detail: undefined }
    }

    const response = error.response
    if (!response || typeof response !== 'object') {
      return { status: null, detail: undefined }
    }

    const status = 'status' in response ? Number(response.status) : null
    const detail =
      'data' in response &&
      response.data &&
      typeof response.data === 'object' &&
      'detail' in response.data
        ? response.data.detail
        : undefined

    return { status, detail }
  }

  useEffect(() => {
    const initAuth = async () => {
      try {
        // First, check if proxy authentication is enabled
        const configResponse = await authAPI.getAuthConfig()
        const { proxy_auth_enabled, proxy_auth_header, proxy_auth_health } = configResponse.data
        setProxyAuthEnabled(proxy_auth_enabled)
        setProxyAuthHeader(proxy_auth_header ?? null)
        setProxyAuthWarnings(proxy_auth_health?.warnings ?? [])
        setProxyAuthMode(proxy_auth_enabled) // Update API interceptor
        setAuthError(null)

        if (proxy_auth_enabled) {
          // Proxy auth mode: trust the reverse proxy, but fail closed when no identity header arrives.
          let retries = 3
          let success = false

          while (retries > 0 && !success) {
            try {
              await refreshUser()
              success = true
              setAuthError(null)
            } catch (error: unknown) {
              console.error('Failed to get profile in proxy auth mode, retrying...', error)
              const { status, detail } = extractAuthError(error)

              if (status === 401 || status === 403) {
                setAuthError(
                  translateBackendKey(
                    detail as
                      | string
                      | { key: string; params?: Record<string, unknown> }
                      | null
                      | undefined
                  )
                )
                retries = 0
                break
              }

              retries--
              if (retries > 0) {
                await new Promise((resolve) => setTimeout(resolve, 1000)) // Wait 1 second before retry
              }
            }
          }

          if (!success) {
            console.error('Failed to authenticate after retries')
            setUser(null)
            setAuthError(
              (existing) =>
                existing ??
                'Proxy authentication is enabled but Borg UI did not receive an authenticated user from the reverse proxy.'
            )
          }
        } else {
          // JWT auth mode: check for token
          const token = localStorage.getItem('access_token')
          if (token) {
            try {
              await refreshUser()
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
        setProxyAuthWarnings([])
        const token = localStorage.getItem('access_token')
        if (token) {
          try {
            await refreshUser()
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

  const login = async (
    username: string,
    password: string
  ): Promise<
    | { mustChangePassword: boolean; totpRequired: false }
    | { mustChangePassword: boolean; totpRequired: true; loginChallengeToken: string }
  > => {
    const response = await authAPI.login(username, password)
    const { access_token, must_change_password, totp_required, login_challenge_token } =
      response.data

    if (totp_required && login_challenge_token) {
      setRecentPasswordForPasskeyPrompt(password)
      return {
        mustChangePassword: must_change_password || false,
        totpRequired: true,
        loginChallengeToken: login_challenge_token,
      }
    }

    if (!access_token) {
      throw new Error('Missing access token')
    }

    localStorage.setItem('access_token', access_token)
    markRecentPasswordLogin()
    setRecentPasswordForPasskeyPrompt(password)

    await refreshUser()

    return {
      mustChangePassword: must_change_password || false,
      totpRequired: false,
    }
  }

  const verifyTotpLogin = async (loginChallengeToken: string, code: string) => {
    const response = await authAPI.verifyTotpLogin(loginChallengeToken, code)
    const { access_token, must_change_password } = response.data
    if (!access_token) {
      throw new Error('Missing access token')
    }
    localStorage.setItem('access_token', access_token)
    markRecentPasswordLogin()
    await refreshUser()
    return { mustChangePassword: must_change_password || false }
  }

  const loginWithPasskey = async () => {
    const { getPasskeyAssertion } = await import('../utils/webauthn')
    const startResponse = await authAPI.beginPasskeyAuthentication()
    const credential = await getPasskeyAssertion(startResponse.data.options)
    const finishResponse = await authAPI.finishPasskeyAuthentication(
      startResponse.data.ceremony_token,
      credential
    )
    const { access_token, must_change_password } = finishResponse.data
    if (!access_token) {
      throw new Error('Missing access token')
    }
    localStorage.setItem('access_token', access_token)
    clearRecentPasswordLogin()
    clearRecentPasskeyEnrollmentState()
    await refreshUser()
    return { mustChangePassword: must_change_password || false }
  }

  const enrollPasskeyFromRecentLogin = async () => {
    if (!recentPasswordForPasskeyPrompt) {
      throw new Error('Missing recent password confirmation')
    }

    const { createPasskeyCredential } = await import('../utils/webauthn')
    const beginResponse = await authAPI.beginPasskeyRegistration(recentPasswordForPasskeyPrompt)
    const credential = await createPasskeyCredential(beginResponse.data.options)

    await authAPI.finishPasskeyRegistration(
      beginResponse.data.ceremony_token,
      credential,
      getDefaultPasskeyDeviceName()
    )

    clearRecentPasskeyEnrollmentState()
  }

  const logout = async () => {
    try {
      await authAPI.logout()
    } catch {
      // Ignore logout errors
    }
    localStorage.removeItem('access_token')
    clearRecentPasswordLogin()
    clearRecentPasskeyEnrollmentState()
    setUser(null)
  }

  const hasGlobalPermission = (permission: string) => {
    return !!user?.global_permissions?.includes(permission)
  }

  const value = {
    user,
    isAuthenticated: !!user,
    isLoading,
    hasGlobalPermission,
    mustChangePassword: user?.must_change_password || false,
    proxyAuthEnabled,
    proxyAuthHeader,
    proxyAuthWarnings,
    authError,
    login,
    verifyTotpLogin,
    loginWithPasskey,
    canEnrollPasskeyFromRecentLogin: !!recentPasswordForPasskeyPrompt,
    enrollPasskeyFromRecentLogin,
    clearRecentPasskeyEnrollmentState,
    logout,
    refreshUser,
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

import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { toast } from 'react-hot-toast'
import { useTranslation } from 'react-i18next'
import { useAuth } from '../hooks/useAuth.tsx'
import { Eye, EyeOff, Loader2 } from 'lucide-react'
import PasswordSetupCard from './FirstLoginPasswordSetup'
import { useAnalytics } from '../hooks/useAnalytics'
import { getApiErrorDetail } from '../utils/apiErrors'
import { translateBackendKey } from '../utils/translateBackendKey'
import { authAPI } from '../services/api'
import { BASE_PATH } from '../utils/basePath'

interface LoginForm {
  username: string
  password: string
}

function hasErrorName(error: unknown, name: string) {
  return typeof error === 'object' && error !== null && 'name' in error && error.name === name
}

// ─── Component ────────────────────────────────────────────────────────────────

export default function Login() {
  const [showPasswordSetupState, setShowPasswordSetup] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [showPassword, setShowPassword] = useState(false)
  const [totpCode, setTotpCode] = useState('')
  const [pendingChallengeToken, setPendingChallengeToken] = useState<string | null>(null)
  const [pendingUsername, setPendingUsername] = useState<string | null>(null)
  const [searchParams, setSearchParams] = useSearchParams()
  const conditionalPasskeyAbortRef = useRef<AbortController | null>(null)
  const {
    login,
    verifyTotpLogin,
    loginWithOidcExchangeToken,
    loginWithPasskey,
    mustChangePassword,
    oidcEnabled,
    oidcProviderName,
    oidcDisableLocalAuth,
  } = useAuth()
  const navigate = useNavigate()
  const { t } = useTranslation()
  const { trackAuth, EventAction } = useAnalytics()

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<LoginForm>()

  const handleSuccessfulLogin = useCallback(
    (
      _username: string | null,
      mustChangePassword: boolean,
      method: 'password' | 'totp' | 'passkey' | 'passkey_autofill'
    ) => {
      trackAuth(EventAction.LOGIN, { method, requires_password_setup: mustChangePassword })
      toast.success(t('login.success'))
      if (mustChangePassword) {
        setShowPasswordSetup(true)
      } else {
        navigate('/dashboard')
      }
    },
    [EventAction.LOGIN, navigate, t, trackAuth]
  )

  useEffect(() => {
    if (pendingChallengeToken || oidcDisableLocalAuth) return

    let cancelled = false

    const startConditionalPasskey = async () => {
      try {
        const { getConditionalPasskeyAssertion, isConditionalMediationAvailable } =
          await import('../utils/webauthn')
        if (!(await isConditionalMediationAvailable())) {
          return
        }

        const startResponse = await authAPI.beginPasskeyAuthentication()
        if (cancelled) return

        conditionalPasskeyAbortRef.current = new AbortController()
        const credential = await getConditionalPasskeyAssertion(
          startResponse.data.options,
          conditionalPasskeyAbortRef.current.signal
        )
        if (cancelled) return

        setIsLoading(true)
        const finishResponse = await authAPI.finishPasskeyAuthentication(
          startResponse.data.ceremony_token,
          credential
        )
        const { access_token, must_change_password } = finishResponse.data
        if (!access_token) {
          throw new Error('Missing access token')
        }
        localStorage.setItem('access_token', access_token)
        handleSuccessfulLogin(null, must_change_password || false, 'passkey_autofill')
      } catch (error: unknown) {
        if (hasErrorName(error, 'AbortError') || cancelled) {
          return
        }
      } finally {
        if (!cancelled) {
          setIsLoading(false)
        }
      }
    }

    void startConditionalPasskey()

    return () => {
      cancelled = true
      conditionalPasskeyAbortRef.current?.abort()
      conditionalPasskeyAbortRef.current = null
    }
  }, [handleSuccessfulLogin, oidcDisableLocalAuth, pendingChallengeToken])

  useEffect(() => {
    const oidcComplete = searchParams.get('oidc') === 'complete'
    const oidcError = searchParams.get('oidc_error')

    if (oidcError) {
      toast.error(translateBackendKey({ key: oidcError }) || t('login.failed'))
      setSearchParams((current) => {
        const next = new URLSearchParams(current)
        next.delete('oidc_error')
        next.delete('oidc')
        return next
      })
      return
    }

    if (!oidcComplete) return

    let cancelled = false
    setSearchParams((current) => {
      const next = new URLSearchParams(current)
      next.delete('oidc')
      return next
    })
    setIsLoading(true)

    void (async () => {
      try {
        const result = await loginWithOidcExchangeToken()
        if (cancelled) return
        handleSuccessfulLogin(null, result.mustChangePassword, 'password')
      } catch (error: unknown) {
        if (!cancelled) {
          toast.error(translateBackendKey(getApiErrorDetail(error)) || t('login.failed'))
          setSearchParams((current) => {
            const next = new URLSearchParams(current)
            next.delete('oidc')
            return next
          })
        }
      } finally {
        if (!cancelled) {
          setIsLoading(false)
        }
      }
    })()

    return () => {
      cancelled = true
    }
  }, [handleSuccessfulLogin, loginWithOidcExchangeToken, searchParams, setSearchParams, t])

  const onSubmit = async (data: LoginForm) => {
    setIsLoading(true)
    try {
      const result = await login(data.username, data.password)
      if (result.totpRequired) {
        setPendingChallengeToken(result.loginChallengeToken)
        setPendingUsername(data.username)
        setTotpCode('')
        toast.success(t('login.totpRequired'))
      } else {
        handleSuccessfulLogin(data.username, result.mustChangePassword, 'password')
      }
    } catch (error: unknown) {
      toast.error(translateBackendKey(getApiErrorDetail(error)) || t('login.failed'))
    } finally {
      setIsLoading(false)
    }
  }

  const onSubmitTotp = async () => {
    if (!pendingChallengeToken || !pendingUsername) return
    setIsLoading(true)
    try {
      const result = await verifyTotpLogin(pendingChallengeToken, totpCode)
      handleSuccessfulLogin(pendingUsername, result.mustChangePassword, 'totp')
    } catch (error: unknown) {
      toast.error(translateBackendKey(getApiErrorDetail(error)) || t('login.failed'))
    } finally {
      setIsLoading(false)
    }
  }

  const onSubmitPasskey = async () => {
    setIsLoading(true)
    trackAuth(EventAction.START, { method: 'passkey', surface: 'login' })
    try {
      conditionalPasskeyAbortRef.current?.abort()
      conditionalPasskeyAbortRef.current = null
      const result = await loginWithPasskey()
      handleSuccessfulLogin(null, result.mustChangePassword, 'passkey')
    } catch (error: unknown) {
      if (
        hasErrorName(error, 'NotAllowedError') ||
        hasErrorName(error, 'AbortError') ||
        hasErrorName(error, 'InvalidStateError')
      ) {
        trackAuth('Cancel', { method: 'passkey', surface: 'login' })
        toast.error(t('login.passkeyCancelled'))
      } else {
        trackAuth(EventAction.FAIL, { method: 'passkey', surface: 'login' })
        toast.error(translateBackendKey(getApiErrorDetail(error)) || t('login.failed'))
      }
    } finally {
      setIsLoading(false)
    }
  }

  const startOidcLogin = () => {
    const returnTo = `${window.location.origin}${BASE_PATH}/login`
    window.location.assign(authAPI.getOidcLoginUrl(returnTo))
  }

  const showPasswordSetup = mustChangePassword || showPasswordSetupState

  if (showPasswordSetup) {
    return <PasswordSetupCard onComplete={() => navigate('/dashboard')} />
  }

  return (
    <>
      {/* Heading */}
      <div style={{ marginBottom: 28 }}>
        <h2
          style={{
            fontSize: '1.375rem',
            fontWeight: 600,
            color: '#f1f5f9',
            margin: '0 0 6px',
            letterSpacing: '-0.01em',
          }}
        >
          {t('login.submit')}
        </h2>
        <p style={{ margin: 0, fontSize: 14, color: '#64748b' }}>{t('login.subtitle')}</p>
      </div>

      {/* Form */}
      <form onSubmit={handleSubmit(onSubmit)} noValidate>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
          {!pendingChallengeToken ? (
            <>
              {oidcEnabled ? (
                <button
                  type="button"
                  disabled={isLoading}
                  onClick={startOidcLogin}
                  style={{
                    width: '100%',
                    padding: '11px 20px',
                    borderRadius: 8,
                    border: '1px solid rgba(0,221,0,0.4)',
                    background: 'rgba(0,221,0,0.08)',
                    color: '#d9f99d',
                    fontSize: 14,
                    fontWeight: 600,
                    cursor: isLoading ? 'not-allowed' : 'pointer',
                    fontFamily: 'inherit',
                  }}
                >
                  {t('login.ssoSubmit', {
                    provider: oidcProviderName || t('login.ssoDefaultProvider'),
                  })}
                </button>
              ) : null}

              {!oidcDisableLocalAuth ? (
                <>
                  {oidcEnabled ? (
                    <p
                      style={{
                        margin: '-4px 0 0',
                        fontSize: 12,
                        color: '#64748b',
                        textAlign: 'center',
                      }}
                    >
                      {t('login.ssoOrLocalHint')}
                    </p>
                  ) : null}

                  <div>
                    <label
                      htmlFor="username"
                      style={{
                        display: 'block',
                        fontSize: 13,
                        fontWeight: 500,
                        color: '#94a3b8',
                        marginBottom: 6,
                        letterSpacing: '0.01em',
                      }}
                    >
                      {t('login.username')}
                    </label>
                    <input
                      {...register('username', {
                        required: t('login.errors.usernameRequired'),
                      })}
                      id="username"
                      type="text"
                      autoComplete="username webauthn"
                      placeholder="admin"
                      className={`borg-card-input${errors.username ? ' error' : ''}`}
                    />
                    {errors.username && (
                      <p style={{ margin: '5px 0 0', fontSize: 12, color: '#f87171' }} role="alert">
                        {errors.username.message}
                      </p>
                    )}
                  </div>

                  <div>
                    <label
                      htmlFor="password"
                      style={{
                        display: 'block',
                        fontSize: 13,
                        fontWeight: 500,
                        color: '#94a3b8',
                        marginBottom: 6,
                        letterSpacing: '0.01em',
                      }}
                    >
                      {t('login.password')}
                    </label>
                    <div style={{ position: 'relative' }}>
                      <input
                        {...register('password', {
                          required: t('login.errors.passwordRequired'),
                        })}
                        id="password"
                        type={showPassword ? 'text' : 'password'}
                        autoComplete="current-password"
                        placeholder="••••••••"
                        style={{ paddingRight: 42 }}
                        className={`borg-card-input${errors.password ? ' error' : ''}`}
                      />
                      <button
                        type="button"
                        onClick={() => setShowPassword((v) => !v)}
                        aria-label={showPassword ? 'Hide password' : 'Show password'}
                        style={{
                          position: 'absolute',
                          right: 12,
                          top: '50%',
                          transform: 'translateY(-50%)',
                          background: 'none',
                          border: 'none',
                          cursor: 'pointer',
                          color: '#64748b',
                          display: 'flex',
                          alignItems: 'center',
                          padding: 4,
                          borderRadius: 4,
                          transition: 'color 0.15s ease',
                        }}
                        onMouseEnter={(e) => (e.currentTarget.style.color = '#94a3b8')}
                        onMouseLeave={(e) => (e.currentTarget.style.color = '#64748b')}
                      >
                        {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                      </button>
                    </div>
                    {errors.password && (
                      <p style={{ margin: '5px 0 0', fontSize: 12, color: '#f87171' }} role="alert">
                        {errors.password.message}
                      </p>
                    )}
                  </div>
                </>
              ) : (
                <p style={{ margin: 0, fontSize: 13, color: '#94a3b8', lineHeight: 1.6 }}>
                  {t('login.localAuthDisabledHint')}
                </p>
              )}
            </>
          ) : (
            <div style={{ display: 'grid', gap: 10 }}>
              <p style={{ margin: 0, fontSize: 14, color: '#94a3b8', lineHeight: 1.6 }}>
                {t('login.totpPrompt')}
              </p>
              <div>
                <label
                  htmlFor="totp-code"
                  style={{
                    display: 'block',
                    fontSize: 13,
                    fontWeight: 500,
                    color: '#94a3b8',
                    marginBottom: 6,
                    letterSpacing: '0.01em',
                  }}
                >
                  {t('login.totpLabel')}
                </label>
                <input
                  id="totp-code"
                  type="text"
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  placeholder="123456"
                  className="borg-card-input"
                  value={totpCode}
                  onChange={(event) => setTotpCode(event.target.value)}
                />
                <p style={{ margin: '5px 0 0', fontSize: 12, color: '#64748b' }}>
                  {t('login.totpHint')}
                </p>
              </div>
            </div>
          )}

          {(!oidcDisableLocalAuth || pendingChallengeToken) && (
            <button
              type={pendingChallengeToken ? 'button' : 'submit'}
              onClick={pendingChallengeToken ? () => void onSubmitTotp() : undefined}
              disabled={isLoading}
              style={{
                marginTop: 4,
                width: '100%',
                padding: '11px 20px',
                borderRadius: 8,
                border: 'none',
                background: isLoading
                  ? 'rgba(0,221,0,0.4)'
                  : 'linear-gradient(135deg, #00dd00 0%, #00b800 100%)',
                color: isLoading ? 'rgba(0,0,0,0.5)' : '#000',
                fontSize: 14,
                fontWeight: 600,
                cursor: isLoading ? 'not-allowed' : 'pointer',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: 8,
                transition: 'opacity 0.2s ease, transform 0.1s ease, box-shadow 0.2s ease',
                fontFamily: 'inherit',
                letterSpacing: '0.01em',
                boxShadow: isLoading ? 'none' : '0 4px 16px rgba(0,221,0,0.25)',
              }}
              onMouseEnter={(e) => {
                if (!isLoading) {
                  e.currentTarget.style.opacity = '0.9'
                  e.currentTarget.style.transform = 'translateY(-1px)'
                  e.currentTarget.style.boxShadow = '0 6px 24px rgba(0,221,0,0.35)'
                }
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.opacity = '1'
                e.currentTarget.style.transform = 'translateY(0)'
                e.currentTarget.style.boxShadow = isLoading
                  ? 'none'
                  : '0 4px 16px rgba(0,221,0,0.25)'
              }}
              onMouseDown={(e) => {
                if (!isLoading) e.currentTarget.style.transform = 'translateY(0)'
              }}
            >
              {isLoading ? (
                <>
                  <Loader2 size={15} style={{ animation: 'spin 1s linear infinite' }} />
                  {t('login.submitting')}
                </>
              ) : pendingChallengeToken ? (
                t('login.verifyTotp')
              ) : (
                t('login.submit')
              )}
            </button>
          )}
          {pendingChallengeToken && (
            <button
              type="button"
              disabled={isLoading}
              onClick={() => {
                setPendingChallengeToken(null)
                setPendingUsername(null)
                setTotpCode('')
              }}
              style={{
                width: '100%',
                padding: '11px 20px',
                borderRadius: 8,
                border: '1px solid rgba(255,255,255,0.12)',
                background: 'transparent',
                color: '#cbd5e1',
                fontSize: 14,
                fontWeight: 600,
                cursor: isLoading ? 'not-allowed' : 'pointer',
                fontFamily: 'inherit',
              }}
            >
              {t('common.buttons.back')}
            </button>
          )}
          {!pendingChallengeToken && !oidcDisableLocalAuth && (
            <button
              type="button"
              disabled={isLoading}
              onClick={() => void onSubmitPasskey()}
              style={{
                width: '100%',
                padding: '11px 20px',
                borderRadius: 8,
                border: '1px solid rgba(255,255,255,0.12)',
                background: 'transparent',
                color: '#cbd5e1',
                fontSize: 14,
                fontWeight: 600,
                cursor: isLoading ? 'not-allowed' : 'pointer',
                fontFamily: 'inherit',
              }}
            >
              {t('login.passkeySubmit')}
            </button>
          )}
        </div>
      </form>
    </>
  )
}

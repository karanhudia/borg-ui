import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { toast } from 'react-hot-toast'
import { useTranslation } from 'react-i18next'
import { useAuth } from '../hooks/useAuth.tsx'
import { Eye, EyeOff, Loader2 } from 'lucide-react'
import { useAnalytics } from '../hooks/useAnalytics'
import { getApiErrorDetail } from '../utils/apiErrors'
import { translateBackendKey } from '../utils/translateBackendKey'
import { authAPI } from '../services/api'
import { BASE_PATH } from '@/utils/basePath'
import {
  hasSeenPasswordSetupPrompt,
  markPasswordSetupPromptSeen,
} from '../utils/passwordSetupPrompt'

interface LoginForm {
  username: string
  password: string
}

function hasErrorName(error: unknown, name: string) {
  return typeof error === 'object' && error !== null && 'name' in error && error.name === name
}

// ─── Animated background nodes ────────────────────────────────────────────────

interface NodeProps {
  x: string
  y: string
  delay: string
  duration: string
  size: number
  opacity: number
}

const ArchiveNode = ({ x, y, delay, duration, size, opacity }: NodeProps) => (
  <div
    aria-hidden="true"
    style={{
      position: 'absolute',
      left: x,
      top: y,
      width: size,
      height: size,
      borderRadius: '50%',
      border: `1px solid rgba(0, 221, 0, ${opacity * 0.6})`,
      backgroundColor: `rgba(0, 221, 0, ${opacity * 0.08})`,
      animation: `borgPulse ${duration} ease-in-out ${delay} infinite`,
      pointerEvents: 'none',
    }}
  />
)

const FloatingDot = ({
  x,
  y,
  delay,
  duration,
}: {
  x: string
  y: string
  delay: string
  duration: string
}) => (
  <div
    aria-hidden="true"
    style={{
      position: 'absolute',
      left: x,
      top: y,
      width: 3,
      height: 3,
      borderRadius: '50%',
      backgroundColor: 'rgba(0, 221, 0, 0.5)',
      animation: `borgFloat ${duration} ease-in-out ${delay} infinite`,
      pointerEvents: 'none',
    }}
  />
)

// ─── Component ────────────────────────────────────────────────────────────────

export default function Login() {
  const [isLoading, setIsLoading] = useState(false)
  const [showPassword, setShowPassword] = useState(false)
  const [totpCode, setTotpCode] = useState('')
  const [pendingChallengeToken, setPendingChallengeToken] = useState<string | null>(null)
  const [pendingUsername, setPendingUsername] = useState<string | null>(null)
  const conditionalPasskeyAbortRef = useRef<AbortController | null>(null)
  const { login, verifyTotpLogin, loginWithPasskey } = useAuth()
  const navigate = useNavigate()
  const { t } = useTranslation()
  const { trackAuth, EventAction } = useAnalytics()

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<LoginForm>()

  const handleSuccessfulLogin = useCallback(
    (username: string | null, mustChangePassword: boolean) => {
      trackAuth(EventAction.LOGIN)
      if (mustChangePassword) {
        if (username && hasSeenPasswordSetupPrompt(username)) {
          toast.success(t('login.success'))
          navigate('/dashboard')
        } else {
          if (username) {
            markPasswordSetupPromptSeen(username)
          }
          toast.success(t('login.successChangePassword'))
          navigate('/settings/account')
        }
      } else {
        toast.success(t('login.success'))
        navigate('/dashboard')
      }
    },
    [EventAction.LOGIN, navigate, t, trackAuth]
  )

  useEffect(() => {
    if (pendingChallengeToken) return

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
        handleSuccessfulLogin(null, must_change_password || false)
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
  }, [handleSuccessfulLogin, pendingChallengeToken])

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
        handleSuccessfulLogin(data.username, result.mustChangePassword)
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
      handleSuccessfulLogin(pendingUsername, result.mustChangePassword)
    } catch (error: unknown) {
      toast.error(translateBackendKey(getApiErrorDetail(error)) || t('login.failed'))
    } finally {
      setIsLoading(false)
    }
  }

  const onSubmitPasskey = async () => {
    setIsLoading(true)
    try {
      conditionalPasskeyAbortRef.current?.abort()
      conditionalPasskeyAbortRef.current = null
      const result = await loginWithPasskey()
      handleSuccessfulLogin(null, result.mustChangePassword)
    } catch (error: unknown) {
      if (
        hasErrorName(error, 'NotAllowedError') ||
        hasErrorName(error, 'AbortError') ||
        hasErrorName(error, 'InvalidStateError')
      ) {
        toast.error(t('login.passkeyCancelled'))
      } else {
        toast.error(translateBackendKey(getApiErrorDetail(error)) || t('login.failed'))
      }
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <>
      {/* ── Keyframe definitions ────────────────────────────────────────────── */}
      <style>{`
        @keyframes borgPulse {
          0%, 100% { transform: scale(1); opacity: 1; }
          50% { transform: scale(1.18); opacity: 0.4; }
        }
        @keyframes borgFloat {
          0%, 100% { transform: translateY(0px); opacity: 0.5; }
          50% { transform: translateY(-12px); opacity: 1; }
        }
        @keyframes borgFadeIn {
          from { opacity: 0; transform: translateY(12px); }
          to { opacity: 1; transform: translateY(0); }
        }
        @keyframes borgScan {
          0% { background-position: 0 0; }
          100% { background-position: 0 40px; }
        }
        @keyframes borgGlow {
          0%, 100% { box-shadow: 0 0 20px rgba(0,221,0,0.15); }
          50% { box-shadow: 0 0 40px rgba(0,221,0,0.35); }
        }
        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
        .borg-card-input {
          width: 100%;
          box-sizing: border-box;
          padding: 10px 14px;
          background: rgba(255,255,255,0.04);
          border: 1px solid rgba(255,255,255,0.1);
          border-radius: 8px;
          color: #e2e8f0;
          font-size: 14px;
          outline: none;
          transition: border-color 0.2s ease, background 0.2s ease, box-shadow 0.2s ease;
          font-family: inherit;
        }
        .borg-card-input::placeholder {
          color: rgba(148,163,184,0.5);
        }
        .borg-card-input:focus {
          border-color: rgba(0,221,0,0.5);
          background: rgba(0,221,0,0.04);
          box-shadow: 0 0 0 3px rgba(0,221,0,0.08);
        }
        .borg-card-input.error {
          border-color: rgba(239,68,68,0.5);
        }
        .borg-card-input.error:focus {
          border-color: rgba(239,68,68,0.6);
          box-shadow: 0 0 0 3px rgba(239,68,68,0.08);
        }
        @media (prefers-reduced-motion: reduce) {
          @keyframes borgPulse { 0%, 100% { opacity: 1; } }
          @keyframes borgFloat { 0%, 100% { opacity: 0.5; } }
          @keyframes borgFadeIn { from { opacity: 0; } to { opacity: 1; } }
          @keyframes borgScan { 0%, 100% {} }
          @keyframes borgGlow { 0%, 100% {} }
        }
      `}</style>

      <div
        className="flex-col lg:flex-row lg:h-screen"
        style={{
          minHeight: '100vh',
          display: 'flex',
          backgroundColor: '#080808',
          fontFamily: "'Inter', system-ui, -apple-system, sans-serif",
          overflow: 'hidden',
        }}
      >
        {/* ── LEFT: Brand panel (full-width on mobile, side panel on desktop) ── */}
        <div
          className="flex lg:w-[52%] xl:w-[55%]"
          style={{
            position: 'relative',
            overflow: 'hidden',
            backgroundColor: '#040a04',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            padding: '24px 32px',
          }}
        >
          {/* Grid dot pattern */}
          <div
            aria-hidden="true"
            style={{
              position: 'absolute',
              inset: 0,
              backgroundImage: 'radial-gradient(circle, rgba(0,221,0,0.12) 1px, transparent 1px)',
              backgroundSize: '28px 28px',
              animation: 'borgScan 8s linear infinite',
              maskImage: 'radial-gradient(ellipse 80% 80% at 50% 50%, black 40%, transparent 100%)',
            }}
          />

          {/* Radial vignette */}
          <div
            aria-hidden="true"
            style={{
              position: 'absolute',
              inset: 0,
              background:
                'radial-gradient(ellipse 70% 70% at 50% 50%, transparent 30%, rgba(4,10,4,0.85) 100%)',
              pointerEvents: 'none',
            }}
          />

          {/* Floating archive nodes */}
          <ArchiveNode x="8%" y="12%" delay="0s" duration="4.2s" size={48} opacity={0.7} />
          <ArchiveNode x="78%" y="8%" delay="1.1s" duration="5.5s" size={32} opacity={0.5} />
          <ArchiveNode x="85%" y="72%" delay="0.5s" duration="3.8s" size={56} opacity={0.6} />
          <ArchiveNode x="6%" y="78%" delay="2s" duration="6s" size={40} opacity={0.4} />
          <ArchiveNode x="55%" y="88%" delay="0.8s" duration="4.7s" size={28} opacity={0.5} />
          <ArchiveNode x="22%" y="45%" delay="1.5s" duration="5s" size={20} opacity={0.3} />
          <FloatingDot x="35%" y="18%" delay="0s" duration="3.5s" />
          <FloatingDot x="65%" y="30%" delay="0.8s" duration="4.2s" />
          <FloatingDot x="15%" y="60%" delay="1.4s" duration="3.8s" />
          <FloatingDot x="80%" y="45%" delay="0.3s" duration="5s" />
          <FloatingDot x="45%" y="72%" delay="1.8s" duration="4.6s" />

          {/* Center brand content */}
          <div
            style={{
              position: 'relative',
              zIndex: 10,
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              textAlign: 'center',
              animation: 'borgFadeIn 0.6s ease-out both',
            }}
          >
            {/* Logo with glow ring */}
            <div
              style={{
                position: 'relative',
                marginBottom: 12,
                animation: 'borgGlow 3s ease-in-out infinite',
                borderRadius: 30,
              }}
            >
              <div
                aria-hidden="true"
                style={{
                  position: 'absolute',
                  inset: -16,
                  borderRadius: '50%',
                  background: 'radial-gradient(circle, rgba(0,221,0,0.2) 0%, transparent 70%)',
                }}
              />
              {/* Sidebar-matching logo container */}
              <div
                style={{
                  width: 72,
                  height: 72,
                  borderRadius: 30,
                  background: 'linear-gradient(135deg, #065f46 0%, #059669 100%)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  padding: 11,
                  boxShadow: '0 4px 14px rgba(5,150,105,0.4)',
                  flexShrink: 0,
                }}
              >
                <img
                  src={`${BASE_PATH}/logo.png`}
                  alt="BorgUI"
                  style={{
                    width: '100%',
                    height: '100%',
                    objectFit: 'contain',
                    filter: 'brightness(2.2) contrast(1.1)',
                  }}
                />
              </div>
            </div>

            {/* App name + version badge — mirrors sidebar typography */}
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 10,
                marginTop: 20,
                marginBottom: 20,
              }}
            >
              <h1
                style={{
                  fontSize: '2rem',
                  fontWeight: 700,
                  color: '#f1f5f9',
                  letterSpacing: '0.14em',
                  textTransform: 'uppercase',
                  margin: 0,
                  lineHeight: 1.1,
                }}
              >
                Borg UI
              </h1>
              <span
                style={{
                  fontSize: '0.75rem',
                  fontWeight: 700,
                  letterSpacing: '0.04em',
                  padding: '3px 7px',
                  borderRadius: 6,
                  background: 'rgba(5,150,105,0.15)',
                  border: '1px solid rgba(5,150,105,0.35)',
                  color: '#34d399',
                  lineHeight: 1.5,
                  userSelect: 'none',
                }}
              >
                2.0
              </span>
            </div>

            {/* Tagline -- desktop only */}
            <p
              className="hidden lg:block"
              style={{
                fontSize: '1.05rem',
                color: '#94a3b8',
                maxWidth: 340,
                lineHeight: 1.6,
                margin: '0 0 40px',
              }}
            >
              {t('login.tagline')}
            </p>
          </div>

          {/* Bottom decoration — desktop only */}
          <div
            aria-hidden="true"
            className="hidden lg:block"
            style={{
              position: 'absolute',
              bottom: 24,
              left: '50%',
              transform: 'translateX(-50%)',
              fontSize: 11,
              color: 'rgba(148,163,184,0.35)',
              fontFamily: "'JetBrains Mono', monospace",
              letterSpacing: '0.08em',
              whiteSpace: 'nowrap',
            }}
          >
            borgbackup · encrypted · open-source
          </div>
        </div>

        {/* ── RIGHT: Form panel ──────────────────────────────────────────────── */}
        <div
          className="px-5 lg:px-12 xl:px-16 justify-start lg:justify-center"
          style={{
            flex: 1,
            minWidth: 0,
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            paddingTop: 24,
            paddingBottom: 24,
            position: 'relative',
          }}
        >
          {/* Subtle corner glow — kept inside viewport */}
          <div
            aria-hidden="true"
            style={{
              position: 'absolute',
              top: 0,
              right: 0,
              width: 280,
              height: 280,
              borderRadius: '50%',
              background: 'radial-gradient(circle, rgba(0,221,0,0.06) 0%, transparent 70%)',
              pointerEvents: 'none',
              transform: 'translate(40%, -40%)',
            }}
          />

          <div
            style={{
              width: '100%',
              maxWidth: 400,
              animation: 'borgFadeIn 0.5s ease-out 0.1s both',
            }}
          >
            {/* Card */}
            <div
              style={{
                background: 'rgba(255,255,255,0.03)',
                border: '1px solid rgba(255,255,255,0.08)',
                borderRadius: 16,
                padding: '36px 28px',
                backdropFilter: 'blur(12px)',
              }}
            >
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
                          <p
                            style={{ margin: '5px 0 0', fontSize: 12, color: '#f87171' }}
                            role="alert"
                          >
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
                          <p
                            style={{ margin: '5px 0 0', fontSize: 12, color: '#f87171' }}
                            role="alert"
                          >
                            {errors.password.message}
                          </p>
                        )}
                      </div>
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

                  {/* Submit */}
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
                  {!pendingChallengeToken && (
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
            </div>
          </div>
        </div>
      </div>
    </>
  )
}

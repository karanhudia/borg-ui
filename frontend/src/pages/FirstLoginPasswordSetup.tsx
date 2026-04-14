import { useEffect, useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { toast } from 'react-hot-toast'
import { Eye, EyeOff, Loader2, ArrowRight } from 'lucide-react'
import { useAuth } from '../hooks/useAuth'
import { useAnalytics } from '../hooks/useAnalytics'
import { getApiErrorDetail } from '../utils/apiErrors'
import { translateBackendKey } from '../utils/translateBackendKey'

/**
 * Card content shown inside the Login page's AuthLayout when the user
 * needs to set a new password after first login. Not a standalone page.
 */
export default function PasswordSetupCard({ onComplete }: { onComplete: () => void }) {
  const { t } = useTranslation()
  const { canChangePasswordFromRecentLogin, changePasswordFromRecentLogin, skipPasswordSetup } =
    useAuth()
  const { trackAuth, EventAction } = useAnalytics()
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [showNewPassword, setShowNewPassword] = useState(false)
  const [showConfirmPassword, setShowConfirmPassword] = useState(false)

  useEffect(() => {
    trackAuth(EventAction.VIEW, { surface: 'first_login_password_setup' })
  }, [EventAction.VIEW, trackAuth])

  const changePasswordMutation = useMutation({
    mutationFn: async () => changePasswordFromRecentLogin(newPassword),
    onSuccess: () => {
      trackAuth(EventAction.COMPLETE, {
        surface: 'first_login_password_setup',
        operation: 'change_password',
      })
      toast.success(t('settings.toasts.passwordChanged'))
      onComplete()
    },
    onError: (error: unknown) => {
      trackAuth(EventAction.FAIL, {
        surface: 'first_login_password_setup',
        operation: 'change_password',
      })
      toast.error(
        translateBackendKey(getApiErrorDetail(error)) || t('settings.toasts.failedToChangePassword')
      )
    },
  })

  const skipSetupMutation = useMutation({
    mutationFn: async () => skipPasswordSetup(),
    onSuccess: () => {
      trackAuth('Skip', {
        surface: 'first_login_password_setup',
        operation: 'change_password',
      })
      onComplete()
    },
    onError: (error: unknown) => {
      trackAuth(EventAction.FAIL, {
        surface: 'first_login_password_setup',
        operation: 'skip_password_change',
      })
      toast.error(
        translateBackendKey(getApiErrorDetail(error)) || t('common.errors.unexpectedError')
      )
    },
  })

  const passwordsMismatch = confirmPassword !== '' && newPassword !== confirmPassword
  const isLoading = changePasswordMutation.isPending || skipSetupMutation.isPending
  const canSubmit =
    !isLoading && canChangePasswordFromRecentLogin && !!newPassword && !!confirmPassword

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (passwordsMismatch) {
      trackAuth(EventAction.FAIL, {
        surface: 'first_login_password_setup',
        operation: 'change_password_validation',
        reason: 'password_mismatch',
      })
      toast.error(t('settings.toasts.passwordsDoNotMatch'))
      return
    }
    void changePasswordMutation.mutateAsync()
  }

  const handleSkip = () => {
    void skipSetupMutation.mutateAsync()
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
          {t('firstLoginSetup.title')}
        </h2>
        <p style={{ margin: 0, fontSize: 14, color: '#64748b' }}>
          {t('firstLoginSetup.description')}
        </p>
      </div>

      {/* Form */}
      <form onSubmit={handleSubmit} noValidate>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
          {/* New password */}
          <div>
            <label
              htmlFor="new-password"
              style={{
                display: 'block',
                fontSize: 13,
                fontWeight: 500,
                color: '#94a3b8',
                marginBottom: 6,
                letterSpacing: '0.01em',
              }}
            >
              {t('settings.password.new')}
            </label>
            <div style={{ position: 'relative' }}>
              <input
                id="new-password"
                type={showNewPassword ? 'text' : 'password'}
                autoComplete="new-password"
                placeholder="••••••••"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                className="borg-card-input"
                style={{ paddingRight: 42 }}
              />
              <button
                type="button"
                onClick={() => setShowNewPassword((v) => !v)}
                aria-label={showNewPassword ? 'Hide password' : 'Show password'}
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
                {showNewPassword ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </div>
          </div>

          {/* Confirm password */}
          <div>
            <label
              htmlFor="confirm-password"
              style={{
                display: 'block',
                fontSize: 13,
                fontWeight: 500,
                color: '#94a3b8',
                marginBottom: 6,
                letterSpacing: '0.01em',
              }}
            >
              {t('settings.password.confirm')}
            </label>
            <div style={{ position: 'relative' }}>
              <input
                id="confirm-password"
                type={showConfirmPassword ? 'text' : 'password'}
                autoComplete="new-password"
                placeholder="••••••••"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                className={`borg-card-input${passwordsMismatch ? ' error' : ''}`}
                style={{ paddingRight: 42 }}
              />
              <button
                type="button"
                onClick={() => setShowConfirmPassword((v) => !v)}
                aria-label={showConfirmPassword ? 'Hide password' : 'Show password'}
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
                {showConfirmPassword ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </div>
            {passwordsMismatch && (
              <p style={{ margin: '5px 0 0', fontSize: 12, color: '#f87171' }} role="alert">
                {t('settings.password.noMatch')}
              </p>
            )}
          </div>

          {/* Primary action */}
          <button
            type="submit"
            disabled={!canSubmit}
            style={{
              marginTop: 4,
              width: '100%',
              padding: '11px 20px',
              borderRadius: 8,
              border: 'none',
              background: !canSubmit
                ? 'rgba(0,221,0,0.25)'
                : isLoading
                  ? 'rgba(0,221,0,0.4)'
                  : 'linear-gradient(135deg, #00dd00 0%, #00b800 100%)',
              color: !canSubmit ? 'rgba(0,0,0,0.4)' : '#000',
              fontSize: 14,
              fontWeight: 600,
              cursor: !canSubmit ? 'not-allowed' : 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: 8,
              transition: 'opacity 0.2s ease, transform 0.1s ease, box-shadow 0.2s ease',
              fontFamily: 'inherit',
              letterSpacing: '0.01em',
              boxShadow: canSubmit ? '0 4px 16px rgba(0,221,0,0.25)' : 'none',
            }}
            onMouseEnter={(e) => {
              if (canSubmit) {
                e.currentTarget.style.opacity = '0.9'
                e.currentTarget.style.transform = 'translateY(-1px)'
                e.currentTarget.style.boxShadow = '0 6px 24px rgba(0,221,0,0.35)'
              }
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.opacity = '1'
              e.currentTarget.style.transform = 'translateY(0)'
              e.currentTarget.style.boxShadow = canSubmit ? '0 4px 16px rgba(0,221,0,0.25)' : 'none'
            }}
            onMouseDown={(e) => {
              if (canSubmit) e.currentTarget.style.transform = 'translateY(0)'
            }}
          >
            {isLoading ? (
              <>
                <Loader2 size={15} style={{ animation: 'spin 1s linear infinite' }} />
                {t('login.submitting')}
              </>
            ) : (
              <>
                {t('common.buttons.next')}
                <ArrowRight size={15} />
              </>
            )}
          </button>

          {/* Skip */}
          <button
            type="button"
            onClick={handleSkip}
            disabled={isLoading}
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
            {skipSetupMutation.isPending ? 'Loading...' : t('firstLoginSetup.skip')}
          </button>
        </div>
      </form>

      {/* Skip hint */}
      <p style={{ margin: '16px 0 0', fontSize: 12, color: '#4a5568', textAlign: 'center' }}>
        {t('firstLoginSetup.skipHint')}
      </p>
    </>
  )
}

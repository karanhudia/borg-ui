import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { toast } from 'react-hot-toast'
import { useTranslation } from 'react-i18next'
import { useAuth } from '../hooks/useAuth.tsx'
import { Shield } from 'lucide-react'
import { useMatomo } from '../hooks/useMatomo'

interface LoginForm {
  username: string
  password: string
}

export default function Login() {
  const [isLoading, setIsLoading] = useState(false)
  const { login } = useAuth()
  const navigate = useNavigate()
  const { t } = useTranslation()
  const { trackAuth, EventAction } = useMatomo()

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<LoginForm>()

  const onSubmit = async (data: LoginForm) => {
    setIsLoading(true)
    try {
      const mustChangePassword = await login(data.username, data.password)

      // Track successful login
      trackAuth(EventAction.LOGIN)

      if (mustChangePassword) {
        toast.success(t('login.successChangePassword'))
        navigate('/settings/account')
      } else {
        toast.success(t('login.success'))
        navigate('/dashboard')
      }
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } catch (error: any) {
      toast.error(error.response?.data?.detail || t('login.failed'))
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-[#1a1a1a] py-12 px-4 sm:px-6 lg:px-8">
      <div className="max-w-md w-full space-y-8">
        <div>
          <div className="mx-auto h-12 w-12 flex items-center justify-center rounded-full bg-primary-100 dark:bg-primary-900">
            <Shield className="h-6 w-6 text-primary-600 dark:text-primary-400" />
          </div>
          <h2 className="mt-6 text-center text-3xl font-extrabold text-gray-900 dark:text-white">
            {t('login.title')}
          </h2>
          <p className="mt-2 text-center text-sm text-gray-600 dark:text-gray-400">
            {t('login.subtitle')}
          </p>
        </div>
        <form className="mt-8 space-y-6" onSubmit={handleSubmit(onSubmit)}>
          <div className="rounded-md shadow-sm -space-y-px">
            <div>
              <label htmlFor="username" className="sr-only">
                {t('login.username')}
              </label>
              <input
                {...register('username', { required: t('login.errors.usernameRequired') })}
                id="username"
                name="username"
                type="text"
                autoComplete="username"
                className={`appearance-none rounded-none relative block w-full px-3 py-2 border ${
                  errors.username
                    ? 'border-danger-300 dark:border-danger-600'
                    : 'border-gray-300 dark:border-gray-600'
                } placeholder-gray-500 dark:placeholder-gray-400 text-gray-900 dark:text-white bg-white dark:bg-[#27272a] rounded-t-md focus:outline-none focus:ring-primary-500 focus:border-primary-500 focus:z-10 sm:text-sm`}
                placeholder={t('login.username')}
              />
              {errors.username && (
                <p className="mt-1 text-sm text-danger-600">{errors.username.message}</p>
              )}
            </div>
            <div>
              <label htmlFor="password" className="sr-only">
                {t('login.password')}
              </label>
              <input
                {...register('password', { required: t('login.errors.passwordRequired') })}
                id="password"
                name="password"
                type="password"
                autoComplete="current-password"
                className={`appearance-none rounded-none relative block w-full px-3 py-2 border ${
                  errors.password
                    ? 'border-danger-300 dark:border-danger-600'
                    : 'border-gray-300 dark:border-gray-600'
                } placeholder-gray-500 dark:placeholder-gray-400 text-gray-900 dark:text-white bg-white dark:bg-[#27272a] rounded-b-md focus:outline-none focus:ring-primary-500 focus:border-primary-500 focus:z-10 sm:text-sm`}
                placeholder={t('login.password')}
              />
              {errors.password && (
                <p className="mt-1 text-sm text-danger-600">{errors.password.message}</p>
              )}
            </div>
          </div>

          <div>
            <button
              type="submit"
              disabled={isLoading}
              className="group relative w-full flex justify-center py-2 px-4 border border-transparent text-sm font-medium rounded-md text-white bg-primary-600 hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-500 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isLoading ? t('login.submitting') : t('login.submit')}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

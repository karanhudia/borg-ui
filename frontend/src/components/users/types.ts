export interface UserType {
  id: number
  username: string
  full_name?: string | null
  email: string
  is_active: boolean
  role: string
  all_repositories_role?: string | null
  auth_source?: string | null
  oidc_subject?: string | null
  created_at: string
  last_login: string | null
  // Legacy fields that may still appear in API responses
  profile_type?: string
  organization_name?: string
}

export interface UserFormState {
  username: string
  email: string
  password: string
  role: string
  full_name: string
  auth_source: string
  oidc_subject: string
}

export interface PasswordFormState {
  new_password: string
}

export type RoleFilter = 'all' | 'admin' | 'operator' | 'viewer'
export type StatusFilter = 'all' | 'active' | 'inactive' | 'pending_sso'

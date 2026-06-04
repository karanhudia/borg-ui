import { UserType } from './types'

export const getRoleAccentColor = (role: string): string => {
  if (role === 'admin' || role === 'superadmin') return '#7c3aed'
  if (role === 'operator') return '#0891b2'
  return '#059669'
}

export const getInitials = (user: UserType): string => {
  if (user.full_name) {
    const parts = user.full_name.trim().split(/\s+/)
    return parts.length > 1
      ? `${parts[0][0]}${parts[1][0]}`.toUpperCase()
      : parts[0].slice(0, 2).toUpperCase()
  }
  return user.username.slice(0, 2).toUpperCase()
}

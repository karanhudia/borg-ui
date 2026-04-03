import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { authAPI } from '../services/api'
import { useAuth } from './useAuth'

function buildRoleRankMap(roles: Array<{ id: string; rank: number }> | undefined) {
  const rank = new Map<string, number>()
  roles?.forEach((role) => rank.set(role.id, role.rank))
  return rank
}

export function useAuthorization() {
  const { user, hasGlobalPermission } = useAuth()
  const { data, isLoading } = useQuery({
    queryKey: ['authorization-model'],
    queryFn: () => authAPI.getAuthorizationModel().then((r) => r.data),
    staleTime: 5 * 60 * 1000,
  })

  const repositoryRoleRank = useMemo(() => {
    return buildRoleRankMap(data?.repository_roles)
  }, [data])

  const globalRoleRank = useMemo(() => {
    return buildRoleRankMap(data?.global_roles)
  }, [data])

  const canRepositoryRoleDo = (role: string, action: string) => {
    const requiredRole = data?.repository_action_rules?.[action]
    if (!requiredRole) return false
    return (repositoryRoleRank.get(role) ?? 0) >= (repositoryRoleRank.get(requiredRole) ?? 0)
  }

  const roleHasGlobalPermission = (role: string, permission: string) => {
    const requiredRole = data?.global_permission_rules?.[permission]
    if (!requiredRole) return false
    return (globalRoleRank.get(role) ?? 0) >= (globalRoleRank.get(requiredRole) ?? 0)
  }

  const assignableRepositoryRolesFor = (globalRole?: string | null) => {
    if (!globalRole) return []
    return data?.assignable_repository_roles_by_global_role?.[globalRole] ?? []
  }

  return {
    model: data,
    isLoading,
    globalRoles: data?.global_roles ?? [],
    repositoryRoles: data?.repository_roles ?? [],
    repositoryActionRules: data?.repository_action_rules ?? {},
    canRepositoryRoleDo,
    roleHasGlobalPermission,
    assignableRepositoryRolesFor,
    hasGlobalPermission,
    currentGlobalRole: user?.role ?? null,
  }
}

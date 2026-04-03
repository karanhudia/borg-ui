import { useMemo, useCallback } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useAuth } from './useAuth'
import { permissionsAPI } from '../services/api'
import { useAuthorization } from './useAuthorization'

export type RepoAction = 'view' | 'restore' | 'backup' | 'maintenance' | 'delete_archive'

export interface UsePermissionsReturn {
  canAccess: (repoId: number) => boolean
  roleFor: (repoId: number) => string | null
  canDo: (repoId: number, action: RepoAction) => boolean
  isLoading: boolean
}

export function usePermissions(): UsePermissionsReturn {
  const { user, hasGlobalPermission } = useAuth()
  const { canRepositoryRoleDo, repositoryRoles } = useAuthorization()
  const managesAllRepositories = hasGlobalPermission('repositories.manage_all')
  const wildcardRole = user?.all_repositories_role ?? null

  const roleRank = useMemo(() => {
    const rank = new Map<string, number>()
    repositoryRoles.forEach((role) => rank.set(role.id, role.rank))
    return rank
  }, [repositoryRoles])

  const { data: permissions, isLoading } = useQuery({
    queryKey: ['my-permissions'],
    queryFn: () => permissionsAPI.getMyPermissions().then((r) => r.data),
    enabled: !!user && !managesAllRepositories,
    staleTime: 5 * 60 * 1000,
  })

  const permMap = useMemo(() => {
    const map = new Map<number, string>()
    permissions?.forEach((p) => map.set(p.repository_id, p.role))
    return map
  }, [permissions])

  const effectiveRoleFor = useCallback(
    (repoId: number): string | null => {
      const explicitRole = permMap.get(repoId) ?? null
      if (!wildcardRole) return explicitRole
      if (!explicitRole) return wildcardRole
      return (roleRank.get(explicitRole) ?? 0) >= (roleRank.get(wildcardRole) ?? 0)
        ? explicitRole
        : wildcardRole
    },
    [permMap, roleRank, wildcardRole]
  )

  const canAccess = useCallback(
    (repoId: number): boolean => {
      if (managesAllRepositories) return true
      if (wildcardRole) return true
      return permMap.has(repoId)
    },
    [managesAllRepositories, permMap, wildcardRole]
  )

  const roleFor = useCallback(
    (repoId: number): string | null => {
      if (managesAllRepositories) return 'operator'
      return effectiveRoleFor(repoId)
    },
    [effectiveRoleFor, managesAllRepositories]
  )

  const canDo = useCallback(
    (repoId: number, action: RepoAction): boolean => {
      if (managesAllRepositories) return true
      const role = effectiveRoleFor(repoId)
      if (!role) return false
      return canRepositoryRoleDo(role, action)
    },
    [canRepositoryRoleDo, effectiveRoleFor, managesAllRepositories]
  )

  return {
    canAccess,
    roleFor,
    canDo,
    isLoading: !managesAllRepositories && isLoading,
  }
}

import { describe, expect, it } from 'vitest'
import { buildRoutePreviews } from '../routePreview'
import type { Repository, SourceLocation } from '../../../types'
import type { WizardState } from '../types'

// The preview has to name the route backup_route_planner.plan_repository_route
// will take: `remote_direct` only when every source is on the repository's
// SSH host, since that route runs Borg there and can reach no other machine.

const sshRepo = { id: 1, name: 'SSH repo', path: 'ssh://u@h/r', connection_id: 5 } as Repository
const localRepo = { id: 2, name: 'Local repo', path: '/r', connection_id: null } as Repository

function remote(connectionId: number, path = '/data'): SourceLocation {
  return {
    source_type: 'remote',
    source_ssh_connection_id: connectionId,
    agent_machine_id: null,
    paths: [path],
  }
}

const local: SourceLocation = {
  source_type: 'local',
  source_ssh_connection_id: null,
  agent_machine_id: null,
  paths: ['/local'],
}

function preview(repository: Repository, sourceLocations: SourceLocation[]) {
  const state = { sourceLocations, sourceDirectories: [] } as unknown as WizardState
  const [result] = buildRoutePreviews([repository], state, [])
  return { strategy: result.strategy, executor: result.executor }
}

describe('buildRoutePreviews', () => {
  it('runs directly on the repository host when it is the only source', () => {
    expect(preview(sshRepo, [remote(5)])).toEqual({ strategy: 'remote_direct', executor: 'ssh' })
    expect(preview(sshRepo, [remote(5, '/a'), remote(5, '/b')])).toEqual({
      strategy: 'remote_direct',
      executor: 'ssh',
    })
  })

  it('pulls over SSHFS when the source is another machine', () => {
    expect(preview(sshRepo, [remote(4)])).toEqual({
      strategy: 'server_sshfs_pull_then_borg_ssh',
      executor: 'server',
    })
  })

  it('pulls over SSHFS when only the first of several sources is the repository host', () => {
    expect(preview(sshRepo, [remote(5), remote(4)])).toEqual({
      strategy: 'server_sshfs_pull_then_borg_ssh',
      executor: 'server',
    })
  })

  it('pulls over SSHFS when a local source comes before a remote one', () => {
    expect(preview(sshRepo, [local, remote(5)])).toEqual({
      strategy: 'server_sshfs_pull_then_borg_ssh',
      executor: 'server',
    })
  })

  it('pulls into a server-side repository without an SSH connection', () => {
    expect(preview(localRepo, [remote(5)])).toEqual({
      strategy: 'server_sshfs_pull',
      executor: 'server',
    })
  })

  it('runs Borg on the server for local sources', () => {
    expect(preview(sshRepo, [local])).toEqual({
      strategy: 'server_direct_borg_ssh',
      executor: 'server',
    })
    expect(preview(localRepo, [local])).toEqual({ strategy: 'server_direct', executor: 'server' })
  })
})

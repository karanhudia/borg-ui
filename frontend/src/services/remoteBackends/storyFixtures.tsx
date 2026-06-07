import { useState, type ReactNode } from 'react'
import { RemoteBackendProvider } from './context'
import {
  createRemoteBackendClient,
  deleteRemoteBackendClient,
  listRemoteBackendClients,
  resetRemoteBackendStateForTests,
  setActiveBackendTarget,
  updateRemoteBackendClient,
  updateRemoteBackendHealth,
} from './storage'
import type { RemoteBackendClient } from './types'

type RemoteBackendStoryState = 'empty' | 'mixed' | 'activeRemote'

interface RemoteBackendStoryProviderProps {
  children: ReactNode
  state?: RemoteBackendStoryState
}

function storyClientResponse(client: RemoteBackendClient) {
  return {
    id: client.id,
    name: client.name,
    api_base_url: client.apiBaseUrl,
    web_base_url: client.webBaseUrl,
    created_at: client.createdAt,
    updated_at: client.updatedAt,
    health: {
      status: client.health.status,
      checked_at: client.health.checkedAt ?? null,
      app_version: client.health.appVersion ?? null,
      borg_version: client.health.borgVersion ?? null,
      borg2_version: client.health.borg2Version ?? null,
      error: client.health.error ?? null,
      compatibility: client.health.compatibility,
      compatibility_message: client.health.compatibilityMessage ?? null,
    },
  }
}

const storyFetch: typeof fetch = async (input, init) => {
  const url =
    typeof input === 'string' ? input : input instanceof Request ? input.url : String(input)
  const path = new URL(url, window.location.origin).pathname
  const remoteClientsIndex = path.lastIndexOf('/api/remote-clients')

  if (remoteClientsIndex !== -1) {
    const method = init?.method ?? 'GET'
    const tail = path.slice(remoteClientsIndex + '/api/remote-clients'.length)

    if (tail === '' && method === 'GET') {
      return new Response(JSON.stringify(listRemoteBackendClients().map(storyClientResponse)), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      })
    }

    if (tail === '' && method === 'POST') {
      const body = JSON.parse(String(init?.body ?? '{}')) as {
        name?: string
        backend_url?: string
      }
      const client = createRemoteBackendClient({
        name: body.name ?? 'Remote client',
        backendUrl: body.backend_url ?? '',
      })
      return new Response(JSON.stringify(storyClientResponse(client)), {
        status: 201,
        headers: { 'Content-Type': 'application/json' },
      })
    }

    const id = decodeURIComponent(tail.replace(/^\//, '').replace(/\/health$/, ''))
    if (id && method === 'PUT') {
      const body = JSON.parse(String(init?.body ?? '{}')) as {
        name?: string
        backend_url?: string
      }
      const client = updateRemoteBackendClient(id, {
        name: body.name ?? 'Remote client',
        backendUrl: body.backend_url ?? '',
      })
      return new Response(JSON.stringify(storyClientResponse(client)), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      })
    }

    if (id && method === 'PATCH' && tail.endsWith('/health')) {
      const body = JSON.parse(String(init?.body ?? '{}')) as Record<string, unknown>
      const client = updateRemoteBackendHealth(id, {
        status: body.status as RemoteBackendClient['health']['status'],
        checkedAt: body.checked_at as string | null,
        appVersion: body.app_version as string | null,
        borgVersion: body.borg_version as string | null,
        borg2Version: body.borg2_version as string | null,
        error: body.error as string | null,
        compatibility: body.compatibility as RemoteBackendClient['health']['compatibility'],
        compatibilityMessage: body.compatibility_message as string | null,
      })
      return new Response(JSON.stringify(storyClientResponse(client)), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      })
    }

    if (id && method === 'DELETE') {
      deleteRemoteBackendClient(id)
      return new Response(null, { status: 204 })
    }
  }

  if (url.endsWith('/health')) {
    return new Response(JSON.stringify({ status: 'ok' }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    })
  }

  if (url.endsWith('/system/info')) {
    return new Response(
      JSON.stringify({
        app_version: '2.2.2-alpha.1',
        borg_version: '1.4.1',
        borg2_version: '2.0.0b19',
      }),
      { status: 200, headers: { 'Content-Type': 'application/json' } }
    )
  }

  return new Response(JSON.stringify({ detail: 'Not found' }), { status: 404 })
}

function seedRemoteBackends(state: RemoteBackendStoryState): void {
  resetRemoteBackendStateForTests()
  if (state === 'empty') return

  const online = createRemoteBackendClient({
    name: 'Studio NAS',
    backendUrl: 'https://nas.example.com/api',
  })
  updateRemoteBackendHealth(online.id, {
    status: 'online',
    checkedAt: '2026-06-05T06:30:00.000Z',
    appVersion: '2.2.2-alpha.1',
    borgVersion: '1.4.1',
    borg2Version: '2.0.0b19',
    compatibility: 'compatible',
    compatibilityMessage: 'Compatible with this frontend.',
  })

  const offline = createRemoteBackendClient({
    name: 'Workshop Mini PC',
    backendUrl: 'http://192.168.1.42:8081',
  })
  updateRemoteBackendHealth(offline.id, {
    status: 'offline',
    checkedAt: '2026-06-05T05:12:00.000Z',
    error: 'Health check failed with HTTP 502.',
    compatibility: 'unknown',
    compatibilityMessage: 'Remote client server compatibility could not be checked.',
  })

  const incompatible = createRemoteBackendClient({
    name: 'Legacy Server',
    backendUrl: 'https://legacy.example.com',
  })
  updateRemoteBackendHealth(incompatible.id, {
    status: 'online',
    checkedAt: '2026-06-05T04:50:00.000Z',
    appVersion: '1.9.0',
    compatibility: 'incompatible',
    compatibilityMessage: 'Borg UI 1.9.0 is not compatible with frontend version 2.2.2-alpha.1.',
  })

  if (state === 'activeRemote') {
    setActiveBackendTarget(online.id)
  }
}

export function RemoteBackendStoryProvider({
  children,
  state = 'mixed',
}: RemoteBackendStoryProviderProps) {
  return (
    <SeededRemoteBackendStoryProvider key={state} state={state}>
      {children}
    </SeededRemoteBackendStoryProvider>
  )
}

function SeededRemoteBackendStoryProvider({
  children,
  state,
}: Required<RemoteBackendStoryProviderProps>) {
  const [seededState] = useState(() => {
    // Storybook fixtures must exist before RemoteBackendProvider reads its initial snapshot.
    seedRemoteBackends(state)
    return state
  })

  return (
    <RemoteBackendProvider key={seededState} fetchImpl={storyFetch}>
      {children}
    </RemoteBackendProvider>
  )
}

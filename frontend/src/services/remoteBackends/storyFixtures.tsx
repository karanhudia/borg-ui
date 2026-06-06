import { useEffect, useRef, type ReactNode } from 'react'
import { RemoteBackendProvider } from './context'
import {
  createRemoteBackendClient,
  resetRemoteBackendStateForTests,
  setActiveBackendTarget,
  updateRemoteBackendHealth,
} from './storage'

type RemoteBackendStoryState = 'empty' | 'mixed' | 'activeRemote'

interface RemoteBackendStoryProviderProps {
  children: ReactNode
  state?: RemoteBackendStoryState
}

const storyFetch: typeof fetch = async (input) => {
  const url =
    typeof input === 'string' ? input : input instanceof Request ? input.url : String(input)

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
  const seededRef = useRef(false)

  useEffect(() => {
    if (seededRef.current) return
    seededRef.current = true
    seedRemoteBackends(state)
  }, [state])

  return <RemoteBackendProvider fetchImpl={storyFetch}>{children}</RemoteBackendProvider>
}

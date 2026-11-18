import { describe, expect, it } from 'vitest'
import { backendOrigin, buildClientSnippets, mcpEndpointUrl } from '../clientSnippets'

const URL = 'https://backups.example.com/mcp'
const TOKEN = 'borgui_EXAMPLE'

describe('mcpEndpointUrl', () => {
  it('keeps the base path', () => {
    expect(mcpEndpointUrl('/borg/mcp', 'https://backups.example.com')).toBe(
      'https://backups.example.com/borg/mcp'
    )
  })
})

describe('backendOrigin', () => {
  it('uses the browser origin for the local backend', () => {
    expect(backendOrigin({ kind: 'local', webBaseUrl: '/borg' }, 'https://hub.example.com')).toBe(
      'https://hub.example.com'
    )
  })

  it('uses the remote backend origin, not the hub', () => {
    expect(
      backendOrigin(
        { kind: 'remote', webBaseUrl: 'https://remote.example.com/borg' },
        'https://hub.example.com'
      )
    ).toBe('https://remote.example.com')
  })
})

describe('buildClientSnippets', () => {
  const snippets = buildClientSnippets(URL, TOKEN)

  it('covers the clients in order', () => {
    expect(snippets.map((s) => s.id)).toEqual([
      'claude-code',
      'claude-desktop',
      'cursor',
      'vscode',
      'generic',
    ])
  })

  it('puts url and token in every snippet', () => {
    for (const s of snippets) {
      expect(s.code).toContain(URL)
      expect(s.code).toContain(TOKEN)
    }
  })

  it('json snippets parse', () => {
    snippets
      .filter((s) => s.language === 'json')
      .forEach((s) => expect(() => JSON.parse(s.code)).not.toThrow())
  })

  it('claude code is one command', () => {
    expect(snippets[0].code).toBe(
      `claude mcp add --transport http borg-ui ${URL} --header "Authorization: Bearer ${TOKEN}"`
    )
  })

  it('claude desktop keeps the space out of args', () => {
    const server = JSON.parse(snippets[1].code).mcpServers['borg-ui']
    expect(server.args).toEqual([
      '-y',
      'mcp-remote',
      URL,
      '--header',
      'Authorization:${AUTH_HEADER}',
    ])
    expect(server.env).toEqual({ AUTH_HEADER: `Bearer ${TOKEN}` })
  })

  it('vs code goes in the per-user file, not the shared workspace one', () => {
    expect(snippets[3].where).toBe('~/.copilot/mcp-config.json')
  })

  it('vs code uses the http server format', () => {
    expect(JSON.parse(snippets[3].code).mcpServers['borg-ui']).toEqual({
      type: 'http',
      url: URL,
      headers: { Authorization: `Bearer ${TOKEN}` },
    })
  })
})

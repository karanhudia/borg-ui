/**
 * Setup snippets for MCP clients. Checked against each client's docs on
 * 2026-11-18. Windsurf is left out: its docs now redirect to Devin and the
 * format could not be confirmed; the generic snippet covers it.
 */

export type McpClientId = 'claude-code' | 'claude-desktop' | 'cursor' | 'vscode' | 'generic'

export interface ClientSnippet {
  id: McpClientId
  /** Product name, not translated. Null for the generic snippet. */
  label: string | null
  /** The file the snippet goes in, or null for a command. */
  where: string | null
  language: 'bash' | 'json' | 'text'
  code: string
}

export const mcpEndpointUrl = (endpointPath: string, origin = window.location.origin): string =>
  `${origin}${endpointPath}`

const json = (value: unknown) => JSON.stringify(value, null, 2)

export function buildClientSnippets(url: string, token: string): ClientSnippet[] {
  const bearer = `Bearer ${token}`
  const httpServer = { type: 'http', url, headers: { Authorization: bearer } }
  return [
    {
      id: 'claude-code',
      label: 'Claude Code',
      where: null,
      language: 'bash',
      code: `claude mcp add --transport http borg-ui ${url} --header "Authorization: ${bearer}"`,
    },
    {
      id: 'claude-desktop',
      label: 'Claude Desktop',
      where: 'claude_desktop_config.json',
      language: 'json',
      // mcp-remote's documented workaround: spaces in args get mangled, so
      // the header value travels through env.
      code: json({
        mcpServers: {
          'borg-ui': {
            command: 'npx',
            args: ['-y', 'mcp-remote', url, '--header', 'Authorization:${AUTH_HEADER}'],
            env: { AUTH_HEADER: bearer },
          },
        },
      }),
    },
    {
      id: 'cursor',
      label: 'Cursor',
      where: '~/.cursor/mcp.json',
      language: 'json',
      code: json({ mcpServers: { 'borg-ui': { url, headers: { Authorization: bearer } } } }),
    },
    {
      id: 'vscode',
      label: 'VS Code',
      where: '.mcp.json',
      language: 'json',
      code: json({ mcpServers: { 'borg-ui': httpServer } }),
    },
    {
      id: 'generic',
      label: null,
      where: null,
      language: 'text',
      code: `URL: ${url}\nHeader: Authorization: ${bearer}`,
    },
  ]
}

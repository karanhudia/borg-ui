/** Reads the deploy link the MCP `add_ssh_connection` tool hands the user when
 *  a key still needs the server's password (spec 2026-11-14-mcp-server 5.9).
 *  The password itself is never in the link. */
export function parseDeployPrefill(
  params: URLSearchParams
): { host?: string; username?: string; port?: number } | null {
  if (params.get('deploy') !== '1') return null
  const values: { host?: string; username?: string; port?: number } = {}
  const host = params.get('host')
  const username = params.get('username')
  if (host) values.host = host
  if (username) values.username = username
  const port = Number(params.get('port'))
  if (Number.isInteger(port) && port > 0 && port < 65536) values.port = port
  return values
}

export const DEPLOY_PREFILL_PARAMS = ['deploy', 'host', 'username', 'port']

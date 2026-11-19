import type { McpLevel } from '../../services/api'

export const MCP_LEVELS: McpLevel[] = ['read', 'operate', 'manage', 'full']

export const levelRank = (level: McpLevel) => MCP_LEVELS.indexOf(level)

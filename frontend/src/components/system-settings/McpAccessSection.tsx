import { useEffect, useState } from 'react'
import {
  Box,
  Button,
  CircularProgress,
  FormControl,
  FormControlLabel,
  FormHelperText,
  InputLabel,
  MenuItem,
  Select,
  Stack,
  Switch,
  Typography,
} from '@mui/material'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'react-hot-toast'
import { useTranslation } from 'react-i18next'
import { mcpAPI, type McpLevel } from '../../services/api'
import { translateBackendKey, type BackendDetail } from '../../utils/translateBackendKey'
import PlanGate from '../shared/PlanGate'
import { MCP_LEVELS } from '../mcp/levels'

/** Admin switch and level cap for MCP. Saves on its own: the MCP config has
 * its own endpoint, apart from the rest of System settings. */
function McpAccessForm() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const config = useQuery({
    queryKey: ['mcp-config'],
    queryFn: () => mcpAPI.getConfig().then((r) => r.data),
  })
  const [enabled, setEnabled] = useState(true)
  const [cap, setCap] = useState<McpLevel>('full')

  useEffect(() => {
    if (!config.data) return
    setEnabled(config.data.enabled)
    setCap(config.data.max_access_level)
  }, [config.data])

  const save = useMutation({
    mutationFn: () => mcpAPI.updateConfig({ enabled, max_access_level: cap }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mcp-config'] })
      queryClient.invalidateQueries({ queryKey: ['mcp-connections'] })
      toast.success(t('systemSettings.mcpSaved'))
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) =>
      toast.error(translateBackendKey(error?.response?.data?.detail as BackendDetail)),
  })

  if (!config.data) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', py: 4 }}>
        <CircularProgress size={24} />
      </Box>
    )
  }
  const changed = enabled !== config.data.enabled || cap !== config.data.max_access_level
  const levelsWithTools = config.data.available_levels
    .map((level) => t(`mcp.levels.${level}.title`))
    .join(', ')

  return (
    <Stack spacing={2.5} sx={{ maxWidth: 560 }}>
      <Box>
        <FormControlLabel
          control={<Switch checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />}
          label={t('systemSettings.mcpEnabled')}
        />
        <Typography variant="body2" color="text.secondary">
          {t('systemSettings.mcpEnabledHelp')}
        </Typography>
      </Box>
      <FormControl fullWidth>
        <InputLabel id="mcp-max-level-label">{t('systemSettings.mcpMaxLevel')}</InputLabel>
        <Select
          labelId="mcp-max-level-label"
          label={t('systemSettings.mcpMaxLevel')}
          value={cap}
          onChange={(e) => setCap(e.target.value as McpLevel)}
        >
          {MCP_LEVELS.map((level) => (
            <MenuItem key={level} value={level}>
              {t(`mcp.levels.${level}.title`)}
            </MenuItem>
          ))}
        </Select>
        <FormHelperText>{t('systemSettings.mcpMaxLevelHelp')}</FormHelperText>
        <FormHelperText>
          {t('systemSettings.mcpToolsToday', { levels: levelsWithTools })}
        </FormHelperText>
      </FormControl>
      <Box>
        <Button
          variant="contained"
          onClick={() => save.mutate()}
          disabled={!changed || save.isPending}
          sx={{ minHeight: 44 }}
        >
          {t('systemSettings.mcpSave')}
        </Button>
      </Box>
    </Stack>
  )
}

export default function McpAccessSection() {
  return (
    <PlanGate feature="mcp" surface="system_settings_mcp">
      <McpAccessForm />
    </PlanGate>
  )
}

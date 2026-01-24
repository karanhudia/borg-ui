import { useState } from 'react'
import {
  Box,
  TextField,
  Typography,
  IconButton,
  InputAdornment,
  Tooltip,
  Chip,
} from '@mui/material'
import { Eye, EyeOff, Lock, Type } from 'lucide-react'

export interface ScriptParameter {
  name: string
  type: 'text' | 'password'
  default: string
  description: string
  required: boolean
}

interface ScriptParameterInputsProps {
  parameters: ScriptParameter[]
  values: Record<string, string>
  onChange: (values: Record<string, string>) => void
  showDescriptions?: boolean
}

export default function ScriptParameterInputs({
  parameters,
  values,
  onChange,
  showDescriptions = true,
}: ScriptParameterInputsProps) {
  const [showPassword, setShowPassword] = useState<Record<string, boolean>>({})

  if (!parameters || parameters.length === 0) {
    return null
  }

  const handleChange = (paramName: string, value: string) => {
    onChange({
      ...values,
      [paramName]: value,
    })
  }

  const toggleShowPassword = (paramName: string) => {
    setShowPassword((prev) => ({
      ...prev,
      [paramName]: !prev[paramName],
    }))
  }

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
        <Typography variant="subtitle2" fontWeight={600}>
          Script Parameters
        </Typography>
        <Chip
          label={`${parameters.length} parameter${parameters.length !== 1 ? 's' : ''}`}
          size="small"
          color="primary"
          variant="outlined"
        />
      </Box>

      {parameters.map((param) => {
        const isPassword = param.type === 'password'
        const shouldShow = showPassword[param.name]
        const currentValue = values[param.name] || ''

        return (
          <Box key={param.name}>
            <TextField
              fullWidth
              label={param.name
                .replace(/_/g, ' ')
                .toLowerCase()
                .replace(/\b\w/g, (c) => c.toUpperCase())}
              type={isPassword && !shouldShow ? 'password' : 'text'}
              value={currentValue}
              onChange={(e) => handleChange(param.name, e.target.value)}
              required={param.required}
              placeholder={param.default || ''}
              helperText={showDescriptions ? param.description : undefined}
              InputProps={{
                startAdornment: (
                  <InputAdornment position="start">
                    {isPassword ? <Lock size={18} color="#666" /> : <Type size={18} color="#666" />}
                  </InputAdornment>
                ),
                endAdornment: isPassword ? (
                  <InputAdornment position="end">
                    <Tooltip title={shouldShow ? 'Hide password' : 'Show password'}>
                      <IconButton
                        size="small"
                        onClick={() => toggleShowPassword(param.name)}
                        edge="end"
                      >
                        {shouldShow ? <EyeOff size={18} /> : <Eye size={18} />}
                      </IconButton>
                    </Tooltip>
                  </InputAdornment>
                ) : null,
              }}
              sx={{
                '& .MuiInputBase-root': {
                  backgroundColor: isPassword ? 'rgba(255, 152, 0, 0.04)' : undefined,
                },
              }}
            />
          </Box>
        )
      })}
    </Box>
  )
}

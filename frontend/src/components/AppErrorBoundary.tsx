import React from 'react'
import { Box, Button, Card, CardContent, Typography } from '@mui/material'
import i18n from '../i18n'
import { reportError } from '../utils/errorReporting'

// Read straight from the i18n instance, in a try, so the crash screen cannot throw
// because a hook or context is broken.
const text = (key: string, fallback: string): string => {
  try {
    const value = i18n.t(key)
    return typeof value === 'string' && value && value !== key ? value : fallback
  } catch {
    return fallback
  }
}

/** The first component name in a React component stack, e.g. "\n    at Boom (file:1:2)". */
const firstComponent = (componentStack?: string | null): string | undefined =>
  /^\s*(?:at\s+)?([^\s(@]+)/.exec(componentStack ?? '')?.[1]

export class AppErrorBoundary extends React.Component<
  { children: React.ReactNode },
  { crashed: boolean }
> {
  state = { crashed: false }

  static getDerivedStateFromError() {
    return { crashed: true }
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    reportError(error, { kind: 'render', component: firstComponent(info?.componentStack) })
  }

  render() {
    if (!this.state.crashed) return this.props.children
    return (
      <Box
        sx={{
          minHeight: '100vh',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          p: 2,
        }}
      >
        <Card sx={{ maxWidth: 440 }}>
          <CardContent sx={{ textAlign: 'center' }}>
            <Typography variant="h5" gutterBottom>
              {text('errorBoundary.title', 'Something went wrong')}
            </Typography>
            <Typography color="text.secondary" sx={{ mb: 3 }}>
              {text(
                'errorBoundary.message',
                'Borg UI hit an unexpected error. Reloading usually fixes it.'
              )}
            </Typography>
            <Button variant="contained" onClick={() => window.location.reload()}>
              {text('errorBoundary.reload', 'Reload')}
            </Button>
          </CardContent>
        </Card>
      </Box>
    )
  }
}

export default AppErrorBoundary

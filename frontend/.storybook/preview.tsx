import type { Preview } from '@storybook/react-vite'
import CssBaseline from '@mui/material/CssBaseline'
import { ThemeProvider } from '@mui/material/styles'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import '../src/i18n'
import '../src/index.css'
import { getTheme } from '../src/theme'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: false,
      refetchOnWindowFocus: false,
    },
  },
})

const preview: Preview = {
  decorators: [
    (Story) => (
      <ThemeProvider theme={getTheme('light')}>
        <CssBaseline />
        <QueryClientProvider client={queryClient}>
          <Story />
        </QueryClientProvider>
      </ThemeProvider>
    ),
  ],
  parameters: {
    backgrounds: {
      default: 'Borg surface',
      values: [{ name: 'Borg surface', value: '#f9fafb' }],
    },
  },
}

export default preview

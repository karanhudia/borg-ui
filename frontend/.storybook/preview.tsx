import type { Preview } from '@storybook/react-vite'
import CssBaseline from '@mui/material/CssBaseline'
import { ThemeProvider } from '@mui/material/styles'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import '../src/i18n'
import '../src/index.css'
import { getTheme } from '../src/theme'
import type { SystemInfo } from '../src/hooks/useSystemInfo'

type RouterParameters = {
  initialEntries?: string[]
}

function createStoryQueryClient(systemInfo?: SystemInfo) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        refetchOnWindowFocus: false,
      },
    },
  })

  if (systemInfo) {
    queryClient.setQueryData(['system-info'], systemInfo)
  }

  return queryClient
}

const preview: Preview = {
  decorators: [
    (Story, context) => {
      const systemInfo = context.parameters.systemInfo as SystemInfo | undefined
      // Every story gets a router: components reach useNavigate/useLocation
      // through children (RepositoryCard does), and without one they render
      // Storybook's error page instead of the component. Stories that need a
      // specific location set parameters.router.initialEntries.
      const router = context.parameters.router as RouterParameters | undefined

      return (
        <ThemeProvider theme={getTheme('light')}>
          <CssBaseline />
          <QueryClientProvider client={createStoryQueryClient(systemInfo)}>
            <MemoryRouter initialEntries={router?.initialEntries ?? ['/']}>
              <Story />
            </MemoryRouter>
          </QueryClientProvider>
        </ThemeProvider>
      )
    },
  ],
  parameters: {
    backgrounds: {
      default: 'Borg surface',
      values: [{ name: 'Borg surface', value: '#f9fafb' }],
    },
  },
}

export default preview

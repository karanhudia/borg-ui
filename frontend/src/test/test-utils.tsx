import { ReactElement, ReactNode } from 'react'
import { render, RenderOptions } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ThemeProvider, createTheme } from '@mui/material/styles'
import { Toaster } from 'react-hot-toast'

// Create a theme for testing
const theme = createTheme({
  palette: {
    mode: 'light',
  },
})

// Create a fresh QueryClient for each test
function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false, // Don't retry failed requests in tests
        gcTime: Infinity, // Keep data in cache forever in tests
      },
      mutations: {
        retry: false,
      },
    },
  })
}

interface AllProvidersProps {
  children: ReactNode
  queryClient?: QueryClient
}

/**
 * Wrapper component that provides all necessary context providers for testing
 */
export function AllProviders({ children, queryClient }: AllProvidersProps) {
  const testQueryClient = queryClient || createTestQueryClient()

  return (
    <QueryClientProvider client={testQueryClient}>
      <BrowserRouter>
        <ThemeProvider theme={theme}>
          {children}
          <Toaster position="top-right" />
        </ThemeProvider>
      </BrowserRouter>
    </QueryClientProvider>
  )
}

interface CustomRenderOptions extends Omit<RenderOptions, 'wrapper'> {
  queryClient?: QueryClient
  initialRoute?: string
}

/**
 * Custom render function that wraps components with all providers
 */
export function renderWithProviders(
  ui: ReactElement,
  { queryClient, initialRoute = '/', ...renderOptions }: CustomRenderOptions = {}
) {
  // Set initial route if provided
  if (initialRoute !== '/') {
    window.history.pushState({}, 'Test page', initialRoute)
  }

  const Wrapper = ({ children }: { children: ReactNode }) => (
    <AllProviders queryClient={queryClient}>{children}</AllProviders>
  )

  return {
    ...render(ui, { wrapper: Wrapper, ...renderOptions }),
    queryClient: queryClient || createTestQueryClient(),
  }
}

/**
 * Wait for async operations to complete
 */
export const waitFor = async (callback: () => void, options?: { timeout?: number }) => {
  const { timeout = 3000 } = options || {}
  const startTime = Date.now()

  while (Date.now() - startTime < timeout) {
    try {
      callback()
      return
    } catch (error) {
      await new Promise((resolve) => setTimeout(resolve, 50))
    }
  }

  throw new Error('Timeout waiting for condition')
}

/**
 * Create mock API responses for testing
 */
export const mockApiResponse = <T,>(data: T, delay = 0): Promise<T> => {
  return new Promise((resolve) => {
    setTimeout(() => resolve(data), delay)
  })
}

/**
 * Create mock API error for testing
 */
export const mockApiError = (message: string, status = 500, delay = 0): Promise<never> => {
  return new Promise((_, reject) => {
    setTimeout(() => {
      reject({
        response: {
          status,
          data: {
            detail: message,
          },
        },
      })
    }, delay)
  })
}

// Re-export everything from @testing-library/react
export * from '@testing-library/react'
export { default as userEvent } from '@testing-library/user-event'
